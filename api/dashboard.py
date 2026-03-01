from flask import Blueprint, render_template, jsonify, request
from datetime import datetime, timezone, timedelta
from sqlalchemy import func

from db import db
from models import Carga, Transferencia

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("/")
def dashboard_page():
    return render_template("dashboard.html")


@dashboard_bp.route("/stats")
def dashboard_stats():
    data_inicio = request.args.get("dataInicio")
    data_fim = request.args.get("dataFim")

    if not data_inicio or not data_fim:
        return jsonify({
            "total_units": 0,
            "total_units_no_show": 0,
            "total_notas_fechadas": 0,
            "total_notas_pendentes": 0,
            "total_notas_andamento": 0,
            "total_notas_deletadas": 0,
            "total_notas_no_show": 0,
            "unidades_por_dia": {},
            "notas_por_dia": {},
            "notas_deletadas_por_dia": {},
            "no_show_por_dia": {},
            "por_login": {},
            "total_cargas_atrasadas": 0,
            "produtividade_por_aa": {},
            "cargas_atrasadas": [],
            "transferencias_late_stow": [],
            "total_transferencias_late_stow": 0,
        })

    # intervalo UTC (00:00:00 até 23:59:59)
    inicio = datetime.fromisoformat(data_inicio).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )
    fim = datetime.fromisoformat(data_fim).replace(
        hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
    )

    agora = datetime.now(timezone.utc)

    def _to_aware_utc(dt):
        if not dt:
            return None
        if getattr(dt, "tzinfo", None) is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _deadline_sla(c):
        # Regra unificada: ARRIVAL e ARRIVAL_SCHEDULED usam +4h do expected.
        expected = _to_aware_utc(c.expected_arrival_date)
        if expected:
            return expected + timedelta(hours=4)

        # fallback para legados sem expected
        if c.status == "arrival":
            base = _to_aware_utc(c.sla_setar_aa_deadline)
            if base:
                return base
            arrived = _to_aware_utc(c.arrived_at)
            if arrived:
                return arrived + timedelta(hours=4)

        return None

    # ==========================
    # CLOSED (fechadas) por end_time
    # ==========================
    total_notas_fechadas = (
        db.session.query(func.count(Carga.id))
        .filter(
            Carga.status == "closed",
            Carga.end_time.isnot(None),
            Carga.end_time >= inicio,
            Carga.end_time <= fim
        )
        .scalar()
    ) or 0

    total_units = (
        db.session.query(func.coalesce(func.sum(Carga.units), 0))
        .filter(
            Carga.status == "closed",
            Carga.end_time.isnot(None),
            Carga.end_time >= inicio,
            Carga.end_time <= fim
        )
        .scalar()
    ) or 0

    unidades_por_dia_rows = (
        db.session.query(
            func.date(Carga.end_time).label("dia"),
            func.coalesce(func.sum(Carga.units), 0).label("units")
        )
        .filter(
            Carga.status == "closed",
            Carga.end_time.isnot(None),
            Carga.end_time >= inicio,
            Carga.end_time <= fim
        )
        .group_by(func.date(Carga.end_time))
        .order_by(func.date(Carga.end_time))
        .all()
    )
    unidades_por_dia = {str(r.dia): int(r.units) for r in unidades_por_dia_rows}

    notas_por_dia_rows = (
        db.session.query(
            func.date(Carga.end_time).label("dia"),
            func.count(Carga.id).label("qtd")
        )
        .filter(
            Carga.status == "closed",
            Carga.end_time.isnot(None),
            Carga.end_time >= inicio,
            Carga.end_time <= fim
        )
        .group_by(func.date(Carga.end_time))
        .order_by(func.date(Carga.end_time))
        .all()
    )
    notas_por_dia = {str(r.dia): int(r.qtd) for r in notas_por_dia_rows}

    por_login_rows = (
        db.session.query(
            Carga.aa_responsavel,
            func.coalesce(func.sum(Carga.units), 0).label("units"),
            func.count(Carga.id).label("notas"),
            (func.coalesce(func.sum(Carga.tempo_total_segundos), 0) / 3600.0).label("horas_produzidas"),
            func.coalesce(func.avg(Carga.units_por_hora), 0).label("produtividade_media")
        )
        .filter(
            Carga.status == "closed",
            Carga.end_time.isnot(None),
            Carga.end_time >= inicio,
            Carga.end_time <= fim,
            Carga.aa_responsavel.isnot(None)
        )
        .group_by(Carga.aa_responsavel)
        .order_by(func.sum(Carga.units).desc())
        .all()
    )
    por_login = {
        r.aa_responsavel: {
            "units": int(r.units),
            "notas": int(r.notas),
            "horas_produzidas": round(float(r.horas_produzidas or 0), 2),
            "produtividade_media": round(float(r.produtividade_media or 0), 2),
        }
        for r in por_login_rows
    }

    # ==========================
    # CHECKIN (andamento) por created_at
    # ==========================
    total_notas_andamento = (
        db.session.query(func.count(Carga.id))
        .filter(
            Carga.status == "checkin",
            Carga.created_at >= inicio,
            Carga.created_at <= fim
        )
        .scalar()
    ) or 0

    # ==========================
    # ARRIVAL (pendentes) por created_at
    # ==========================
    total_notas_pendentes = (
        db.session.query(func.count(Carga.id))
        .filter(
            Carga.status == "arrival",
            Carga.created_at >= inicio,
            Carga.created_at <= fim
        )
        .scalar()
    ) or 0

    # ==========================
    # DELETED por deleted_at
    # ==========================
    total_notas_deletadas = (
        db.session.query(func.count(Carga.id))
        .filter(
            Carga.status == "deleted",
            Carga.deleted_at.isnot(None),
            Carga.deleted_at >= inicio,
            Carga.deleted_at <= fim
        )
        .scalar()
    ) or 0

    deletadas_por_dia_rows = (
        db.session.query(
            func.date(Carga.deleted_at).label("dia"),
            func.count(Carga.id).label("qtd")
        )
        .filter(
            Carga.status == "deleted",
            Carga.deleted_at.isnot(None),
            Carga.deleted_at >= inicio,
            Carga.deleted_at <= fim
        )
        .group_by(func.date(Carga.deleted_at))
        .order_by(func.date(Carga.deleted_at))
        .all()
    )
    notas_deletadas_por_dia = {str(r.dia): int(r.qtd) for r in deletadas_por_dia_rows}

    # ==========================
    # NO SHOW por created_at (mantendo sua lógica atual)
    # ==========================
    total_notas_no_show = (
        db.session.query(func.count(Carga.id))
        .filter(
            Carga.status == "no_show",
            Carga.created_at >= inicio,
            Carga.created_at <= fim
        )
        .scalar()
    ) or 0

    no_show_por_dia_rows = (
        db.session.query(
            func.date(Carga.created_at).label("dia"),
            func.count(Carga.id).label("qtd")
        )
        .filter(
            Carga.status == "no_show",
            Carga.created_at >= inicio,
            Carga.created_at <= fim
        )
        .group_by(func.date(Carga.created_at))
        .order_by(func.date(Carga.created_at))
        .all()
    )
    no_show_por_dia = {str(r.dia): int(r.qtd) for r in no_show_por_dia_rows}

    total_units_no_show = (
        db.session.query(func.coalesce(func.sum(Carga.units), 0))
        .filter(
            Carga.status == "no_show",
            Carga.created_at >= inicio,
            Carga.created_at <= fim
        )
        .scalar()
    ) or 0

    # Métrica histórica: carga que ofendeu permanece registrada para sempre.
    cargas_sla = (
        Carga.query
        .filter(Carga.expected_arrival_date.isnot(None))
        .order_by(Carga.expected_arrival_date.asc())
        .all()
    )

    cargas_atrasadas = []
    for c in cargas_sla:
        deadline = _deadline_sla(c)
        if not deadline:
            continue

        ofendeu_agora = agora > deadline
        ofendeu_historico = bool(c.atraso_registrado)

        if not ofendeu_agora and not ofendeu_historico:
            continue

        if ofendeu_agora:
            atraso = int((agora - deadline).total_seconds())
        else:
            atraso = int(c.atraso_segundos or 0)

        expected_utc = _to_aware_utc(c.expected_arrival_date)
        cargas_atrasadas.append({
            "appointment_id": c.appointment_id,
            "status": c.status,
            "expected_arrival_date": expected_utc.isoformat() if expected_utc else None,
            "tempo_atraso_segundos": atraso,
            "units": int(c.units or 0),
            "cartons": int(c.cartons or 0),
            "aa_responsavel": c.aa_responsavel,
            "atraso_comentario": c.atraso_comentario,
        })

    transferencias_rows = (
        Transferencia.query
        .filter(
            Transferencia.expected_arrival_date.isnot(None),
            Transferencia.expected_arrival_date >= inicio,
            Transferencia.expected_arrival_date <= fim,
        )
        .order_by(Transferencia.expected_arrival_date.asc())
        .all()
    )

    transferencias_late = []
    for t in transferencias_rows:
        deadline = _to_aware_utc(t.late_stow_deadline)
        if not deadline:
            continue

        estourada_agora = (not t.finalizada) and (agora > deadline)
        estourada_historica = bool(t.prazo_estourado)

        if not estourada_agora and not estourada_historica:
            continue

        if estourada_agora:
            atraso_seg = int((agora - deadline).total_seconds())
        else:
            atraso_seg = int(t.prazo_estourado_segundos or 0)

        transferencias_late.append({
            "appointment_id": t.appointment_id,
            "vrid": t.vrid,
            "origem": t.origem,
            "expected_arrival_date": _to_aware_utc(t.expected_arrival_date).isoformat() if t.expected_arrival_date else None,
            "late_stow_deadline": deadline.isoformat(),
            "status": "finalizada" if t.finalizada else "em_aberto",
            "tempo_atraso_segundos": atraso_seg,
            "comentario_late_stow": t.comentario_late_stow,
        })

    return jsonify({
        "total_units": int(total_units),
        "total_units_no_show": int(total_units_no_show),
        "total_notas_fechadas": int(total_notas_fechadas),
        "total_notas_pendentes": int(total_notas_pendentes),
        "total_notas_andamento": int(total_notas_andamento),
        "total_notas_deletadas": int(total_notas_deletadas),
        "total_notas_no_show": int(total_notas_no_show),
        "unidades_por_dia": unidades_por_dia,
        "notas_por_dia": notas_por_dia,
        "notas_deletadas_por_dia": notas_deletadas_por_dia,
        "no_show_por_dia": no_show_por_dia,
        "por_login": por_login,
        "produtividade_por_aa": por_login,
        "total_cargas_atrasadas": len(cargas_atrasadas),
        "cargas_atrasadas": cargas_atrasadas[:50],
        "total_transferencias_late_stow": len(transferencias_late),
        "transferencias_late_stow": transferencias_late[:100],
    })
