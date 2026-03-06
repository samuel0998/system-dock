from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from sqlalchemy import text

from db import db

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

ROLE_ORDER = ["LC1", "LC3", "LC5", "EXPERT"]

CAPABILITIES_BY_ROLE = {
    "LC1": {
        "dashboard_access": True,
        "dashboard_tables": False,
        "upload": False,
        "transferin_view": False,
        "transferin_edit": False,
        "painel_comment": False,
        "painel_carga_chegou": False,
        "painel_set_aa": False,
        "painel_delete": False,
        "painel_finalize": False,
        "expert_manage": False,
    },
    "LC3": {
        "dashboard_access": True,
        "dashboard_tables": True,
        "upload": False,
        "transferin_view": True,
        "transferin_edit": False,
        "painel_comment": True,
        "painel_carga_chegou": True,
        "painel_set_aa": False,
        "painel_delete": False,
        "painel_finalize": False,
        "expert_manage": False,
    },
    "LC5": {
        "dashboard_access": True,
        "dashboard_tables": True,
        "upload": True,
        "transferin_view": True,
        "transferin_edit": True,
        "painel_comment": True,
        "painel_carga_chegou": True,
        "painel_set_aa": True,
        "painel_delete": True,
        "painel_finalize": True,
        "expert_manage": False,
    },
    "EXPERT": {
        "dashboard_access": True,
        "dashboard_tables": True,
        "upload": True,
        "transferin_view": True,
        "transferin_edit": True,
        "painel_comment": True,
        "painel_carga_chegou": True,
        "painel_set_aa": True,
        "painel_delete": True,
        "painel_finalize": True,
        "expert_manage": True,
    },
}


def _normalize_role(raw_permission) -> str | None:
    if raw_permission is None:
        return None

    if isinstance(raw_permission, bool):
        return "LC5" if raw_permission else None

    s = str(raw_permission).strip().upper()
    if s in {"", "FALSE", "0", "NONE", "NO"}:
        return None
    if s in {"TRUE", "1", "YES"}:
        return "LC5"
    if s in CAPABILITIES_BY_ROLE:
        return s
    return None


def _normalize_bool(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, bool):
        return raw_value

    s = str(raw_value).strip().upper()
    if s in {"TRUE", "1", "YES", "Y", "SIM", "S"}:
        return True
    if s in {"FALSE", "0", "NO", "N", "NAO", "NÃO", ""}:
        return False
    return None


def _first_present(row, keys):
    for k in keys:
        if k in row:
            return row.get(k)
    return None




def _resolve_role_from_row(row) -> str | None:
    # Se existir flag booleana explícita de dockview e ela for falsa, bloqueia login.
    dockview_raw = _first_present(row, ["permission_dockview", "permissao_dockview", "dockview"])
    dockview_bool = _normalize_bool(dockview_raw)
    if dockview_bool is False:
        return None

    # Prioridade: nível explícito > flag booleana legada.
    role_raw = _first_present(
        row,
        [
            "permission_level_dockview",
            "permission_nivel_dockview",
            "nivel_permissao_dockview",
            "permission_level",
            "permission_dockview",
        ],
    )

    # Sem nível explícito, usa o flag booleano quando disponível.
    if role_raw is None and dockview_bool is not None:
        return "LC5" if dockview_bool else None

    return _normalize_role(role_raw)


def refresh_session_role_from_db() -> bool:
    """Atualiza session['permission_level'] com base no banco para o operador logado.
    Retorna True se sessão continua válida, False caso contrário.
    """
    if not session.get("auth_ok"):
        return False

    login = (session.get("operator_login") or "").strip()
    if not login:
        return False

    try:
        row = db.session.execute(
            text(
                """
                SELECT *
                FROM operadores
                WHERE UPPER(login) = UPPER(:login)
                LIMIT 1
                """
            ),
            {"login": login},
        ).mappings().first()
    except Exception:
        return False

    if not row:
        return False

    role = _resolve_role_from_row(row)
    if not role:
        return False

    session["permission_level"] = role
    return True

def current_role() -> str | None:
    return session.get("permission_level")


def current_capabilities() -> dict:
    role = current_role() or "LC1"
    return CAPABILITIES_BY_ROLE.get(role, CAPABILITIES_BY_ROLE["LC1"])


def has_capability(capability: str) -> bool:
    return bool(current_capabilities().get(capability, False))


def require_capability(capability: str):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if has_capability(capability):
                return fn(*args, **kwargs)

            is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
            accepts_json = "application/json" in (request.headers.get("Accept") or "")
            if is_ajax or accepts_json or request.method != "GET":
                return jsonify({"error": "Sem permissão para esta ação"}), 403

            flash("Sem permissão para acessar esta funcionalidade.", "error")
            return redirect(url_for("painel.painel_page"))

        return wrapped

    return decorator


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
        # SELECT * para suportar bancos com nomes de coluna diferentes sem quebrar login.
        row = db.session.execute(
            text(
                """
                SELECT *
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

    role = _resolve_role_from_row(row)
    if not role:
        flash("Você não possui permissão Dock View.", "error")
        return redirect(url_for("auth.login_page"))

    session["auth_ok"] = True
    session["operator_login"] = row.get("login")
    session["operator_nome"] = row.get("nome")
    session["permission_level"] = role

    return redirect(url_for("painel.painel_page"))


@auth_bp.get("/me")
def me():
    if not session.get("auth_ok"):
        return jsonify({"auth_ok": False}), 401

    role = current_role()
    return jsonify({
        "auth_ok": True,
        "login": session.get("operator_login"),
        "nome": session.get("operator_nome"),
        "role": role,
        "capabilities": current_capabilities(),
    })


@auth_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login_page"))
