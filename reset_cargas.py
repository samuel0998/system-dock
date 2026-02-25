import os
from sqlalchemy import create_engine, text


def get_db_url() -> str:
    """
    Busca a URL do Postgres a partir das variáveis mais comuns no Railway/Flask.
    Normaliza postgres:// -> postgresql://
    """
    url = (
        os.getenv("DATABASE_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRESQL_URL")
    )

    if not url:
        raise RuntimeError(
            "Sem URL do banco no ambiente. Defina DATABASE_URL (Railway) ou SQLALCHEMY_DATABASE_URI."
        )

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


def run():
    engine = create_engine(get_db_url(), future=True, pool_pre_ping=True)

    ddl = """
    DROP TABLE IF EXISTS cargas CASCADE;

    CREATE TABLE cargas (
      id SERIAL PRIMARY KEY,

      appointment_id VARCHAR(80) UNIQUE,

      -- NOVAS COLUNAS (coluna B do upload)
      truck_type VARCHAR(30) NULL,   -- OTHER / CARP / TRANSSHIP
      truck_tipo VARCHAR(30) NULL,   -- VDD / Transferência

      expected_arrival_date TIMESTAMP NULL,
      priority_last_update TIMESTAMP NULL,
      priority_score DOUBLE PRECISION NULL, -- era INTEGER, mas no upload vem float
      prioridade_maxima BOOLEAN NOT NULL DEFAULT FALSE,
      status VARCHAR(30) NOT NULL DEFAULT 'arrival',
      cartons INTEGER NOT NULL DEFAULT 0,
      units INTEGER NOT NULL DEFAULT 0,

      aa_responsavel VARCHAR(80) NULL,
      start_time TIMESTAMP NULL,
      end_time TIMESTAMP NULL,
      tempo_total_segundos INTEGER NULL,
      units_por_hora DOUBLE PRECISION NULL, -- pode ser decimal

      delete_reason VARCHAR(255) NULL,
      deleted_at TIMESTAMP NULL,

      created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))

    print("✅ Tabela 'cargas' recriada com sucesso (com truck_type e truck_tipo).")


if __name__ == "__main__":
    run()