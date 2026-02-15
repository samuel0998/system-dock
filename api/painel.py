from flask import Blueprint, jsonify, request, render_template
from firebase_config import db
from datetime import datetime, timezone

painel_bp = Blueprint("painel", __name__, url_prefix="/pc")


@painel_bp.route("/")
def painel_page():
    return render_template("pc.html")


@painel_bp.route("/listar", methods=["GET"])
def listar_cargas():

    cargas_ref = db.collection("cargas").stream()
    lista = []

    for doc in cargas_ref:

        data = doc.to_dict() or {}

        lista.append({
            "tempo_total_segundos": data.get("tempo_total_segundos"),
            "start_time": data.get("start_time").isoformat()
                if isinstance(data.get("start_time"), datetime)
                else None,
            "id": doc.id,
            "appointment_id": data.get("appointment_id"),
            "expected_arrival_date": data.get("expected_arrival_date").isoformat()
                if isinstance(data.get("expected_arrival_date"), datetime)
                else None,
            "units": data.get("units", 0),
            "cartons": data.get("cartons", 0),
            "status": data.get("status"),
            "aa_responsavel": data.get("aa_responsavel"),
            "priority_score": data.get("priority_score", 0)
            
        })

    return jsonify(lista)



@painel_bp.route("/checkin/<carga_id>", methods=["POST"])
def checkin(carga_id):

    dados = request.get_json()

    if not dados or not dados.get("aa_responsavel"):
        return jsonify({"error": "AA não informado"}), 400

    db.collection("cargas").document(carga_id).update({
        "status": "checkin",
        "aa_responsavel": dados.get("aa_responsavel"),
        "start_time": datetime.now(timezone.utc)
    })

    return jsonify({"message": "Checkin realizado"})


@painel_bp.route("/finalizar/<carga_id>", methods=["POST"])
def finalizar(carga_id):

    carga_ref = db.collection("cargas").document(carga_id)
    carga = carga_ref.get().to_dict()

    start_time = carga.get("start_time")

    if not isinstance(start_time, datetime):
        return jsonify({"error": "Carga não iniciada"}), 400

    end_time = datetime.now(timezone.utc)

    tempo_total_segundos = int((end_time - start_time).total_seconds())
    units = carga.get("units", 0)

    tempo_total_horas = tempo_total_segundos / 3600
    units_por_hora = round(units / tempo_total_horas, 2) if tempo_total_horas > 0 else 0

    carga_ref.update({
        "status": "closed",
        "end_time": end_time,
        "tempo_total_segundos": tempo_total_segundos,
        "units_por_hora": units_por_hora
    })

    return jsonify({"message": "Carga finalizada"})
@painel_bp.route("/limpar-banco", methods=["DELETE"])
def limpar_banco():

    cargas_ref = db.collection("cargas").stream()

    deletadas = 0

    for doc in cargas_ref:
        db.collection("cargas").document(doc.id).delete()
        deletadas += 1

    return jsonify({
        "message": "Banco limpo com sucesso",
        "deletadas": deletadas
    })
