from flask import Blueprint, render_template, request, jsonify
import pandas as pd
from datetime import datetime, timezone, timedelta
import re

from db import db
from models import Carga

upload_bp = Blueprint("upload", __name__, url_prefix="/upload")


@upload_bp.route("/")
def upload_page():
    return render_template("upload.html")


def _get_col(row, *names, default=None):
    """Pega coluna por nome (case-insensitive)."""
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


def _strip_tz(dt):
    """Remove ' BRT' e similares no final (evita NaT / warnings)."""
    if dt is None or (isinstance(dt, float) and pd.isna(dt)) or pd.isna(dt):
        return None
    s = str(dt).strip()
    if not s:
        return None
    # remove timezone textual no fim: " ... BRT"
    s = re.sub(r"\s+[A-Za-z]{2,5}$", "", s)
    return s


def _to_utc_aware(dt):
    """Converte para datetime timezone-aware em UTC."""
    dt = _strip_tz(dt)
    if dt is None:
        return None

    d = pd.to_datetime(dt, errors="coerce")
    if pd.isna(d):
        return None

    py = d.to_pydatetime()
    if py.tzinfo is None:
        py = py.replace(tzinfo=timezone.utc)
    else:
        py = py.astimezone(timezone.utc)

    return py


def _normalize_type(raw):
    """
    Coluna B (Type):
      - OTHER / CARP => VDD
      - TRANSSHIP => Transferência
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or pd.isna(raw):
        return None, None

    s = str(raw).strip().upper()
    if not s:
        return None, None

    # corrige erros comuns / variações
    s = (
        s.replace("TRASNSSHIP", "TRANSSHIP")
         .replace("TRANS SHIP", "TRANSSHIP")
         .replace("TRANS-SHIP", "TRANSSHIP")
    )

    # alguns exports aparecem truncados visualmente (ex: "TRANSSHI")
    if s.startswith("TRANSS"):
        s = "TRANSSHIP"

    if s in ("OTHER", "CARP"):
        return s, "VDD"

    if s == "TRANSSHIP":
        return s, "Transferência"

    return s, None  # desconhecido


def _normalize_status(raw):
    """
    Status da planilha -> status do sistema
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or pd.isna(raw):
        return "arrival"  # fallback

    s = str(raw).strip().upper()
    s = s.replace("-", "_").replace(" ", "_")

    if s in ("ARRIVAL_SCHEDULED",):
        return "arrival_scheduled"

    if s in ("ARRIVED", "ARRIVAL"):
        return "arrival"

    if s in ("CHECKIN", "CHECKED_IN"):
        return "checkin"

    if s in ("CHECKIN_SCHEDULED",):
        return "checkin_scheduled"

    if s in ("NO_SHOW", "NOSHOW"):
        return "no_show"

    # fallback seguro
    return "arrival"


@upload_bp.route("/processar", methods=["POST"])
def processar_planilha():
    file = request.files.get("file")
    if not file:
        return jsonify({"message": "Nenhum arquivo enviado.", "inseridas": 0, "ignoradas": 0}), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return jsonify({"message": f"Erro ao ler arquivo Excel: {str(e)}", "inseridas": 0, "ignoradas": 0}), 400

    inseridas = 0
    ignoradas = 0
    atualizadas = 0
    erros = []

    agora = datetime.now(timezone.utc)

    for idx, row in df.iterrows():
        try:
            # A = Appointment / B = Type (garante 100% mesmo se header mudar)
            appointment_id = row.iloc[0] if len(row) > 0 else None
            if appointment_id is None or pd.isna(appointment_id):
                ignoradas += 1
                continue

            type_raw = row.iloc[1] if len(row) > 1 else None
            truck_type, truck_tipo = _normalize_type(type_raw)

            # Units (pelo nome)
            units_raw = _get_col(row, "Units", "UNITS", "units", default=0)
            try:
                units_val = 0 if pd.isna(units_raw) else int(float(units_raw))
            except Exception:
                units_val = 0

            # Datas
            expected_arrival = _to_utc_aware(_get_col(row, "Expected Arrival Date", default=None))
            priority_last_update = _to_utc_aware(_get_col(row, "Priority Score Last Updated Date", default=None))

            # Se não tiver expected_arrival, não dá pra controlar SLA/status
            if not expected_arrival:
                ignoradas += 1
                continue

            # Priority Score
            priority_score_raw = _get_col(row, "Priority Score", default=0) or 0
            try:
                priority_score = float(priority_score_raw)
            except Exception:
                priority_score = 0.0

            # Cartons
            cartons_raw = _get_col(row, "Cartons", default=0) or 0
            try:
                cartons = int(float(cartons_raw))
            except Exception:
                cartons = 0

            # Status vindo da planilha
            plan_status = _get_col(row, "Status", "STATUS", default=None)
            status = _normalize_status(plan_status)

            # Regra: ARRIVAL_SCHEDULED passou 24h do expected_arrival -> no_show
            if status == "arrival_scheduled":
                if agora > (expected_arrival + timedelta(hours=24)):
                    status = "no_show"

            # prioridade_maxima (só se tiver priority_last_update)
            prioridade_maxima = False
            if priority_last_update:
                prioridade_maxima = priority_last_update < expected_arrival

            # ❗ Regra de ignorar:
            # Se Units == 0 e não for um caso que você queira manter no painel, ignora.
            # (Se você quiser que tudo suba mesmo com Units 0, eu removo essa regra.)
            if units_val <= 0:
                ignoradas += 1
                continue

            appointment_str = str(appointment_id).strip()

            # UPSERT simples (não duplica)
            carga = Carga.query.filter_by(appointment_id=appointment_str).first()
            if carga:
                # atualiza
                carga.expected_arrival_date = expected_arrival
                carga.priority_last_update = priority_last_update
                carga.priority_score = priority_score
                carga.prioridade_maxima = prioridade_maxima
                carga.status = status
                carga.cartons = cartons
                carga.units = units_val
                carga.truck_type = truck_type
                carga.truck_tipo = truck_tipo
                atualizadas += 1
            else:
                # cria
                carga = Carga(
                    appointment_id=appointment_str,
                    expected_arrival_date=expected_arrival,
                    priority_last_update=priority_last_update,
                    priority_score=priority_score,
                    prioridade_maxima=prioridade_maxima,
                    status=status,
                    cartons=cartons,
                    units=units_val,
                    truck_type=truck_type,
                    truck_tipo=truck_tipo,
                    aa_responsavel=None,
                    start_time=None,
                    end_time=None,
                    tempo_total_segundos=None,
                    units_por_hora=None,
                    created_at=agora,
                )
                db.session.add(carga)
                inseridas += 1

        except Exception as e:
            ignoradas += 1
            erros.append(f"Linha {idx+2}: {str(e)}")  # +2 por causa do header

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "message": f"Erro ao salvar no banco: {str(e)}",
            "inseridas": 0,
            "atualizadas": 0,
            "ignoradas": len(df),
            "erros": erros[:20],
        }), 500

    return jsonify({
        "message": "Upload concluído com sucesso!",
        "inseridas": inseridas,
        "atualizadas": atualizadas,
        "ignoradas": ignoradas,
        "erros": erros[:20],
    }), 200