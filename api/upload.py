from flask import Blueprint, render_template, request, jsonify
import pandas as pd
from datetime import datetime, timezone, timedelta
import re
from flask import current_app 

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


def _status_sistema_from_planilha(raw):
    """
    REGRA DO SISTEMA:
    - ARRIVAL_SCHEDULED -> arrival_scheduled
    - CLOSED -> IGNORA (retorna None)
    - QUALQUER OUTRO (exceto CLOSED) -> arrival
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or pd.isna(raw):
        # se não veio status, assume arrival
        return "arrival"

    s = str(raw).strip().upper().replace("-", "_").replace(" ", "_")

    if s == "ARRIVAL_SCHEDULED":
        return "arrival_scheduled"

    if s == "CLOSED":
        return None  # ignora

    # todo resto vira ARRIVAL
    return "arrival"


@upload_bp.route("/processar", methods=["POST"])
def processar_planilha():
    file = request.files.get("file")
    if not file:
        return jsonify({
            "message": "Nenhum arquivo enviado.",
            "inseridas": 0,
            "atualizadas": 0,
            "ignoradas": 0,
            "erros": []
        }), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return jsonify({
            "message": f"Erro ao ler arquivo Excel: {str(e)}",
            "inseridas": 0,
            "atualizadas": 0,
            "ignoradas": 0,
            "erros": []
        }), 400

    inseridas = 0
    atualizadas = 0
    ignoradas = 0
    erros = []

    agora = datetime.now(timezone.utc)

    def _safe_str(x):
        if x is None or (isinstance(x, float) and pd.isna(x)) or pd.isna(x):
            return ""
        return str(x).strip()

    def _to_utc(dt):
        """
        Converte datas, removendo 'BRT'/'BRST' se vier na string.
        """
        if dt is None or (isinstance(dt, float) and pd.isna(dt)) or pd.isna(dt):
            return None

        s = _safe_str(dt)
        if s:
            s = s.replace(" BRT", "").replace(" BRST", "")

        try:
            d = pd.to_datetime(s if s else dt, errors="coerce")
        except Exception:
            return None

        if pd.isna(d):
            return None

        # se vier tz-aware, converte pra UTC; se vier naive, assume UTC
        if getattr(d, "tzinfo", None) is not None:
            try:
                d = d.tz_convert("UTC")
            except Exception:
                d = d.tz_localize(None)

        py = d.to_pydatetime()
        if py.tzinfo is None:
            py = py.replace(tzinfo=timezone.utc)
        else:
            py = py.astimezone(timezone.utc)

        return py

    def _status_sistema(plan_status_raw):
        """
        REGRA DO SISTEMA (fixa):
        - ARRIVAL_SCHEDULED -> arrival_scheduled
        - CLOSED -> ignora (None)
        - qualquer outro status -> arrival
        """
        s = _safe_str(plan_status_raw).upper().replace("-", "_").replace(" ", "_")

        if s == "ARRIVAL_SCHEDULED":
            return "arrival_scheduled"
        if s == "CLOSED":
            return None
        return "arrival"

    # Processa linha por linha
    for idx, row in df.iterrows():
        try:
            # A = appointment, B = Type (sempre por posição)
            appointment_id_raw = row.iloc[0] if len(row) > 0 else None
            appointment_str = _safe_str(appointment_id_raw)

            if not appointment_str:
                ignoradas += 1
                continue

            type_raw = row.iloc[1] if len(row) > 1 else None
            truck_type, truck_tipo = _normalize_type(type_raw)

            # Units (pelo nome; se não achar, tenta colunas por posição comuns)
            units_raw = _get_col(row, "Units", "UNITS", "units", default=None)
            if units_raw is None:
                # fallback: algumas exports colocam units em coluna perto do fim
                units_raw = None

            try:
                units_val = 0 if (units_raw is None or pd.isna(units_raw)) else int(float(units_raw))
            except Exception:
                units_val = 0

            # Cartons
            cartons_raw = _get_col(row, "Cartons", "CARTONS", "cartons", default=0)
            try:
                cartons = 0 if pd.isna(cartons_raw) else int(float(cartons_raw))
            except Exception:
                cartons = 0

            # Datas essenciais
            expected_arrival = _to_utc(_get_col(row, "Expected Arrival Date", default=None))
            if not expected_arrival:
                # sem expected não tem como trabalhar SLA/NoShow
                ignoradas += 1
                continue

            priority_last_update = _to_utc(_get_col(row, "Priority Score Last Updated Date", default=None))

            # Priority Score
            priority_score_raw = _get_col(row, "Priority Score", default=0) or 0
            try:
                priority_score = float(priority_score_raw)
            except Exception:
                priority_score = 0.0

            # Status vindo da planilha -> convertido pela REGRA DO SISTEMA
            plan_status = _get_col(row, "Status", "STATUS", default=None)
            status = _status_sistema(plan_status)

            # CLOSED ignora
            if status is None:
                ignoradas += 1
                continue

            # REGRA: arrival_scheduled > 24h do expected => no_show
            if status == "arrival_scheduled" and agora > (expected_arrival + timedelta(hours=24)):
                status = "no_show"

            # prioridade_maxima (só se tiver priority_last_update)
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
                carga.status = status
                carga.cartons = cartons
                carga.units = units_val
                carga.truck_type = truck_type
                carga.truck_tipo = truck_tipo
                atualizadas += 1
            else:
                db.session.add(Carga(
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
                ))
                inseridas += 1

        except Exception as e:
            ignoradas += 1
            erros.append(f"Linha {idx + 2}: {str(e)}")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Erro ao salvar upload no banco")
        return jsonify({
            "message": f"Erro ao salvar no banco: {str(e)}",
            "inseridas": 0,
            "atualizadas": 0,
            "ignoradas": int(len(df)),
            "erros": erros[:30]
        }), 500

    return jsonify({
        "message": "Upload concluído com sucesso!",
        "inseridas": int(inseridas),
        "atualizadas": int(atualizadas),
        "ignoradas": int(ignoradas),
        "erros": erros[:30]
    }), 200