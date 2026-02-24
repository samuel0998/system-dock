import os
from flask import Flask, jsonify
from flask_cors import CORS

from api.upload import upload_bp
from api.painel import painel_bp
from api.dashboard import dashboard_bp

from db import init_db
import models  # garante que os models carreguem pro migrate


def create_app():
    app = Flask(__name__)

    # Configs básicas
    app.config["JSON_SORT_KEYS"] = False
    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

    # CORS (se quiser restringir depois, dá pra colocar origins)
    CORS(app)

    # Inicializa DB + Migrate
    init_db(app)

    # Blueprints
    app.register_blueprint(upload_bp)
    app.register_blueprint(painel_bp)
    app.register_blueprint(dashboard_bp)

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


# ✅ Apenas para rodar localmente (Railway usa Gunicorn do Dockerfile)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)