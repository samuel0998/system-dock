from flask import Blueprint, jsonify, request, render_template, current_app
from datetime import datetime, timedelta

from db import db
from models import Carga  # Operador pode ou não existir no models, por isso não dependo dele aqui
from sqlalchemy import text

painel_bp = Blueprint("painel", __name__, url_prefix="/pc")


# =====================================================
# PÁGINAS
# =====================================================
@painel_bp.route("/rate")
def rate_page():
    return render_template("rate.html")


@painel_bp.route("/")
def painel_page():
    return render_template("pc.html")


# =====================================================
# HELPERS (timezone safe)
# =====================================================
def now_utc_naive():
    # Mantém tudo NAIVE para não estourar comparação com campos sem timezone no banco
    return datetime.utcnow()


def dt_to_iso(dt):
    if not dt:
        return None
    # Se vier aware, converte pra naive UTC
    try:
        if getattr(dt, "tzinfo", None) is not None:
            return dt.astimezone(tz=None).replace(tzinfo=None).isoformat()
    except Exception:
        pass
    return dt.isoformat()


def to_naive(dt):
    if not dt:
        return None
    try:
        if getattr(dt, "tzinfo", None) is not None:
            return dt.replace(tzinfo=None)
    except Exception:
        pass
    return dt


# =====================================================
# LISTAR CARGAS (front depende disso)
# =====================================================
@painel_bp.route("/listar")
def listar_cargas():
    try:
        agora = now_utc_naive()

        cargas = Carga.query.order_by(Carga.expected_arrival_date.asc()).all()
        lista = []
        mudou_status = False

        for c in cargas:
            expected = to_naive(c.expected_arrival_date)

            # No-show automático: arrival + 24h após expected_arrival_date
            if c.status == "arrival" and isinstance(expected, datetime):
                limite_no_show = expected + timedelta(hours=24)
                if agora > limite_no_show:
                    c.status = "no_show"
                    mudou_status = True

            lista.append({
                "id": c.id,
                "appointment_id": c.appointment_id,
                "expected_arrival_date": dt_to_iso(expected),
                "units": int(c.units or 0),
                "cartons": int(c.cartons or 0),
                "status": c.status,
                "aa_responsavel": c.aa_responsavel,
                "priority_score": float(c.priority_score or 0),
                "start_time": dt_to_iso(to_naive(c.start_time)),
                "end_time": dt_to_iso(to_naive(getattr(c, "end_time", None))),
                "tempo_total_segundos": int(c.tempo_total_segundos or 0),
                "units_por_hora": float(getattr(c, "units_por_hora", 0) or 0),
                "delete_reason": getattr(c, "delete_reason", None),
                "deleted_at": dt_to_iso(to_naive(getattr(c, "deleted_at", None))),
            })

        if mudou_status:
            db.session.commit()

        return jsonify(lista), 200

    except Exception:
        current_app.logger.exception("Erro em /pc/listar")
        # Nunca deixa o front “sem nada” por exceção
        return jsonify([]), 200


# =====================================================
# CHECKIN
# =====================================================
@painel_bp.route("/checkin/<int:carga_id>", methods=["POST"])
def checkin(carga_id):
    try:
        dados = request.get_json(silent=True) or {}
        aa = dados.get("aa_responsavel")

        if not aa:
            return jsonify({"error": "AA não informado"}), 400

        carga = Carga.query.get(carga_id)
        if not carga:
            return jsonify({"error": "Carga não encontrada"}), 404

        carga.status = "checkin"
        carga.aa_responsavel = aa
        carga.start_time = now_utc_naive()

        db.session.commit()
        return jsonify({"message": "Checkin realizado"}), 200

    except Exception:
        current_app.logger.exception("Erro em /pc/checkin")
        return jsonify({"error": "Erro interno"}), 500


