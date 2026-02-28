from flask import Blueprint, render_template, request, jsonify, current_app
import pandas as pd
from datetime import datetime, timezone

from db import db
from models import Carga

upload_bp = Blueprint("upload", __name__, url_prefix="/upload")


@upload_bp.route("/")
def upload_page():
    return render_template("upload.html")


def _get_col(row, *names, default=None):
    """
    Pega a primeira coluna existente (case insensitive) dentre as opções.
    Ex: _get_col(row, "Units", "UNITS", "units")
    """
    # match direto
    for n in names:
        if n in row and pd.notna(row.get(n)):
            return row.get(n)

    # match case-insensitive
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
    Retorna: (truck_type_bruto, truck_tipo_normalizado)
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, None

    s = str(raw).strip()
    if not s:
        return None, None

    up = s.upper()

    # normaliza erros comuns
    up = (
        up.replace("TRASNSSHIP", "TRANSSHIP")
          .replace("TRASNSHIP", "TRANSSHIP")
          .replace("TRANS SHIP", "TRANSSHIP")
          .replace("TRANS-SHIP", "TRANSSHIP")
          .replace("TRANSSHIPMENT", "TRANSSHIP")
    )

    if up in ("OTHER", "CARP"):
        return up, "VDD"
    if up == "TRANSSHIP":
        return up, "Transferência"

    return up, None


def _normalize_status(raw):
    """
    Status vindo da planilha:
      - ARRIVAL_SCHEDULED -> arrival_scheduled
      - ARRIVAL -> arrival
      - CHECKIN -> checkin
      - CLOSED / CONCLUIDAS -> closed
      - NO_SHOW -> no_show
    Se não vier, default = arrival
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "arrival"

    s = str(raw).strip()
    if not s:
        return "arrival"

    up = s.upper().replace(" ", "_")

    if up == "ARRIVAL_SCHEDULED":
        return "arrival_scheduled"
    if up == "ARRIVAL":
        return "arrival"
    if up == "CHECKIN":
        return "checkin"
    if up in ("CLOSED", "CONCLUIDAS", "CONCLUÍDAS", "CONCLUIDA", "CONCLUÍDA"):
        return "closed"
    if up in ("NO_SHOW", "NOSHOW"):
        return "no_show"

    # fallback seguro
    return "arrival"


def _to_utc_aware(dt):
    """
    Converte datetime do pandas em datetime aware UTC.
    - Se vier tz-aware, converte pra UTC.
    - Se vier naive, assume UTC.
    - Se vier string com 'BRT' (não reconhecida), remove e assume UTC.
    """
    if dt is None or pd.isna(dt):
        return None

    # trata strings com timezone "BRT" (pandas warning)
    if isinstance(dt, str) and "BRT" in dt.upper():
        dt = dt.upper().replace(" BRT", "").strip()

    try:
        d = pd.to_datetime(dt, errors="coerce")
    except Exception:
        return None

    if pd.isna(d):
        return None

    # d pode ser Timestamp tz-aware
    try:
        if getattr(d, "tzinfo", None) is not None:
            try:
                d = d.tz_convert("UTC")
            except Exception:
                d = d.tz_localize(None)
    except Exception:
        pass

    py = d.to_pydatetime()

    if py.tzinfo is None:
        py = py.replace(tzinfo=timezone.utc)
    else:
        py = py.astimezone(timezone.utc)

    return py


@upload_bp.route("/processar", methods=["POST"])
def processar_planilha():
    file = request.files.get("file")
    if not file:
        return jsonify({"message": "Nenhum arquivo enviado."}), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return jsonify({"message": f"Erro ao ler arquivo Excel: {str(e)}"}), 400

    inseridas = 0
    ignoradas = 0
    objetos = []
    agora = datetime.now(timezone.utc)

    for _, row in df.iterrows():
        try:
            # Appointment ID (coluna A)
            appointment_id = row.iloc[0] if len(row) > 0 else None
            if appointment_id is None or pd.isna(appointment_id):
                ignoradas += 1
                continue
            appointment_id = str(appointment_id).strip()

            # Type (coluna B)
            type_raw = row.iloc[1] if len(row) > 1 else None
            truck_type, truck_tipo = _normalize_type(type_raw)

            # Units
            units_raw = _get_col(row, "Units", "UNITS", "units", default=0)
            try:
                if pd.isna(units_raw) or float(units_raw) == 0:
                    ignoradas += 1
                    continue
                units = int(float(units_raw))
            except Exception:
                ignoradas += 1
                continue

            # Datas
            expected_arrival = _to_utc_aware(_get_col(row, "Expected Arrival Date", default=None))
            priority_last_update = _to_utc_aware(_get_col(row, "Priority Score Last Updated Date", default=None))
            if not expected_arrival or not priority_last_update:
                ignoradas += 1
                continue

            # Status (se existir na planilha)
            # Ajuste os nomes se sua planilha usar outro cabeçalho.
            status_raw = _get_col(row, "Status", "STATUS", "Appointment Status", "APPOINTMENT STATUS", default="ARRIVAL")
            status = _normalize_status(status_raw)

            # Outros campos
            priority_score_raw = _get_col(row, "Priority Score", default=0) or 0
            cartons_raw = _get_col(row, "Cartons", default=0) or 0

            try:
                priority_score = float(priority_score_raw)
            except Exception:
                priority_score = 0.0

            try:
                cartons = int(float(cartons_raw))
            except Exception:
                cartons = 0

            prioridade_maxima = priority_last_update < expected_arrival

            # ✅ IMPORTANTE:
            # - Se vier arrival_scheduled, NÃO inicia arrived_at/deadline aqui.
            # - Só inicia quando clicar "CARGA CHEGOU".
            objetos.append(
                Carga(
                    appointment_id=appointment_id,
                    expected_arrival_date=expected_arrival,
                    priority_score=priority_score,
                    priority_last_update=priority_last_update,
                    status=status,
                    cartons=cartons,
                    units=units,

                    truck_type=truck_type,
                    truck_tipo=truck_tipo,

                    aa_responsavel=None,
                    start_time=None,
                    end_time=None,
                    tempo_total_segundos=None,
                    units_por_hora=None,
                    prioridade_maxima=prioridade_maxima,
                    created_at=agora,

                    # campos novos (se existirem no model)
                    arrived_at=None,
                    sla_setar_aa_deadline=None,
                    atraso_segundos=0,
                    atraso_registrado=False,
                )
            )
            inseridas += 1

        except Exception:
            current_app.logger.exception("Erro ao processar linha do upload")
            ignoradas += 1

    if objetos:
        # evita erro caso tenha appointment_id repetido (UNIQUE) -> grava um por um
        # (bulk_save_objects explode e aborta tudo)
        salvas = 0
        for obj in objetos:
            try:
                db.session.add(obj)
                db.session.flush()
                salvas += 1
            except Exception:
                db.session.rollback()
                ignoradas += 1
        db.session.commit()
        inseridas = salvas

    return jsonify(
        {
            "message": "Upload concluído com sucesso!",
            "inseridas": inseridas,
            "ignoradas": ignoradas,
        }
    )