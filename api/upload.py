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
    Pega a primeira coluna existente (case sensitive) dentre as opções.
    Ex: _get_col(row, "Units", "UNITS", "units")
    """
    for n in names:
        if n in row and pd.notna(row.get(n)):
            return row.get(n)
    return default


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

        # Appointment ID (primeira coluna)
        appointment_id = row.iloc[0]
        if pd.isna(appointment_id):
            ignoradas += 1
            continue

        # Datas
        expected_arrival = pd.to_datetime(_get_col(row, "Expected Arrival Date", default=None), errors="coerce")
        priority_last_update = pd.to_datetime(_get_col(row, "Priority Score Last Updated Date", default=None), errors="coerce")

        if pd.isna(expected_arrival) or pd.isna(priority_last_update):
            ignoradas += 1
            continue

        expected_arrival = expected_arrival.to_pydatetime().replace(tzinfo=timezone.utc)
        priority_last_update = priority_last_update.to_pydatetime().replace(tzinfo=timezone.utc)

        # Outros campos
        priority_score = _get_col(row, "Priority Score", default=0) or 0
        cartons_raw = _get_col(row, "Cartons", default=0) or 0

        try:
            priority_score = float(priority_score)
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
                aa_responsavel=None,
                start_time=None,
                end_time=None,
                tempo_total_segundos=None,
                units_por_hora=None,
                prioridade_maxima=prioridade_maxima,
                created_at=agora
            )
        )
        inseridas += 1

    if objetos:
        db.session.bulk_save_objects(objetos)
        db.session.commit()

    return jsonify({
        "message": "Upload concluído com sucesso!",
        "inseridas": inseridas,
        "ignoradas": ignoradas
    })