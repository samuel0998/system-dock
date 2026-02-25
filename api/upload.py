from flask import Blueprint, render_template, request, jsonify
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
    # tenta match direto (como veio no excel)
    for n in names:
        if n in row and pd.notna(row.get(n)):
            return row.get(n)

    # tenta match case-insensitive (pandas às vezes muda nomes)
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

    # normaliza erros comuns
    up = (
        up.replace("TRASNSSHIP", "TRANSSHIP")
          .replace("TRANS SHIP", "TRANSSHIP")
          .replace("TRANS-SHIP", "TRANSSHIP")
    )

    if up in ("OTHER", "CARP"):
        return up, "VDD"
    if up == "TRANSSHIP":
        return up, "Transferência"

    # desconhecido: salva raw e deixa tipo normalizado vazio
    return up, None


def _to_utc_aware(dt):
    """
    Converte datetime do pandas em datetime aware UTC.
    Se vier naive, assume UTC.
    """
    if dt is None or pd.isna(dt):
        return None
    try:
        d = pd.to_datetime(dt, errors="coerce")
    except Exception:
        return None

    if pd.isna(d):
        return None

    # se vier tz-aware, converte pra UTC
    if getattr(d, "tzinfo", None) is not None:
        try:
            d = d.tz_convert("UTC")
        except Exception:
            # algumas strings tz quebradas: remove tz e assume UTC
            d = d.tz_localize(None)

    py = d.to_pydatetime()

    # garante tzinfo UTC
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

        # Appointment ID (coluna A)
        appointment_id = row.iloc[0] if len(row) > 0 else None
        if pd.isna(appointment_id):
            ignoradas += 1
            continue

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

        objetos.append(
            Carga(
                appointment_id=str(appointment_id),
                expected_arrival_date=expected_arrival,
                priority_score=priority_score,
                priority_last_update=priority_last_update,
                status="arrival",
                cartons=cartons,
                units=units,

                # ✅ NOVO
                truck_type=truck_type,
                truck_tipo=truck_tipo,

                aa_responsavel=None,
                start_time=None,
                end_time=None,
                tempo_total_segundos=None,
                units_por_hora=None,
                prioridade_maxima=prioridade_maxima,
                created_at=agora,
            )
        )
        inseridas += 1

    if objetos:
        db.session.bulk_save_objects(objetos)
        db.session.commit()

    return jsonify(
        {
            "message": "Upload concluído com sucesso!",
            "inseridas": inseridas,
            "ignoradas": ignoradas,
        }
    )