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
        raise RuntimeError("Sem URL do banco no ambiente (DATABASE_URL / SQLALCHEMY_DATABASE_URI).")

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


def run():
    engine = create_engine(get_db_url(), future=True, pool_pre_ping=True)

    ddl = """
    DROP TABLE IF EXISTS transferencias CASCADE;
    DROP TABLE IF EXISTS cargas CASCADE;

    CREATE TABLE cargas (
      id SERIAL PRIMARY KEY,

      appointment_id VARCHAR(80) UNIQUE NOT NULL,

      -- Datas principais
      expected_arrival_date TIMESTAMP NULL,
      priority_last_update TIMESTAMP NULL,

      -- Prioridade / Métricas
      priority_score DOUBLE PRECISION NULL,
      prioridade_maxima BOOLEAN NOT NULL DEFAULT FALSE,

      -- Status do sistema (sempre lower)
      -- arrival_scheduled | arrival | checkin | closed | no_show | deleted
      status VARCHAR(40) NOT NULL DEFAULT 'arrival',

      cartons INTEGER NOT NULL DEFAULT 0,
      units INTEGER NOT NULL DEFAULT 0,

      -- Tipo de carro (coluna B)
      truck_type VARCHAR(30) NULL,   -- ex: OTHER / CARP / TRANSSHIP
      truck_tipo VARCHAR(30) NULL,   -- ex: VDD / Transferência

      -- Fluxo operacional
      aa_responsavel VARCHAR(80) NULL,
      start_time TIMESTAMP NULL,
      end_time TIMESTAMP NULL,
      tempo_total_segundos INTEGER NULL,
      units_por_hora DOUBLE PRECISION NULL,

      -- ARRIVAL SLA (quando clicar "CARGA CHEGOU")
      arrived_at TIMESTAMP NULL,
      sla_setar_aa_deadline TIMESTAMP NULL,

      -- Atraso persistente
      atraso_registrado BOOLEAN NOT NULL DEFAULT FALSE,
      atraso_segundos INTEGER NOT NULL DEFAULT 0,
      atraso_comentario TEXT NULL,
      atraso_comentado_em TIMESTAMP NULL,

      -- Exclusão lógica
      delete_reason VARCHAR(255) NULL,
      deleted_at TIMESTAMP NULL,

      created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE TABLE transferencias (
      id SERIAL PRIMARY KEY,
      appointment_id VARCHAR(80) UNIQUE NOT NULL,
      carga_id INTEGER NULL,

      expected_arrival_date TIMESTAMP NULL,
      status_carga VARCHAR(30) NULL,
      units INTEGER NOT NULL DEFAULT 0,
      cartons INTEGER NOT NULL DEFAULT 0,

      vrid VARCHAR(80) NULL,
      late_stow_deadline TIMESTAMP NULL,
      origem VARCHAR(10) NULL,

      info_preenchida BOOLEAN NOT NULL DEFAULT FALSE,
      finalizada BOOLEAN NOT NULL DEFAULT FALSE,
      finished_at TIMESTAMP NULL,

      prazo_estourado BOOLEAN NOT NULL DEFAULT FALSE,
      prazo_estourado_segundos INTEGER NOT NULL DEFAULT 0,
      comentario_late_stow TEXT NULL,
      comentario_late_stow_em TIMESTAMP NULL,

      created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))

    print("✅ Tabela 'cargas' recriada com sucesso (com SLA/Tipo/Atraso).")


if __name__ == "__main__":
    run()