# =====================================================
# FINALIZAR
# =====================================================
@painel_bp.route("/finalizar/<int:carga_id>", methods=["POST"])
def finalizar(carga_id):
    try:
        carga = Carga.query.get(carga_id)
        if not carga:
            return jsonify({"error": "Carga não encontrada"}), 404

        start_time = to_naive(carga.start_time)
        if not isinstance(start_time, datetime):
            return jsonify({"error": "Carga não iniciada"}), 400

        end_time = now_utc_naive()
        tempo_total_segundos = int((end_time - start_time).total_seconds())

        units = int(carga.units or 0)
        horas = tempo_total_segundos / 3600 if tempo_total_segundos > 0 else 0
        units_por_hora = round(units / horas, 2) if horas > 0 else 0

        carga.status = "closed"
        carga.end_time = end_time
        carga.tempo_total_segundos = tempo_total_segundos
        carga.units_por_hora = units_por_hora

        db.session.commit()
        return jsonify({"message": "Carga finalizada"}), 200

    except Exception:
        current_app.logger.exception("Erro em /pc/finalizar")
        return jsonify({"error": "Erro interno"}), 500


# =====================================================
# LIMPAR BANCO
# =====================================================
@painel_bp.route("/limpar-banco", methods=["DELETE"])
def limpar_banco():
    try:
        deletadas = db.session.query(Carga).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"message": "Banco limpo com sucesso", "deletadas": int(deletadas or 0)}), 200
    except Exception:
        current_app.logger.exception("Erro em /pc/limpar-banco")
        return jsonify({"error": "Erro interno"}), 500


# =====================================================
# DELETAR (soft delete)
# =====================================================
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
        carga.deleted_at = now_utc_naive()

        db.session.commit()
        return jsonify({"message": "Carga marcada como deletada"}), 200

    except Exception:
        current_app.logger.exception("Erro em /pc/deletar")
        return jsonify({"error": "Erro interno"}), 500


# =====================================================
# AA DISPONÍVEIS (via MOVIMENTAÇÕES + tabela OPERADORES)
# =====================================================
@painel_bp.route("/aa-disponiveis")
def aa_disponiveis():
    """
    Regra:
    - Puxa AAs da tabela operadores
    - Descobre o ÚLTIMO movimento por badge na tabela movimentos (ORDER BY criado_em DESC)
    - Disponível se o último movimento tiver processo_destino = 'DOCA IN'
    - Ignora quem está com falta = true
    """
    try:
        query = text("""
            WITH ultimo_mov AS (
                SELECT DISTINCT ON (m.badge)
                       m.badge,
                       m.nome,
                       m.processo_destino,
                       m.criado_em,
                       m.data_inicio,
                       m.data_fim,
                       m.status
                FROM movimentos m
                WHERE m.badge IS NOT NULL
                ORDER BY m.badge, m.criado_em DESC NULLS LAST, m.data_inicio DESC NULLS LAST
            )
            SELECT
                o.login,
                o.nome AS nome_operador,
                o.badge,
                o.tag,
                o.setor,
                o.turno,
                o.cargo,
                o.processo_atual,
                o.emprestado,
                o.falta,
                um.processo_destino,
                um.criado_em
            FROM operadores o
            LEFT JOIN ultimo_mov um
                   ON (um.badge::text = o.badge::text OR um.badge::text = o.tag::text)
            WHERE o.cargo = 'AA'
              AND COALESCE(o.falta, false) = false
              AND um.processo_destino = 'DOCA IN'
            ORDER BY o.nome;
        """)

        result = db.session.execute(query).mappings().all()

        lista = []
        for r in result:
            lista.append({
                "login": r.get("login"),
                "nome": r.get("nome_operador") or r.get("nome"),
                "badge": r.get("badge") or r.get("tag"),
                "setor": r.get("setor"),
                "turno": r.get("turno"),
                "emprestado": bool(r.get("emprestado") or False),
                "processo_destino": r.get("processo_destino"),
                "ultima_movimentacao": dt_to_iso(to_naive(r.get("criado_em"))),
            })

        return jsonify(lista), 200

    except Exception:
        current_app.logger.exception("Erro em /pc/aa-disponiveis")
        # seu print da imagem: você colocou return jsonify([]),200 no except -> manter
        return jsonify([]), 200