# /app/api/painel.py
from flask import Blueprint, jsonify, request, render_template, current_app
from datetime import datetime, timezone, timedelta

from sqlalchemy import text

from db import db
from models import Carga  # Operador pode ficar no models, mas aqui vamos consultar via SQL direto

painel_bp = Blueprint("painel", __name__, url_prefix="/pc")


# =====================================================
# Helpers
# =====================================================
def _to_aware_utc(dt: datetime | None) -> datetime | None:
    """Garante datetime timezone-aware em UTC (evita erro naive vs aware)."""
    if not dt:
        return None
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc) if isinstance(dt, datetime) else None


# =====================================================
# Pages
# =====================================================
@painel_bp.route("/rate")
def rate_page():
    return render_template("rate.html")


@painel_bp.route("/")
def painel_page():
    return render_template("pc.html")


# =====================================================
# CARGAS
# =====================================================
@painel_bp.route("/listar")
def listar_cargas():
    try:
        agora = datetime.now(timezone.utc)

        cargas = Carga.query.order_by(Carga.expected_arrival_date.asc()).all()
        lista = []
        mudou_algo = False

        for c in cargas:
            expected = c.expected_arrival_date
            if expected and expected.tzinfo is None:
                expected = expected.replace(tzinfo=timezone.utc)

            # ✅ NO SHOW só para ARRIVAL_SCHEDULED (24h após expected)
            if c.status == "arrival_scheduled" and expected:
                if agora > (expected + timedelta(hours=24)):
                    c.status = "no_show"
                    mudou_algo = True

            tempo_sla_segundos = None

            # ✅ Nova regra de contagem:
            # - ARRIVAL: mantém deadline de 4h a partir de "carga chegou"
            # - ARRIVAL_SCHEDULED: após passar do expected, inicia contagem de 4h
            if c.status in ("arrival", "arrival_scheduled"):
                deadline = None

                if c.status == "arrival":
                    if c.sla_setar_aa_deadline is None:
                        # fallback defensivo caso algum registro antigo esteja sem deadline
                        base = c.arrived_at or agora
                        c.arrived_at = c.arrived_at or base
                        c.sla_setar_aa_deadline = base + timedelta(hours=4)
                        mudou_algo = True

                    deadline = c.sla_setar_aa_deadline

                elif c.status == "arrival_scheduled" and expected and agora > expected:
                    deadline = expected + timedelta(hours=4)

                if deadline and deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)

                if deadline:
                    tempo_sla_segundos = int((deadline - agora).total_seconds())

                    # ✅ registrador de atraso persistente
                    if tempo_sla_segundos < 0:
                        atraso_atual = abs(tempo_sla_segundos)
                        if (not c.atraso_registrado) or (atraso_atual > int(c.atraso_segundos or 0)):
                            c.atraso_segundos = atraso_atual
                            c.atraso_registrado = True
                            mudou_algo = True

            lista.append({
                "id": c.id,
                "appointment_id": c.appointment_id,

                "truck_type": getattr(c, "truck_type", None),
                "truck_tipo": getattr(c, "truck_tipo", None),

                "expected_arrival_date": expected.isoformat() if expected else None,
                "status": c.status,

                "units": int(c.units or 0),
                "cartons": int(c.cartons or 0),
                "aa_responsavel": c.aa_responsavel,
                "start_time": c.start_time.isoformat() if c.start_time else None,
                "tempo_total_segundos": int(c.tempo_total_segundos) if c.tempo_total_segundos is not None else None,

                # ✅ tempo do SLA (front decide se mostra vermelho quando negativo)
                "tempo_sla_segundos": tempo_sla_segundos,

                # ✅ atraso persistido
                "atraso_segundos": int(c.atraso_segundos or 0),
                "atraso_registrado": bool(c.atraso_registrado),

                "priority_score": float(c.priority_score or 0),
            })

        if mudou_algo:
            db.session.commit()

        return jsonify(lista), 200

    except Exception:
        current_app.logger.exception("Erro em /pc/listar")
        return jsonify([]), 200


@painel_bp.route("/checkin/<int:carga_id>", methods=["POST"])
def checkin(carga_id):
    dados = request.get_json(silent=True) or {}
    aa_login = (dados.get("aa_responsavel") or "").strip()

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


