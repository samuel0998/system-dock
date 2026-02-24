import os
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

def _get_database_uri() -> str:
    # Railway pode fornecer nomes diferentes dependendo do template/serviço
    uri = (
        os.getenv("DATABASE_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRESQL_URL")
    )

    if not uri:
        raise RuntimeError(
            "Banco não configurado. Defina DATABASE_URL (Railway) ou SQLALCHEMY_DATABASE_URI."
        )

    # Alguns provedores usam 'postgres://' (antigo). SQLAlchemy 2 prefere 'postgresql://'
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    return uri


def init_db(app):
    app.config["SQLALCHEMY_DATABASE_URI"] = _get_database_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    migrate.init_app(app, db)