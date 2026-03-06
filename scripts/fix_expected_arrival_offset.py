#!/usr/bin/env python3
"""
Corrige expected_arrival_date sem apagar dados.

Uso (dry-run):
  python scripts/fix_expected_arrival_offset.py --offset-hours 3 --from 2026-03-01 --to 2026-03-10

Aplicar:
  python scripts/fix_expected_arrival_offset.py --offset-hours 3 --from 2026-03-01 --to 2026-03-10 --apply

Filtro por appointments:
  python scripts/fix_expected_arrival_offset.py --offset-hours 3 --appointments 92265056969,75525056969 --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import db
from db import init_db
from flask import Flask


BACKUP_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cargas_expected_arrival_backup (
    id BIGSERIAL PRIMARY KEY,
    carga_id INTEGER NOT NULL,
    appointment_id VARCHAR(80) NOT NULL,
    old_expected_arrival_date TIMESTAMPTZ,
    new_expected_arrival_date TIMESTAMPTZ,
    reason TEXT,
    corrected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--offset-hours", type=int, required=True, help="Horas a somar no expected_arrival_date")
    p.add_argument("--from", dest="from_date", type=str, default=None, help="Data inicial YYYY-MM-DD")
    p.add_argument("--to", dest="to_date", type=str, default=None, help="Data final YYYY-MM-DD")
    p.add_argument("--appointments", type=str, default=None, help="Lista CSV de appointment IDs")
    p.add_argument("--apply", action="store_true", help="Efetiva update. Sem essa flag executa dry-run")
    return p.parse_args()


def main():
    args = parse_args()
    app = Flask(__name__)
    init_db(app)

    appointments = None
    if args.appointments:
        appointments = [a.strip() for a in args.appointments.split(",") if a.strip()]

    with app.app_context():
        db.session.execute(text(BACKUP_TABLE_SQL))
        db.session.commit()

        filters = ["expected_arrival_date IS NOT NULL"]
        params: dict[str, object] = {"offset_hours": args.offset_hours}

        if args.from_date:
            filters.append("expected_arrival_date >= :from_date")
            params["from_date"] = datetime.fromisoformat(args.from_date).replace(tzinfo=timezone.utc)

        if args.to_date:
            filters.append("expected_arrival_date <= :to_date")
            params["to_date"] = datetime.fromisoformat(args.to_date).replace(
                hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
            )

        if appointments:
            filters.append("appointment_id = ANY(:appointments)")
            params["appointments"] = appointments

        where_clause = " AND ".join(filters)

        preview_sql = text(
            f"""
            SELECT id, appointment_id, expected_arrival_date,
                   expected_arrival_date + make_interval(hours => :offset_hours) AS new_expected
            FROM cargas
            WHERE {where_clause}
            ORDER BY expected_arrival_date ASC
            """
        )
        rows = db.session.execute(preview_sql, params).mappings().all()

        print(f"Registros candidatos: {len(rows)}")
        for r in rows[:20]:
            print(f"- id={r['id']} appt={r['appointment_id']} old={r['expected_arrival_date']} new={r['new_expected']}")
        if len(rows) > 20:
            print(f"... +{len(rows)-20} registros")

        if not args.apply:
            print("Dry-run concluído. Use --apply para efetivar.")
            return

        if not rows:
            print("Nenhum registro para atualizar.")
            return

        backup_insert = text(
            f"""
            INSERT INTO cargas_expected_arrival_backup (carga_id, appointment_id, old_expected_arrival_date, new_expected_arrival_date, reason)
            SELECT id, appointment_id, expected_arrival_date,
                   expected_arrival_date + make_interval(hours => :offset_hours),
                   :reason
            FROM cargas
            WHERE {where_clause}
            """
        )
        db.session.execute(backup_insert, {**params, "reason": f"offset_hours={args.offset_hours}"})

        update_sql = text(
            f"""
            UPDATE cargas
            SET expected_arrival_date = expected_arrival_date + make_interval(hours => :offset_hours)
            WHERE {where_clause}
            """
        )
        db.session.execute(update_sql, params)
        db.session.commit()
        print("Atualização aplicada com backup em cargas_expected_arrival_backup.")


if __name__ == "__main__":
    main()
