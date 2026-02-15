from flask import Blueprint, render_template, request, jsonify
from firebase_config import db
import pandas as pd
from datetime import datetime, timezone

upload_bp = Blueprint("upload", __name__, url_prefix="/upload")


@upload_bp.route("/")
def upload_page():
    return render_template("upload.html")


@upload_bp.route("/processar", methods=["POST"])
def processar_planilha():

    file = request.files.get("file")

    if not file:
        return jsonify({"message": "Nenhum arquivo enviado."}), 400

    df = pd.read_excel(file)

    inseridas = 0
    ignoradas = 0

    for _, row in df.iterrows():

        units = row.get("Units", 0)

        # 🔴 Ignorar units = 0
        if pd.isna(units) or float(units) == 0:
            ignoradas += 1
            continue

        # 🔹 Appointment ID (primeira coluna da planilha)
        appointment_id = row.iloc[0]

        # 🔹 Datas
        expected_arrival = pd.to_datetime(row.get("Expected Arrival Date"), errors="coerce")
        priority_last_update = pd.to_datetime(row.get("Priority Score Last Updated Date"), errors="coerce")

        if pd.isna(expected_arrival) or pd.isna(priority_last_update):
            ignoradas += 1
            continue

        expected_arrival = expected_arrival.to_pydatetime().replace(tzinfo=timezone.utc)
        priority_last_update = priority_last_update.to_pydatetime().replace(tzinfo=timezone.utc)

        priority_score = float(row.get("Priority Score", 0))
        cartons = int(row.get("Cartons", 0))

        # 🔴 Regra prioridade máxima
        prioridade_maxima = priority_last_update < expected_arrival

        carga_data = {
            "appointment_id": str(appointment_id),
            "expected_arrival_date": expected_arrival,
            "priority_score": priority_score,
            "priority_last_update": priority_last_update,
            "status": "arrival",
            "cartons": cartons,
            "units": int(units),
            "aa_responsavel": None,
            "start_time": None,
            "end_time": None,
            "tempo_total_horas": None,
            "units_por_hora": None,
            "prioridade_maxima": prioridade_maxima,
            "created_at": datetime.now(timezone.utc)
        }

        db.collection("cargas").add(carga_data)
        inseridas += 1

    return jsonify({
        "message": "Upload concluído com sucesso!",
        "inseridas": inseridas,
        "ignoradas": ignoradas
    })
