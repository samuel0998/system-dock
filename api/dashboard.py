from flask import Blueprint, render_template, jsonify, request
from datetime import datetime, timezone
from sqlalchemy import func

from db import db
from models import Carga

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
            "por_login": {}
        })

    # intervalo UTC (00:00:00 até 23:59:59)
    inicio = datetime.fromisoformat(data_inicio).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )
    fim = datetime.fromisoformat(data_fim).replace(
        hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
    )

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
            func.count(Carga.id).label("notas")
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
        r.aa_responsavel: {"units": int(r.units), "notas": int(r.notas)}
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
        "por_login": por_login
    })