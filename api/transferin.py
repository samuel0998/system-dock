from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import or_

from db import db
from models import Carga, Transferencia

try:
    LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    LOCAL_TZ = timezone.utc

transferin_bp = Blueprint("transferin", __name__, url_prefix="/transferin")

ORIGENS_VALIDAS = {"CNF2", "FOR2", "GIG1", "GRU9", "POA1", "REC1", "REC3", "XBRA", "XCV9"}


def _to_aware_utc(dt):
    if not dt:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_local_day_bounds_utc(ref_utc=None):
    ref_utc = ref_utc or datetime.now(timezone.utc)
    ref_local = ref_utc.astimezone(LOCAL_TZ)
    inicio_local = ref_local.replace(hour=0, minute=0, second=0, microsecond=0)
    fim_local = ref_local.replace(hour=23, minute=59, second=59, microsecond=999999)
    return inicio_local.astimezone(timezone.utc), fim_local.astimezone(timezone.utc)


def _sync_transferencias_do_dia() -> bool:
    inicio_utc, fim_utc = _to_local_day_bounds_utc()

    cargas_transfer = (
        Carga.query
        .filter(
            Carga.expected_arrival_date.isnot(None),
            Carga.expected_arrival_date >= inicio_utc,
            Carga.expected_arrival_date <= fim_utc,
            or_(Carga.truck_tipo == "Transferência", Carga.truck_type == "TRANSSHIP")
        )
        .all()
    )

    mudou = False

    for carga in cargas_transfer:
        t = Transferencia.query.filter_by(appointment_id=carga.appointment_id).first()
        if not t:
            t = Transferencia(
                appointment_id=carga.appointment_id,
                carga_id=carga.id,
                expected_arrival_date=_to_aware_utc(carga.expected_arrival_date),
                status_carga=carga.status,
                units=int(carga.units or 0),
                cartons=int(carga.cartons or 0),
                created_at=datetime.now(timezone.utc),
            )
            db.session.add(t)
            mudou = True
        else:
            before = (
                t.carga_id,
                _to_aware_utc(t.expected_arrival_date),
                t.status_carga,
                int(t.units or 0),
                int(t.cartons or 0),
            )
            t.carga_id = carga.id
            t.expected_arrival_date = _to_aware_utc(carga.expected_arrival_date)
            t.status_carga = carga.status
            t.units = int(carga.units or 0)
            t.cartons = int(carga.cartons or 0)

            after = (
                t.carga_id,
                _to_aware_utc(t.expected_arrival_date),
                t.status_carga,
                int(t.units or 0),
                int(t.cartons or 0),
            )
            if before != after:
                mudou = True

    return mudou


def _atualizar_estado_prazo(t: Transferencia, agora_utc: datetime):
    deadline = _to_aware_utc(t.late_stow_deadline)
    if not deadline:
        return

    if t.finalizada:
        fim = _to_aware_utc(t.finished_at) or agora_utc
        atraso = int((fim - deadline).total_seconds())
        if atraso > 0:
            t.prazo_estourado = True
            t.prazo_estourado_segundos = max(int(t.prazo_estourado_segundos or 0), atraso)
        return

    if agora_utc > deadline:
        t.prazo_estourado = True
        t.prazo_estourado_segundos = int((agora_utc - deadline).total_seconds())


@transferin_bp.route("/")
def transferin_page():
    return render_template("transferin.html")


