from flask import Blueprint, render_template, jsonify, request
from firebase_config import db
from datetime import datetime, timedelta, timezone

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("/")
def dashboard_page():
    return render_template("dashboard.html")

@dashboard_bp.route("/stats")
def dashboard_stats():

    data_inicio = request.args.get("dataInicio")
    data_fim = request.args.get("dataFim")

    if not data_inicio or not data_fim:
        return jsonify({})

    inicio = datetime.fromisoformat(data_inicio).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )

    fim = datetime.fromisoformat(data_fim).replace(
        hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
    )

    cargas_ref = db.collection("cargas").stream()

    total_units = 0
    total_notas_fechadas = 0
    total_notas_pendentes = 0

    unidades_por_dia = {}
    notas_por_dia = {}
    por_login = {}

    for doc in cargas_ref:
        carga = doc.to_dict()

        status = carga.get("status")
        end_time = carga.get("end_time")
        created_at = carga.get("created_at")
        units = carga.get("units", 0)
        login = carga.get("aa_responsavel")

        # 🔹 FECHADAS
        if status == "closed" and isinstance(end_time, datetime):

            if inicio <= end_time <= fim:

                total_notas_fechadas += 1
                total_units += units

                dia = end_time.date().isoformat()

                # Units por dia
                unidades_por_dia[dia] = unidades_por_dia.get(dia, 0) + units

                # Notas por dia
                notas_por_dia[dia] = notas_por_dia.get(dia, 0) + 1

                # Por login
                if login:
                    if login not in por_login:
                        por_login[login] = {"units": 0, "notas": 0}

                    por_login[login]["units"] += units
                    por_login[login]["notas"] += 1

        # 🔹 PENDENTES
        elif status != "closed" and isinstance(created_at, datetime):

            if inicio <= created_at <= fim:
                total_notas_pendentes += 1

    return jsonify({
        "total_units": total_units,
        "total_notas_fechadas": total_notas_fechadas,
        "total_notas_pendentes": total_notas_pendentes,
        "unidades_por_dia": unidades_por_dia,
        "notas_por_dia": notas_por_dia,
        "por_login": por_login
    })

