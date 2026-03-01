import os
from flask import Flask, jsonify
from flask_cors import CORS

from api.upload import upload_bp
from api.painel import painel_bp
from api.dashboard import dashboard_bp
from api.transferin import transferin_bp

from db import init_db, db
import models  # garante que os models sejam importados (Carga etc.)


def _maybe_reset_cargas(app: Flask) -> None:
    """
    Reset controlado da tabela 'cargas' no deploy.
    Use no Railway com variável de ambiente:
      RESET_CARGAS=1
    Depois de rodar 1x, REMOVA/volte pra 0.
    """
    if os.getenv("RESET_CARGAS", "0") != "1":
        return

    with app.app_context():
        # Garantia extra (models já importado acima)
        from models import Carga  # noqa: F401

        # Drop somente da tabela 'cargas' e recria pelo model atual
        db.drop_all(bind=None, tables=[models.Carga.__table__])
        db.create_all()


def create_app() -> Flask:
    app = Flask(__name__)

    # Configs básicas
    app.config["JSON_SORT_KEYS"] = False
    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

    # CORS
    CORS(app)

    # Inicializa DB
    init_db(app)

    # ✅ Reset controlado (apenas se RESET_CARGAS=1)
    _maybe_reset_cargas(app)

    # Blueprints
    app.register_blueprint(upload_bp)
    app.register_blueprint(painel_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(transferin_bp)

    # Healthcheck
    @app.get("/")
    def home():
        return jsonify({
            "status": "online",
            "system": "DOCA",
            "version": "1.0"
        })

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    # Errors
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Rota não encontrada"}), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "Erro interno no servidor"}), 500

    return app


# ✅ Gunicorn/Railway precisa dessa variável no nível do módulo
app = create_app()


# ✅ Rodar localmente
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
