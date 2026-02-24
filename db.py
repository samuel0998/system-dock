# db.py
import os
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

DEFAULT_RAILWAY_DB = (
    "postgresql://postgres:WxmwezugggdaTwTvKsTiQrymIRkDAAvk"
    "@tramway.proxy.rlwy.net:41111/railway"
)

def init_db(app):
    database_url = os.environ.get("DATABASE_URL", "").strip()

    # Se não existir variável local, usa direto o Railway
    if not database_url:
        database_url = DEFAULT_RAILWAY_DB

    # Ajuste de compatibilidade (caso venha postgres://)
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    migrate.init_app(app, db)