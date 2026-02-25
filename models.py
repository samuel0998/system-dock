# models.py
from db import db
from datetime import datetime, timezone

class Carga(db.Model):
    __tablename__ = "cargas"

    id = db.Column(db.Integer, primary_key=True)

    appointment_id = db.Column(db.String(80), nullable=False, index=True)

    truck_type = db.Column(db.String(30))
    truck_tipo = db.Column(db.String(30))

    expected_arrival_date = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    priority_last_update = db.Column(db.DateTime(timezone=True), nullable=False)

    priority_score = db.Column(db.Float, default=0)
    prioridade_maxima = db.Column(db.Boolean, default=False)

    status = db.Column(db.String(20), default="arrival", index=True)

    cartons = db.Column(db.Integer, default=0)
    units = db.Column(db.Integer, default=0)

    aa_responsavel = db.Column(db.String(80), nullable=True, index=True)

    start_time = db.Column(db.DateTime(timezone=True), nullable=True)
    end_time = db.Column(db.DateTime(timezone=True), nullable=True)

    tempo_total_segundos = db.Column(db.Integer, nullable=True)
    units_por_hora = db.Column(db.Float, nullable=True)

    delete_reason = db.Column(db.Text, nullable=True)
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class Operador(db.Model):
    __tablename__ = "op"

    login = db.Column(db.String(60), primary_key=True)
    nome = db.Column(db.String(120), nullable=True)
    badge = db.Column(db.String(60), nullable=True)

    processo_atual = db.Column(db.String(60), nullable=True, index=True)

    falta = db.Column(db.Boolean, default=False)
    emprestado = db.Column(db.Boolean, default=False)