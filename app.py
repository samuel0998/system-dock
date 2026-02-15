from flask import Flask, jsonify
from flask_cors import CORS

# 🔹 Importar Blueprints
from api.upload import upload_bp
from api.painel import painel_bp
from api.dashboard import dashboard_bp


def create_app():

    app = Flask(__name__)

    # 🔹 Configurações básicas
    app.config["JSON_SORT_KEYS"] = False
    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

    # 🔹 Habilitar CORS (opcional, útil para integração futura)
    CORS(app)

    # 🔹 Registrar Blueprints
    app.register_blueprint(upload_bp)
    app.register_blueprint(painel_bp)
    app.register_blueprint(dashboard_bp)

    # 🔹 Rota principal
    @app.route("/")
    def home():
        return jsonify({
            "status": "online",
            "system": "DOCA",
            "version": "1.0"
        })

    # 🔹 Tratamento de erro 404
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Rota não encontrada"}), 404

    # 🔹 Tratamento de erro 500
    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "Erro interno no servidor"}), 500

    return app


# 🔹 Instância da aplicação
app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