@painel_bp.route("/finalizar/<int:carga_id>", methods=["POST"])
def finalizar(carga_id):
    carga = Carga.query.get(carga_id)
    if not carga:
        return jsonify({"error": "Carga não encontrada"}), 404

    start_time = _to_aware_utc(carga.start_time)
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


@painel_bp.route("/limpar-banco", methods=["DELETE"])
def limpar_banco():
    deletadas = db.session.query(Carga).delete(synchronize_session=False)
    db.session.commit()

    return jsonify(
        {
            "message": "Banco limpo com sucesso",
            "deletadas": int(deletadas or 0),
        }
    )


@painel_bp.route("/deletar/<int:carga_id>", methods=["POST"])
def deletar_carga(carga_id):
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



@painel_bp.route("/carga-chegou/<int:carga_id>", methods=["POST"])
def carga_chegou(carga_id):
    try:
        c = Carga.query.get_or_404(carga_id)

        if c.status != "arrival_scheduled":
            return jsonify({"message": "Carga não está em ARRIVAL_SCHEDULED."}), 400

        agora = datetime.now(timezone.utc)
        c.status = "arrival"
        c.arrived_at = agora
        c.sla_setar_aa_deadline = agora + timedelta(hours=4)

        db.session.commit()
        return jsonify({"message": "Status atualizado para ARRIVAL e SLA de 4h iniciado."}), 200

    except Exception:
        current_app.logger.exception("Erro em /pc/carga-chegou")
        return jsonify({"message": "Erro interno."}), 500


# =====================================================
# AA DISPONÍVEIS (LÓGICA POR 2 TABELAS)
#
# REGRA:
# 1) operadores.processo_atual = 'DOCA IN'  -> aparece no "Setar AA"
# 2) movimentos.processo_destino = 'DOCA IN' AND movimentos.status = 'ativo' -> aparece no "Setar AA"
#
# Observações:
# - tabela é "operadores" (não "op")
# - em movimentos NÃO existe coluna "data" (use data_inicio / criado_em)
# - join por badge: movimentos.badge pode bater com operadores.tag OU operadores.badge
# =====================================================
@painel_bp.route("/aa-disponiveis")
def aa_disponiveis():
    try:
        query = text(
            """
            SELECT DISTINCT
                o.login,
                o.nome,
                o.badge,
                o.tag,
                o.setor,
                o.turno,
                o.processo_atual,
                o.foto_url,
                COALESCE(o.emprestado, false) AS emprestado,
                COALESCE(o.falta, false) AS falta
            FROM operadores o
            WHERE
                o.cargo = 'AA'
                AND COALESCE(o.falta, false) = false
                AND (
                    -- REGRA 1: processo_atual = DOCA IN
                    o.processo_atual = 'DOCA IN'

                    OR

                    -- REGRA 2: existe movimentação ATIVA com destino DOCA IN
                    EXISTS (
                        SELECT 1
                        FROM movimentos m
                        WHERE
                            (m.badge::text = o.tag::text OR m.badge::text = o.badge::text)
                            AND m.processo_destino = 'DOCA IN'
                            AND LOWER(m.status) = 'ativo'
                    )
                )
            ORDER BY o.nome ASC
            """
        )

        rows = db.session.execute(query).mappings().all()

        lista = []
        for r in rows:
            # prioridade de "badge": usa badge se existir, senão cai no tag
            badge = r.get("badge") or r.get("tag")

            lista.append(
                {
                    "login": r.get("login"),
                    "nome": r.get("nome"),
                    "badge": badge,
                    "emprestado": bool(r.get("emprestado")),
                    "falta": bool(r.get("falta")),
                    "processo_atual": r.get("processo_atual"),
                    "setor": r.get("setor"),
                    "turno": r.get("turno"),
                    "foto_url": r.get("foto_url"),
                }
            )

        return jsonify(lista)

    except Exception:
        current_app.logger.exception("Erro em /pc/aa-disponiveis")
        # não quebra o front (modal abre vazio, mas não estoura erro no JS)
        return jsonify([]), 200