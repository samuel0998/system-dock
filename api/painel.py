from flask import Blueprint, jsonify, request, render_template, current_app
from datetime import datetime, timezone, timedelta

from sqlalchemy import text

from db import db
from models import Carga, Operador  # Operador deve mapear a tabela "operadores"

painel_bp = Blueprint("painel", __name__, url_prefix="/pc")


# =========================
# Helpers
# =========================
def to_aware_utc(dt: datetime | None) -> datetime | None:
    """Garante datetime timezone-aware em UTC para evitar erro naive vs aware."""
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# =========================
# Pages
# =========================
@painel_bp.route("/rate")
def rate_page():
    return render_template("rate.html")


@painel_bp.route("/")
def painel_page():
    return render_template("pc.html")


# =========================
# Cargas
# =========================
@painel_bp.route("/listar")
def listar_cargas():
    try:
        agora = datetime.now(timezone.utc)

        cargas = Carga.query.order_by(Carga.expected_arrival_date.asc()).all()
        lista = []

        for c in cargas:
            expected = to_aware_utc(c.expected_arrival_date)

            # regra no-show automático (24h depois do Expected Arrival)
            if c.status == "arrival" and expected:
                limite_no_show = expected + timedelta(hours=24)
                if agora > limite_no_show:
                    c.status = "no_show"

            lista.append({
                "id": c.id,
                "appointment_id": c.appointment_id,
                "expected_arrival_date": expected.isoformat() if expected else None,
                "units": c.units or 0,
                "cartons": c.cartons or 0,
                "status": c.status,
                "aa_responsavel": c.aa_responsavel,
                "priority_score": c.priority_score or 0,
                "start_time": to_aware_utc(c.start_time).isoformat() if c.start_time else None,
                "tempo_total_segundos": c.tempo_total_segundos
            })

        db.session.commit()
        return jsonify(lista)

    except Exception:
        current_app.logger.exception("Erro em /pc/listar")
        return jsonify([]), 200


@painel_bp.route("/checkin/<int:carga_id>", methods=["POST"])
def checkin(carga_id):
    try:
        data = request.get_json(silent=True) or {}
        aa_login = data.get("aa_responsavel") or data.get("login") or data.get("aa_login")

        if not aa_login:
            return jsonify({"error": "AA não informado"}), 400

        carga = Carga.query.get(carga_id)
        if not carga:
            return jsonify({"error": "Carga não encontrada"}), 404

        carga.status = "checkin"
        carga.aa_responsavel = aa_login
        carga.start_time = datetime.now(timezone.utc)

        db.session.commit()
        return jsonify({"message": "Checkin realizado"})

    except Exception:
        current_app.logger.exception("Erro em /pc/checkin")
        return jsonify({"error": "Erro interno"}), 500


@painel_bp.route("/finalizar/<int:carga_id>", methods=["POST"])
def finalizar(carga_id):
    try:
        carga = Carga.query.get(carga_id)
        if not carga:
            return jsonify({"error": "Carga não encontrada"}), 404

        start_time = to_aware_utc(carga.start_time)
        if not start_time:
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

    except Exception:
        current_app.logger.exception("Erro em /pc/finalizar")
        return jsonify({"error": "Erro interno"}), 500


@painel_bp.route("/limpar-banco", methods=["DELETE"])
def limpar_banco():
    try:
        deletadas = db.session.query(Carga).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"message": "Banco limpo com sucesso", "deletadas": int(deletadas or 0)})

    except Exception:
        current_app.logger.exception("Erro em /pc/limpar-banco")
        return jsonify({"error": "Erro interno"}), 500


@painel_bp.route("/deletar/<int:carga_id>", methods=["POST"])
def deletar_carga(carga_id):
    try:
        data = request.get_json(silent=True) or {}
        motivo = (data.get("motivo") or "").strip()

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

    except Exception:
        current_app.logger.exception("Erro em /pc/deletar")
        return jsonify({"error": "Erro interno"}), 500


# =========================
# AAs disponíveis (LÓGICA CORRETA)
# =========================
from flask import jsonify, current_app
from sqlalchemy import text

@painel_bp.route("/aa-disponiveis")
def aa_disponiveis():
    """
    AA aparece no Setar AA se:

    1) cargo = 'AA'
    2) não estiver falta / emprestado / treinamento
    3) (operadores.processo = 'DOCA IN')
       OU
       (existe movimento ativo com destino DOCA IN)
    """

    try:
        query = text("""
            SELECT DISTINCT
                o.login,
                o.nome,
                o.tag AS badge,
                o.setor,
                o.turno
            FROM operadores o
            LEFT JOIN movimentos m
                ON m.badge = o.tag
            WHERE o.cargo = 'AA'
              AND COALESCE(o.falta, false) = false
              AND COALESCE(o.emprestado, false) = false
              AND COALESCE(o.treinamento, false) = false
              AND (
                    UPPER(COALESCE(o.processo,'')) = 'DOCA IN'
                 OR (
                        UPPER(COALESCE(m.processo_destino,'')) = 'DOCA IN'
                    AND LOWER(COALESCE(m.status,'')) = 'ativo'
                    )
                  )
            ORDER BY o.nome;
        """)

        result = db.session.execute(query).mappings().all()

        lista = [
            {
                "login": r["login"],
                "nome": r["nome"],
                "badge": r["badge"],
                "setor": r["setor"],
                "turno": r["turno"],
            }
            for r in result
        ]

        return jsonify(lista)

    except Exception:
        current_app.logger.exception("Erro em /pc/aa-disponiveis")
        return jsonify([]), 200