from flask import Blueprint, jsonify, request, render_template
from datetime import datetime, timezone, timedelta

from db import db
from models import Carga, Operador

painel_bp = Blueprint("painel", __name__, url_prefix="/pc")


@painel_bp.route("/rate")
def rate_page():
    return render_template("rate.html")


@painel_bp.route("/")
def painel_page():
    return render_template("pc.html")


@painel_bp.route("/listar")
def listar_cargas():
    agora = datetime.now(timezone.utc)

    cargas = Carga.query.order_by(Carga.expected_arrival_date.asc()).all()
    lista = []

    for c in cargas:
        # regra no-show automático
        if c.status == "arrival" and isinstance(c.expected_arrival_date, datetime):
            limite_no_show = c.expected_arrival_date + timedelta(hours=24)
            if agora > limite_no_show:
                c.status = "no_show"

        lista.append({
            "id": c.id,
            "appointment_id": c.appointment_id,
            "expected_arrival_date": c.expected_arrival_date.isoformat() if c.expected_arrival_date else None,
            "units": c.units or 0,
            "cartons": c.cartons or 0,
            "status": c.status,
            "aa_responsavel": c.aa_responsavel,
            "priority_score": c.priority_score or 0,
            "start_time": c.start_time.isoformat() if c.start_time else None,
            "tempo_total_segundos": c.tempo_total_segundos
        })

    db.session.commit()  # salva eventuais no_show
    return jsonify(lista)


@painel_bp.route("/checkin/<int:carga_id>", methods=["POST"])
def checkin(carga_id):
    dados = request.get_json()

    if not dados or not dados.get("aa_responsavel"):
        return jsonify({"error": "AA não informado"}), 400

    carga = Carga.query.get(carga_id)
    if not carga:
        return jsonify({"error": "Carga não encontrada"}), 404

    carga.status = "checkin"
    carga.aa_responsavel = dados.get("aa_responsavel")
    carga.start_time = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify({"message": "Checkin realizado"})


@painel_bp.route("/finalizar/<int:carga_id>", methods=["POST"])
def finalizar(carga_id):
    carga = Carga.query.get(carga_id)
    if not carga:
        return jsonify({"error": "Carga não encontrada"}), 404

    start_time = carga.start_time
    if not isinstance(start_time, datetime):
        return jsonify({"error": "Carga não iniciada"}), 400

    end_time = datetime.now(timezone.utc)

    tempo_total_segundos = int((end_time - start_time).total_seconds())
    units = carga.units or 0

    tempo_total_horas = tempo_total_segundos / 3600
    units_por_hora = round(units / tempo_total_horas, 2) if tempo_total_horas > 0 else 0

    carga.status = "closed"
    carga.end_time = end_time
    carga.tempo_total_segundos = tempo_total_segundos
    carga.units_por_hora = units_por_hora

    db.session.commit()
    return jsonify({"message": "Carga finalizada"})


@painel_bp.route("/limpar-banco", methods=["DELETE"])
def limpar_banco():
    # apaga tudo da tabela cargas
    deletadas = db.session.query(Carga).delete(synchronize_session=False)
    db.session.commit()

    return jsonify({
        "message": "Banco limpo com sucesso",
        "deletadas": int(deletadas or 0)
    })


@painel_bp.route("/deletar/<int:carga_id>", methods=["POST"])
def deletar_carga(carga_id):
    data = request.get_json() or {}
    motivo = data.get("motivo")

    if not motivo:
        return jsonify({"error": "Motivo é obrigatório"}), 400

    carga = Carga.query.get(carga_id)
    if not carga:
        return jsonify({"error": "Carga não encontrada"}), 404

    carga.status = "deleted"
    carga.delete_reason = motivo
    carga.deleted_at = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify({"message": "Carga marcada como deletada"})


@painel_bp.route("/aa-disponiveis")
def aa_disponiveis():
    operadores = (
        Operador.query
        .filter(Operador.processo_atual == "DOCA IN")
        .all()
    )

    lista = []
    for op in operadores:
        if op.falta:
            continue

        lista.append({
            "login": op.login,
            "nome": op.nome,
            "badge": op.badge,
            "emprestado": bool(op.emprestado)
        })

    return jsonify(lista)