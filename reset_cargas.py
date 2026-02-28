import os
from sqlalchemy import create_engine, text


def get_db_url() -> str:
    url = (
        os.getenv("DATABASE_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRESQL_URL")
    )
    if not url:
        raise RuntimeError("Sem URL do banco no ambiente. Defina DATABASE_URL/SQLALCHEMY_DATABASE_URI.")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def run():
    engine = create_engine(get_db_url(), future=True, pool_pre_ping=True)

    ddl = """
    DROP TABLE IF EXISTS cargas CASCADE;

    CREATE TABLE cargas (
      id SERIAL PRIMARY KEY,

      appointment_id VARCHAR(80) UNIQUE NOT NULL,

      -- ✅ Novo: tipo da carga
      truck_type VARCHAR(30) NULL,   -- CARP / OTHER / TRANSSHIP (bruto)
      truck_tipo VARCHAR(30) NULL,   -- VDD / Transferência (mapeado)

      expected_arrival_date TIMESTAMP NULL,
      priority_last_update TIMESTAMP NULL,
      priority_score NUMERIC NULL,

      -- ✅ Status
      status VARCHAR(30) NOT NULL DEFAULT 'arrival',

      prioridade_maxima BOOLEAN NOT NULL DEFAULT FALSE,
      cartons INTEGER NOT NULL DEFAULT 0,
      units INTEGER NOT NULL DEFAULT 0,

      aa_responsavel VARCHAR(80) NULL,

      -- ✅ Times do processo
      start_time TIMESTAMP NULL,
      end_time TIMESTAMP NULL,
      tempo_total_segundos INTEGER NULL,
      units_por_hora NUMERIC NULL,

      -- ✅ Novo: controle de chegada e SLA de 4h para setar AA
      arrived_at TIMESTAMP NULL,          -- quando clicou "CARGA CHEGOU" (virou arrival)
      sla_setar_aa_deadline TIMESTAMP NULL, -- arrived_at + 4h

      -- ✅ Novo: registro de atraso (persistente)
      atraso_segundos INTEGER NOT NULL DEFAULT 0,     -- maior atraso já registrado (>=0)
      atraso_registrado BOOLEAN NOT NULL DEFAULT FALSE,

      delete_reason VARCHAR(255) NULL,
      deleted_at TIMESTAMP NULL,

      created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_cargas_status ON cargas(status);
    CREATE INDEX IF NOT EXISTS idx_cargas_expected ON cargas(expected_arrival_date);
    CREATE INDEX IF NOT EXISTS idx_cargas_deadline ON cargas(sla_setar_aa_deadline);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))

    print("✅ Tabela 'cargas' recriada com sucesso (com ARRIVAL_SCHEDULED + SLA + atraso).")


if __name__ == "__main__":
    run()