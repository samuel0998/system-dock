# init_schema.py
import os
from db import db
import models  # registra Carga no metadata


def should_reset_cargas():
    return os.getenv("RESET_CARGAS", "0") == "1"


def reset_cargas_table(app):
    """
    ⚠️ DROPA e CRIA APENAS a tabela 'cargas'.
    Use quando não há dados (seu caso).
    """
    with app.app_context():
        db.drop_all(tables=[models.Carga.__table__])
        db.create_all(tables=[models.Carga.__table__])
        db.session.commit()
        print("✅ Tabela 'cargas' recriada (drop + create).")