import os
from flask import Flask, jsonify, session, request, redirect, url_for
from flask_cors import CORS

from api.upload import upload_bp
from api.painel import painel_bp
from api.dashboard import dashboard_bp
from api.transferin import transferin_bp
from api.auth import auth_bp, current_capabilities, current_role, refresh_session_role_from_db

from db import init_db
import models  # garante que os models sejam importados (Carga etc.)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "dock-view-dev-secret")

    # Configs básicas
    app.config["JSON_SORT_KEYS"] = False
    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

    # CORS
    CORS(app)

    # Inicializa DB
    init_db(app)


    # Blueprints
    app.register_blueprint(upload_bp)
    app.register_blueprint(painel_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(transferin_bp)
    app.register_blueprint(auth_bp)

    @app.context_processor
    def inject_auth_context():
        return {
            "auth_role": current_role(),
            "auth_caps": current_capabilities(),
        }

    @app.before_request
    def _auth_guard():
        path = request.path or ""

        if (
            path.startswith("/static/")
            or path.startswith("/auth/")
            or path in ("/", "/health")
        ):
            return None

        if session.get("auth_ok"):
            # Revalida perfil no banco a cada request para refletir mudanças de permissão em tempo real.
            if refresh_session_role_from_db():
                return None
            session.clear()

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        accepts_json = "application/json" in (request.headers.get("Accept") or "")
        if is_ajax or accepts_json or request.method != "GET":
            return jsonify({"error": "Não autenticado"}), 401

        return redirect(url_for("auth.login_page"))

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
