# /app/api/painel.py
from flask import Blueprint, jsonify, request, render_template, current_app
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

from db import db
from models import Carga  # Operador pode ficar no models, mas aqui vamos consultar via SQL direto
from api.auth import require_capability

painel_bp = Blueprint("painel", __name__, url_prefix="/pc")

try:
    LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=-3))


# =====================================================
# Helpers
# =====================================================
def _to_aware_utc(dt: datetime | None) -> datetime | None:
    """Garante datetime timezone-aware em UTC (evita erro naive vs aware)."""
    if not dt:
        return None
    if isinstance(dt, datetime) and dt.tzinfo is None:
        # O banco persiste timestamps em UTC (sem tzinfo em alguns drivers).
        # Portanto, datetime naive deve ser interpretado como UTC.
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc) if isinstance(dt, datetime) else None


def _deadline_sla_por_expected(carga: Carga) -> datetime | None:
    """
    Regra operacional: a ofensa sempre é 4h após Expected Arrival Date,
    inclusive quando a carga já avançou de ARRIVAL_SCHEDULED para ARRIVAL.
    """
    expected = _to_aware_utc(carga.expected_arrival_date)
    if expected:
        return expected + timedelta(hours=4)

    # fallback defensivo para registros legados sem expected
    arrived = _to_aware_utc(carga.arrived_at)
    if arrived:
        return arrived + timedelta(hours=4)

    return None


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

            # ✅ Regra de SLA única:
            # ARRIVAL, ARRIVAL_SCHEDULED e CHECKIN ofendem em +4h do Expected Arrival Date.
            if c.status in ("arrival", "arrival_scheduled", "checkin"):
                deadline = _deadline_sla_por_expected(c)

                if deadline:
                    tempo_sla_segundos = int((deadline - agora).total_seconds())

                    # ✅ registrador de atraso persistente
                    if tempo_sla_segundos < 0:
                        atraso_atual = abs(tempo_sla_segundos)
                        if (not c.atraso_registrado) or (atraso_atual > int(c.atraso_segundos or 0)):
                            c.atraso_segundos = atraso_atual
                            c.atraso_registrado = True
                            mudou_algo = True

            start_time_utc = _to_aware_utc(c.start_time)

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
                "start_time": start_time_utc.isoformat() if start_time_utc else None,
                "tempo_total_segundos": int(c.tempo_total_segundos) if c.tempo_total_segundos is not None else None,

                # ✅ tempo do SLA (front decide se mostra vermelho quando negativo)
                "tempo_sla_segundos": tempo_sla_segundos,

                # ✅ atraso persistido
                "atraso_segundos": int(c.atraso_segundos or 0),
                "atraso_registrado": bool(c.atraso_registrado),
                "atraso_comentario": c.atraso_comentario,

                "priority_score": float(c.priority_score or 0),
            })

        if mudou_algo:
            db.session.commit()

        return jsonify(lista), 200

    except Exception:
        current_app.logger.exception("Erro em /pc/listar")
        return jsonify([]), 200


@painel_bp.route("/adicionar", methods=["POST"])
@require_capability("painel_set_aa")
def adicionar_carga():
    data = request.get_json(silent=True) or {}

    appointment_id = (data.get("appointment_id") or "").strip()
    expected_raw = (data.get("expected_arrival_date") or "").strip()
    status = (data.get("status") or "arrival_scheduled").strip().lower()
    truck_tipo = (data.get("truck_tipo") or "").strip() or None
    truck_type = (data.get("truck_type") or "").strip() or None

    try:
        units = int(data.get("units") or 0)
        cartons = int(data.get("cartons") or 0)
    except Exception:
        return jsonify({"error": "Units/Cartons inválidos"}), 400

    if not appointment_id:
        return jsonify({"error": "Appointment ID é obrigatório"}), 400

    if status not in {"arrival_scheduled", "arrival", "checkin", "closed", "no_show", "deleted"}:
        return jsonify({"error": "Status inválido"}), 400

    try:
        expected_dt = datetime.fromisoformat(expected_raw)
    except Exception:
        return jsonify({"error": "Expected Arrival Date inválida"}), 400

    if expected_dt.tzinfo is None:
        expected_dt = expected_dt.replace(tzinfo=LOCAL_TZ)

    existente = Carga.query.filter_by(appointment_id=appointment_id).first()
    if existente:
        return jsonify({"error": "Appointment ID já existe"}), 409

    agora = datetime.now(timezone.utc)
    carga = Carga(
        appointment_id=appointment_id,
        truck_tipo=truck_tipo,
        truck_type=truck_type,
        expected_arrival_date=expected_dt.astimezone(timezone.utc),
        priority_last_update=agora,
        status=status,
        units=max(0, units),
        cartons=max(0, cartons),
    )

    db.session.add(carga)
    db.session.commit()

    return jsonify({"message": "Carga adicionada com sucesso", "id": carga.id}), 201


@painel_bp.route("/checkin/<int:carga_id>", methods=["POST"])
@require_capability("painel_set_aa")
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
@require_capability("painel_finalize")
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

    # Persistência da métrica: se ofendeu no fechamento, fica registrada para sempre.
    deadline = _deadline_sla_por_expected(carga)
    if deadline and end_time > deadline:
        atraso_atual = int((end_time - deadline).total_seconds())
        if (not carga.atraso_registrado) or (atraso_atual > int(carga.atraso_segundos or 0)):
            carga.atraso_registrado = True
            carga.atraso_segundos = atraso_atual

    db.session.commit()
    return jsonify({"message": "Carga finalizada"})



@painel_bp.route("/deletar/<int:carga_id>", methods=["POST"])
@require_capability("painel_delete")
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
@require_capability("painel_carga_chegou")
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


@painel_bp.route("/comentar-atraso/<int:carga_id>", methods=["POST"])
@require_capability("painel_comment")
def comentar_atraso(carga_id):
    data = request.get_json(silent=True) or {}
    comentario = (data.get("comentario") or "").strip()

    if not comentario:
        return jsonify({"error": "Comentário é obrigatório"}), 400

    carga = Carga.query.get(carga_id)
    if not carga:
        return jsonify({"error": "Carga não encontrada"}), 404

    if carga.status not in ("arrival", "arrival_scheduled", "checkin"):
        return jsonify({"error": "Comentário só pode ser registrado para cargas em ARRIVAL/ARRIVAL_SCHEDULED/CHECKIN"}), 400

    carga.atraso_comentario = comentario
    carga.atraso_comentado_em = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify({"message": "Comentário de atraso salvo"}), 200


@painel_bp.route("/expert/manage/<int:carga_id>", methods=["POST"])
@require_capability("expert_manage")
def expert_manage_carga(carga_id):
    carga = Carga.query.get(carga_id)
    if not carga:
        return jsonify({"error": "Carga não encontrada"}), 404

    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip().lower()

    if action == "hard_delete":
        db.session.delete(carga)
        db.session.commit()
        return jsonify({"message": "Carga deletada do banco com sucesso"}), 200

    if action == "edit":
        allowed_fields = {
            "appointment_id",
            "status",
            "units",
            "cartons",
            "aa_responsavel",
            "truck_type",
            "truck_tipo",
        }

        updates = data.get("updates") or {}
        for field, value in updates.items():
            if field not in allowed_fields:
                continue
            if field in {"units", "cartons"}:
                try:
                    value = int(value)
                except Exception:
                    continue
            setattr(carga, field, value)

        db.session.commit()
        return jsonify({"message": "Carga atualizada com sucesso"}), 200

    return jsonify({"error": "Ação inválida"}), 400


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
@require_capability("painel_set_aa")
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
