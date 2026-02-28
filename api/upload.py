from flask import Blueprint, render_template, request, jsonify
import pandas as pd
from datetime import datetime, timezone

from db import db
from models import Carga

upload_bp = Blueprint("upload", __name__, url_prefix="/upload")


@upload_bp.route("/")
def upload_page():
    return render_template("upload.html")


def _norm(s: str) -> str:
    """Normaliza nome de coluna: lower, remove espaços/underscore/traços."""
    return (
        str(s)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
    )


def _build_colmap(df: pd.DataFrame) -> dict:
    """Mapeia nome normalizado -> nome real."""
    return {_norm(c): c for c in df.columns}


def _get(row, colmap, *names, default=None):
    """
    Pega valor de uma coluna por vários nomes possíveis (normalizados).
    """
    for n in names:
        key = _norm(n)
        real = colmap.get(key)
        if real is not None:
            val = row.get(real)
            if pd.notna(val):
                return val
    return default


def _to_utc_aware(dt):
    if dt is None or pd.isna(dt):
        return None
    d = pd.to_datetime(dt, errors="coerce")
    if pd.isna(d):
        return None

    # Se vier com tz, converte; se vier "BRT" (bagunçado), remove tz
    try:
        if getattr(d, "tzinfo", None) is not None:
            d = d.tz_convert("UTC")
    except Exception:
        try:
            d = d.tz_localize(None)
        except Exception:
            pass

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


def _normalize_status(raw):
    """
    Status vindo da planilha:
    ARRIVAL_SCHEDULED, ARRIVED, CHECKIN_SCHEDULED, CHECKIN, CLOSED, NO_SHOW...
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None

    s = str(raw).strip().upper()
    if not s:
        return None

    # normalizações
    if s == "ARRIVED":
        return "ARRIVAL"
    if s == "NO SHOW":
        return "NO_SHOW"

    return s


@upload_bp.route("/processar", methods=["POST"])
def processar_planilha():
    file = request.files.get("file")
    if not file:
        return jsonify({"message": "Nenhum arquivo enviado."}), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return jsonify({"message": f"Erro ao ler arquivo Excel: {str(e)}"}), 400

    # DEBUG (vai aparecer no log do Railway)
    print("📌 COLUNAS DO EXCEL:", list(df.columns))

    colmap = _build_colmap(df)

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

        # Status (procura por nome, e se não achar tenta por posições comuns)
        status_raw = _get(row, colmap, "Status", "STATUS", default=None)
        if status_raw is None and len(row) > 7:
            # fallback (se sua planilha tiver status perto do fim)
            status_raw = row.iloc[7]
        status_planilha = _normalize_status(status_raw)
        if not status_planilha:
            ignoradas += 1
            continue

        # Units (nome + fallback por posição)
        units_raw = _get(row, colmap, "Units", "UNITS", "Total Units", "TotalUnits", default=None)
        if units_raw is None and len(row) > 8:
            units_raw = row.iloc[8]  # fallback: ajuste se necessário
        if units_raw is None or pd.isna(units_raw):
            ignoradas += 1
            continue

        try:
            units = int(float(units_raw))
        except Exception:
            ignoradas += 1
            continue

        # Cartons (nome + fallback por posição)
        cartons_raw = _get(row, colmap, "Cartons", "CARTONS", default=None)
        if cartons_raw is None and len(row) > 9:
            cartons_raw = row.iloc[9]
        try:
            cartons = int(float(cartons_raw)) if cartons_raw is not None and pd.notna(cartons_raw) else 0
        except Exception:
            cartons = 0

        # Datas
        expected_arrival = _to_utc_aware(_get(row, colmap, "Expected Arrival Date", default=None))
        priority_last_update = _to_utc_aware(_get(row, colmap, "Priority Score Last Updated Date", default=None))

        if not expected_arrival or not priority_last_update:
            ignoradas += 1
            continue

        # Priority Score
        priority_score_raw = _get(row, colmap, "Priority Score", default=0) or 0
        try:
            priority_score = float(priority_score_raw)
        except Exception:
            priority_score = 0.0

        prioridade_maxima = priority_last_update < expected_arrival

        objetos.append(
            Carga(
                appointment_id=str(appointment_id),
                expected_arrival_date=expected_arrival,
                priority_score=priority_score,
                priority_last_update=priority_last_update,
                status=status_planilha,  # ✅ salva o status REAL da planilha
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
            )
        )
        inseridas += 1

    if objetos:
        db.session.bulk_save_objects(objetos)
        db.session.commit()

    return jsonify({
        "message": "Upload concluído com sucesso!",
        "inseridas": inseridas,
        "ignoradas": ignoradas,
    })