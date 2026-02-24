import os
from sqlalchemy import create_engine, text

def get_db_url():
    url = (
        os.getenv("DATABASE_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("POSTGRESQL_URL")
    )
    if not url:
        raise RuntimeError("Sem DATABASE_URL no ambiente.")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url

def run():
    engine = create_engine(get_db_url(), future=True)

    with engine.begin() as conn:
        # 1) apaga a tabela antiga
        conn.execute(text("DROP TABLE IF EXISTS cargas CASCADE;"))

        # 2) recria com as colunas que seu upload/model usa
        conn.execute(text("""
        CREATE TABLE cargas (
            id SERIAL PRIMARY KEY,
            appointment_id VARCHAR(80) UNIQUE,
            expected_arrival_date TIMESTAMP NULL,
            priority_last_update TIMESTAMP NULL,
            priority_score INTEGER NULL,
            prioridade_maxima BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(30) NOT NULL DEFAULT 'arrival',
            cartons INTEGER NOT NULL DEFAULT 0,
            units INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """))

if __name__ == "__main__":
    run()