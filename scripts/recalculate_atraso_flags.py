#!/usr/bin/env python3
"""Recalcula atraso_registrado/atraso_segundos sem apagar dados.

Regra aplicada:
- closed: atraso = max(0, end_time - (expected_arrival_date + 4h))
- demais status: mantém como está (atualização ocorre em tempo real no sistema)
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import timezone, timedelta
from zoneinfo import ZoneInfo

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import db, init_db
from models import Carga

try:
    LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=-3))


def _to_aware_utc(dt):
    if not dt:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _deadline(c):
    expected = _to_aware_utc(c.expected_arrival_date)
    if expected:
        return expected + timedelta(hours=4)
    return None


def main():
    app = Flask(__name__)
    init_db(app)

    with app.app_context():
        cargas = Carga.query.filter(Carga.status == "closed").all()
        changed = 0

        for c in cargas:
            deadline = _deadline(c)
            end_time = _to_aware_utc(c.end_time)
            atraso = 0
            if deadline and end_time:
                atraso = max(0, int((end_time - deadline).total_seconds()))

            novo_flag = atraso > 0
            if int(c.atraso_segundos or 0) != atraso or bool(c.atraso_registrado) != novo_flag:
                c.atraso_segundos = atraso
                c.atraso_registrado = novo_flag
                changed += 1

        db.session.commit()
        print(f"Cargas closed recalculadas: {len(cargas)} | alteradas: {changed}")


if __name__ == "__main__":
    main()