@transferin_bp.route("/listar")
def listar_transferencias():
    mudou_sync = _sync_transferencias_do_dia()

    appointment_q = (request.args.get("appointment") or "").strip().lower()
    origem_q = (request.args.get("origem") or "").strip().upper()
    status_q = (request.args.get("status") or "").strip().lower()

    transferencias = Transferencia.query.order_by(Transferencia.expected_arrival_date.asc()).all()

    agora = datetime.now(timezone.utc)
    mudou = False
    out = []

    for t in transferencias:
        _atualizar_estado_prazo(t, agora)
        if t.prazo_estourado:
            mudou = True

        if appointment_q and appointment_q not in (t.appointment_id or "").lower():
            continue
        if origem_q and (t.origem or "") != origem_q:
            continue

        status_card = "pendente"
        if t.info_preenchida:
            status_card = "preenchida"
        if t.prazo_estourado and not t.finalizada:
            status_card = "atrasada"
        if t.finalizada:
            status_card = "finalizada"

        if status_q and status_q != status_card:
            continue

        deadline = _to_aware_utc(t.late_stow_deadline)
        tempo_prazo_segundos = int((deadline - agora).total_seconds()) if deadline and not t.finalizada else None

        out.append({
            "id": t.id,
            "appointment_id": t.appointment_id,
            "expected_arrival_date": _to_aware_utc(t.expected_arrival_date).isoformat() if t.expected_arrival_date else None,
            "status_carga": t.status_carga,
            "units": int(t.units or 0),
            "cartons": int(t.cartons or 0),
            "vrid": t.vrid,
            "late_stow_deadline": deadline.isoformat() if deadline else None,
            "origem": t.origem,
            "info_preenchida": bool(t.info_preenchida),
            "finalizada": bool(t.finalizada),
            "finished_at": _to_aware_utc(t.finished_at).isoformat() if t.finished_at else None,
            "prazo_estourado": bool(t.prazo_estourado),
            "prazo_estourado_segundos": int(t.prazo_estourado_segundos or 0),
            "tempo_prazo_segundos": tempo_prazo_segundos,
            "comentario_late_stow": t.comentario_late_stow,
        })

    if mudou or mudou_sync:
        db.session.commit()

    return jsonify(out)


@transferin_bp.route("/atualizar/<int:transfer_id>", methods=["POST"])
def atualizar_transferencia(transfer_id):
    t = Transferencia.query.get(transfer_id)
    data = request.get_json(silent=True) or {}
    appointment_id = (data.get("appointment_id") or "").strip()

    if not t and appointment_id:
        t = Transferencia.query.filter_by(appointment_id=appointment_id).first()

    if not t and appointment_id:
        carga = Carga.query.filter_by(appointment_id=appointment_id).first()
        if carga:
            t = Transferencia(
                appointment_id=appointment_id,
                carga_id=carga.id,
                expected_arrival_date=_to_aware_utc(carga.expected_arrival_date),
                status_carga=carga.status,
                units=int(carga.units or 0),
                cartons=int(carga.cartons or 0),
                created_at=datetime.now(timezone.utc),
            )
            db.session.add(t)
            db.session.flush()

    if not t:
        return jsonify({"error": "Transferência não encontrada"}), 404

    vrid = (data.get("vrid") or "").strip()
    origem = (data.get("origem") or "").strip().upper()
    late_stow = (data.get("late_stow_deadline") or "").strip()

    if not vrid:
        return jsonify({"error": "VRID é obrigatório"}), 400
    if origem not in ORIGENS_VALIDAS:
        return jsonify({"error": "Origem inválida"}), 400

    try:
        late_dt = datetime.fromisoformat(late_stow)
    except Exception:
        return jsonify({"error": "Data/hora de LATE STOW inválida"}), 400

    if late_dt.tzinfo is None:
        late_dt = late_dt.replace(tzinfo=LOCAL_TZ)

    t.vrid = vrid
    t.origem = origem
    t.late_stow_deadline = late_dt.astimezone(timezone.utc)
    t.info_preenchida = True

    _atualizar_estado_prazo(t, datetime.now(timezone.utc))

    db.session.commit()
    return jsonify({"message": "Informações da transferência atualizadas"})


@transferin_bp.route("/finalizar/<int:transfer_id>", methods=["POST"])
def finalizar_transferencia(transfer_id):
    t = Transferencia.query.get(transfer_id)
    if not t:
        return jsonify({"error": "Transferência não encontrada"}), 404

    t.finalizada = True
    t.finished_at = datetime.now(timezone.utc)
    _atualizar_estado_prazo(t, t.finished_at)

    db.session.commit()
    return jsonify({"message": "Transferência finalizada"})


@transferin_bp.route("/comentar/<int:transfer_id>", methods=["POST"])
def comentar_transferencia(transfer_id):
    t = Transferencia.query.get(transfer_id)
    if not t:
        return jsonify({"error": "Transferência não encontrada"}), 404

    data = request.get_json(silent=True) or {}
    comentario = (data.get("comentario") or "").strip()

    if not comentario:
        return jsonify({"error": "Comentário é obrigatório"}), 400

    # Só registra comentário para carga vencida (ou que venceu e já finalizou)
    _atualizar_estado_prazo(t, datetime.now(timezone.utc))
    if not t.prazo_estourado:
        return jsonify({"error": "Comentário permitido apenas para transferência vencida"}), 400

    t.comentario_late_stow = comentario
    t.comentario_late_stow_em = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"message": "Comentário salvo"}), 200
