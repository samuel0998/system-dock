from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import text

from db import db

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.get("/login")
def login_page():
    if session.get("auth_ok"):
        return redirect(url_for("painel.painel_page"))
    return render_template("auth_login.html")


@auth_bp.post("/login")
def login_submit():
    login = (request.form.get("login") or "").strip()
    if not login:
        flash("Informe seu login.", "error")
        return redirect(url_for("auth.login_page"))

    try:
        row = db.session.execute(
            text(
                """
                SELECT login, nome, COALESCE(permission_dockview, false) AS permitido
                FROM operadores
                WHERE UPPER(login) = UPPER(:login)
                LIMIT 1
                """
            ),
            {"login": login},
        ).mappings().first()
    except Exception:
        flash("Não foi possível validar acesso agora. Tente novamente.", "error")
        return redirect(url_for("auth.login_page"))

    if not row:
        flash("Operador não encontrado.", "error")
        return redirect(url_for("auth.login_page"))

    if not bool(row.get("permitido")):
        flash("Você não possui permissão Dock View.", "error")
        return redirect(url_for("auth.login_page"))

    session["auth_ok"] = True
    session["operator_login"] = row.get("login")
    session["operator_nome"] = row.get("nome")

    return redirect(url_for("painel.painel_page"))


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_page"))
