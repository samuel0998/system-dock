import os
from sqlalchemy import create_engine, text


def _normalize_db_url(url: str) -> str:
    """
    Railway às vezes fornece postgres:// e o SQLAlchemy prefere postgresql://
    """
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def run():
    db_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL não encontrada. Defina DATABASE_URL (Railway) ou SQLALCHEMY_DATABASE_URI."
        )

    db_url = _normalize_db_url(db_url)
    engine = create_engine(db_url, pool_pre_ping=True)

    with engine.begin() as conn:
        # =========================
        # 1) TABELA CARGAS (CREATE)
        # =========================
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS cargas (
            id SERIAL PRIMARY KEY,

            appointment_id VARCHAR(80) NOT NULL,

            expected_arrival_date TIMESTAMPTZ NOT NULL,
            priority_last_update TIMESTAMPTZ NOT NULL,

            priority_score DOUBLE PRECISION DEFAULT 0,
            prioridade_maxima BOOLEAN DEFAULT FALSE,

            status VARCHAR(20) DEFAULT 'arrival',

            cartons INTEGER DEFAULT 0,
            units INTEGER DEFAULT 0,

            aa_responsavel VARCHAR(80),

            start_time TIMESTAMPTZ,
            end_time TIMESTAMPTZ,

            tempo_total_segundos INTEGER,
            units_por_hora DOUBLE PRECISION,

            delete_reason TEXT,
            deleted_at TIMESTAMPTZ,

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """))

        # =========================
        # 2) MIGRAÇÃO "ANTI-BANCO TORTO"
        #    adiciona colunas faltantes se a tabela já existia
        # =========================
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS appointment_id VARCHAR(80);"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS expected_arrival_date TIMESTAMPTZ;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS priority_last_update TIMESTAMPTZ;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS priority_score DOUBLE PRECISION DEFAULT 0;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS prioridade_maxima BOOLEAN DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'arrival';"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS cartons INTEGER DEFAULT 0;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS units INTEGER DEFAULT 0;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS aa_responsavel VARCHAR(80);"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS start_time TIMESTAMPTZ;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS end_time TIMESTAMPTZ;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS tempo_total_segundos INTEGER;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS units_por_hora DOUBLE PRECISION;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS delete_reason TEXT;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;"))
        conn.execute(text("ALTER TABLE cargas ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();"))

        # Se appointment_id existir mas tiver linhas nulas antigas, define algo padrão (evita NOT NULL quebrar caso você aplique depois)
        # (Opcional, mas ajuda)
        conn.execute(text("""
        UPDATE cargas
        SET appointment_id = COALESCE(appointment_id, 'UNKNOWN')
        WHERE appointment_id IS NULL;
        """))

        # =========================
        # 3) TABELA OP (CREATE)
        # =========================
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS op (
            login VARCHAR(60) PRIMARY KEY,
            nome VARCHAR(120),
            badge VARCHAR(60),
            processo_atual VARCHAR(60),
            falta BOOLEAN DEFAULT FALSE,
            emprestado BOOLEAN DEFAULT FALSE
        );
        """))

        # =========================
        # 4) INDEXES (IF NOT EXISTS)
        # =========================
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_cargas_appointment_id ON cargas (appointment_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_cargas_expected_arrival_date ON cargas (expected_arrival_date);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_cargas_status ON cargas (status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_cargas_aa_responsavel ON cargas (aa_responsavel);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_op_processo_atual ON op (processo_atual);"))

    print("✅ Schema criado/atualizado com sucesso no Railway!")


if __name__ == "__main__":
    run()