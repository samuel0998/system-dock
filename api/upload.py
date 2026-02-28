from flask import Blueprint, render_template, request, jsonify, current_app
import pandas as pd
from datetime import datetime, timezone, timedelta

from db import db
from models import Carga

upload_bp = Blueprint("upload", __name__, url_prefix="/upload")


@upload_bp.route("/")
def upload_page():
    return render_template("upload.html")


def _get_col(row, *names, default=None):
    # tenta match direto
    for n in names:
        if n in row and pd.notna(row.get(n)):
            return row.get(n)

    # tenta case-insensitive
    row_keys_lower = {str(k).strip().lower(): k for k in row.index}
    for n in names:
        key = row_keys_lower.get(str(n).strip().lower())
        if key is not None and pd.notna(row.get(key)):
            return row.get(key)

    return default


def _normalize_type(raw):
    """
    Coluna B (Type):
      - OTHER / CARP => VDD
      - TRANSSHIP => Transferência
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, None

    s = str(raw).strip()
    if not s:
        return None, None

    up = s.upper()
    up = (
        up.replace("TRASNSSHIP", "TRANSSHIP")
          .replace("TRANS SHIP", "TRANSSHIP")
          .replace("TRANS-SHIP", "TRANSSHIP")
    )

    if up in ("OTHER", "CARP"):
        return up, "VDD"
    if up == "TRANSSHIP":
        return up, "Transferência"

    return up, None


def _to_utc_aware(dt):
    if dt is None or pd.isna(dt):
        return None

    try:
        d = pd.to_datetime(dt, errors="coerce")
    except Exception:
        return None

    if pd.isna(d):
        return None

    # se vier tz quebrada (ex: "BRT"), pandas pode dropar tz.
    py = d.to_pydatetime()

    if py.tzinfo is None:
        return py.replace(tzinfo=timezone.utc)

    return py.astimezone(timezone.utc)


def _status_do_sistema(plan_status_raw: object) -> str | None:
    """
    LÓGICA DO SISTEMA (não copia status livremente)
    - ARRIVAL_SCHEDULED -> arrival_scheduled
    - CLOSED -> None (ignora)
    - qualquer outro -> arrival
    """
    if plan_status_raw is None or (isinstance(plan_status_raw, float) and pd.isna(plan_status_raw)):
        return "arrival"

    s = str(plan_status_raw).strip().upper()
    if not s:
        return "arrival"

    # normaliza
    s = s.replace("ARRIVED", "ARRIVAL")

    if s == "ARRIVAL_SCHEDULED":
        return "arrival_scheduled"
    if s == "CLOSED":
        return None

    return "arrival"


@upload_bp.route("/processar", methods=["POST"])
def processar_planilha():
    file = request.files.get("file")
    if not file:
        return jsonify({"message": "Nenhum arquivo enviado.", "inseridas": 0, "atualizadas": 0, "ignoradas": 0, "erros": []}), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return jsonify({"message": f"Erro ao ler arquivo Excel: {str(e)}", "inseridas": 0, "atualizadas": 0, "ignoradas": 0, "erros": []}), 400

    inseridas = 0
    atualizadas = 0
    ignoradas = 0
    repetidas_no_arquivo = 0
    erros: list[str] = []

    agora = datetime.now(timezone.utc)

    seen_appointments: set[str] = set()

    for idx, row in df.iterrows():
        try:
            # A = Appointment ID | B = Type (garante mesmo se header mudar)
            appointment_id = row.iloc[0] if len(row) > 0 else None
            if appointment_id is None or pd.isna(appointment_id):
                ignoradas += 1
                continue

            appointment_str = str(appointment_id).strip()
            if not appointment_str:
                ignoradas += 1
                continue

            if appointment_str in seen_appointments:
                repetidas_no_arquivo += 1
            else:
                seen_appointments.add(appointment_str)

            type_raw = row.iloc[1] if len(row) > 1 else None
            truck_type, truck_tipo = _normalize_type(type_raw)

            # Datas
            expected_arrival = _to_utc_aware(_get_col(row, "Expected Arrival Date", default=None))
            priority_last_update = _to_utc_aware(_get_col(row, "Priority Score Last Updated Date", default=None))

            # sem expected_arrival não dá pra SLA / no_show
            if not expected_arrival:
                ignoradas += 1
                continue

            # Units / Cartons
            units_raw = _get_col(row, "Units", "UNITS", "units", default=0)
            cartons_raw = _get_col(row, "Cartons", "CARTONS", "cartons", default=0)

            try:
                units_val = 0 if pd.isna(units_raw) else int(float(units_raw))
            except Exception:
                units_val = 0

            try:
                cartons_val = 0 if pd.isna(cartons_raw) else int(float(cartons_raw))
            except Exception:
                cartons_val = 0

            # Priority score
            priority_score_raw = _get_col(row, "Priority Score", default=0) or 0
            try:
                priority_score = float(priority_score_raw)
            except Exception:
                priority_score = 0.0

            # STATUS (lógica do sistema)
            plan_status = _get_col(row, "Status", "STATUS", default=None)
            status = _status_do_sistema(plan_status)

            # CLOSED -> ignorar
            if status is None:
                ignoradas += 1
                continue

            # regra: arrival_scheduled passou 24h -> no_show
            if status == "arrival_scheduled":
                if agora > (expected_arrival + timedelta(hours=24)):
                    status = "no_show"

            prioridade_maxima = False
            if priority_last_update:
                prioridade_maxima = priority_last_update < expected_arrival

            # UPSERT por appointment_id
            carga = Carga.query.filter_by(appointment_id=appointment_str).first()
            if carga:
                carga.expected_arrival_date = expected_arrival
                carga.priority_last_update = priority_last_update
                carga.priority_score = priority_score
                carga.prioridade_maxima = prioridade_maxima

                # ✅ não sobrescreve checkin/closed se já estiver rodando
                if carga.status not in ("checkin", "closed"):
                    carga.status = status

                carga.cartons = cartons_val
                carga.units = units_val
                carga.truck_type = truck_type
                carga.truck_tipo = truck_tipo

                atualizadas += 1
            else:
                carga = Carga(
                    appointment_id=appointment_str,
                    expected_arrival_date=expected_arrival,
                    priority_last_update=priority_last_update,
                    priority_score=priority_score,
                    prioridade_maxima=prioridade_maxima,
                    status=status,
                    cartons=cartons_val,
                    units=units_val,
                    truck_type=truck_type,
                    truck_tipo=truck_tipo,
                    created_at=agora,

                    aa_responsavel=None,
                    start_time=None,
                    end_time=None,
                    tempo_total_segundos=None,
                    units_por_hora=None,

                    arrived_at=None,
                    sla_setar_aa_deadline=None,
                    atraso_registrado=False,
                    atraso_segundos=0,
                )
                db.session.add(carga)
                inseridas += 1

        except Exception as e:
            ignoradas += 1
            erros.append(f"Linha {idx+2}: {str(e)}")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Erro ao salvar upload")
        return jsonify({
            "message": f"Erro ao salvar no banco: {str(e)}",
            "inseridas": 0,
            "atualizadas": 0,
            "ignoradas": int(len(df)),
            "erros": erros[:30],
        }), 500

    return jsonify({
        "message": "Upload concluído com sucesso!",
        "inseridas": inseridas,
        "atualizadas": atualizadas,
        "ignoradas": ignoradas,
        "repetidas_no_arquivo": repetidas_no_arquivo,
        "observacao": "Quando o mesmo Appointment ID aparece mais de uma vez, o sistema atualiza o registro já existente em vez de criar uma nova carga.",
        "erros": erros[:30],
    }), 200
