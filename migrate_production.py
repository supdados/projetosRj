#!/usr/bin/env python3
"""
migrate_production.py
=====================
Migração incremental para banco de dados MySQL de produção.
Idempotente: pode ser executado várias vezes sem efeitos colaterais.

Pré-requisitos:
  pip install pymysql python-dotenv sqlalchemy

Configuração (.env ou variáveis de ambiente):
  DATABASE_URL=mysql+pymysql://user:pass@host/dbname
  — ou —
  DB_USER=...
  DB_PASSWORD=...
  DB_NAME=...
  DB_HOST=localhost   (opcional, padrão: localhost)
  DB_PORT=3306        (opcional, padrão: 3306)

Uso:
  python migrate_production.py
"""

import os
import sys
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

load_dotenv()


# ── Conexão ───────────────────────────────────────────────────────────────────

def build_engine():
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        return create_engine(database_url)

    user     = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    name     = os.getenv('DB_NAME')
    host     = os.getenv('DB_HOST', 'localhost')
    port     = os.getenv('DB_PORT', '3306')

    if not all([user, password, name]):
        print("ERRO: Configure DATABASE_URL ou DB_USER / DB_PASSWORD / DB_NAME no .env")
        sys.exit(1)

    uri = f"mysql+pymysql://{user}:{quote_plus(password)}@{host}:{port}/{name}"
    return create_engine(uri)


# ── Helpers ───────────────────────────────────────────────────────────────────

def table_exists(inspector, table):
    return table in inspector.get_table_names()


def column_exists(inspector, table, column):
    return column in {c['name'] for c in inspector.get_columns(table)}


def add_column(conn, table, column, col_type, log):
    conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {col_type}"))
    conn.commit()
    log.append(f"  [OK] {table}.{column}  adicionado  ({col_type})")


def ensure_column(inspector, conn, table, column, col_type, log):
    if column_exists(inspector, table, column):
        log.append(f"  [--] {table}.{column}  já existe")
    else:
        add_column(conn, table, column, col_type, log)


# ── Migrações ─────────────────────────────────────────────────────────────────

def run_migrations(engine):
    log = []

    with engine.connect() as conn:
        inspector = inspect(engine)

        # ── 1. Colunas novas em `project` ─────────────────────────────────────
        log.append("\n[project] — novas colunas:")
        if table_exists(inspector, 'project'):
            new_project_cols = [
                ('special_project',    'VARCHAR(20)'),
                ('sei_process',        'VARCHAR(50)'),
                ('short_description',  'TEXT'),
                ('delivery_type',      'VARCHAR(50)'),
                ('abep_indicator',     'VARCHAR(255)'),
                ('github_link',        'VARCHAR(500)'),
                ('documentation_link', 'VARCHAR(500)'),
            ]
            for col, typ in new_project_cols:
                ensure_column(inspector, conn, 'project', col, typ, log)
        else:
            log.append("  [AVISO] Tabela `project` não encontrada — pulando.")

        # ── 2. Coluna nova em `etapa` ─────────────────────────────────────────
        log.append("\n[etapa] — novas colunas:")
        if table_exists(inspector, 'etapa'):
            ensure_column(inspector, conn, 'etapa', 'ordem', 'INT NOT NULL DEFAULT 0', log)
        else:
            log.append("  [AVISO] Tabela `etapa` não encontrada — pulando.")

        # ── 3. Tabela `user_areas` ────────────────────────────────────────────
        log.append("\n[user_areas]:")
        if not table_exists(inspector, 'user_areas'):
            conn.execute(text("""
                CREATE TABLE `user_areas` (
                    `id`      INT AUTO_INCREMENT PRIMARY KEY,
                    `user_id` INT          NOT NULL,
                    `area`    VARCHAR(100) NOT NULL,
                    CONSTRAINT `fk_userareas_user`
                        FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()
            log.append("  [OK] Tabela `user_areas` criada.")
        else:
            log.append("  [--] Tabela `user_areas` já existe.")

        # ── 4. Tabela `project_history` ───────────────────────────────────────
        log.append("\n[project_history]:")
        if not table_exists(inspector, 'project_history'):
            conn.execute(text("""
                CREATE TABLE `project_history` (
                    `id`                 INT AUTO_INCREMENT PRIMARY KEY,
                    `project_id`         INT      NOT NULL,
                    `user_id`            INT      NOT NULL,
                    `action_type`        VARCHAR(50)  NOT NULL,
                    `action_description` TEXT         NOT NULL,
                    `old_value`          TEXT,
                    `new_value`          TEXT,
                    `timestamp`          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT `fk_ph_project`
                        FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON DELETE CASCADE,
                    CONSTRAINT `fk_ph_user`
                        FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()
            log.append("  [OK] Tabela `project_history` criada.")
        else:
            log.append("  [--] Tabela `project_history` já existe.")

        # ── 5. Tabela `StageTemplate` ─────────────────────────────────────────
        log.append("\n[StageTemplate]:")
        if not table_exists(inspector, 'StageTemplate'):
            conn.execute(text("""
                CREATE TABLE `StageTemplate` (
                    `id`          INT AUTO_INCREMENT PRIMARY KEY,
                    `name`        VARCHAR(255) NOT NULL,
                    `description` TEXT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()
            log.append("  [OK] Tabela `StageTemplate` criada.")
        else:
            log.append("  [--] Tabela `StageTemplate` já existe.")

        # ── 6. Tabela `StageTemplateItem` ─────────────────────────────────────
        log.append("\n[StageTemplateItem]:")
        if not table_exists(inspector, 'StageTemplateItem'):
            conn.execute(text("""
                CREATE TABLE `StageTemplateItem` (
                    `id`            INT AUTO_INCREMENT PRIMARY KEY,
                    `name`          VARCHAR(255) NOT NULL,
                    `duration_days` INT          NOT NULL DEFAULT 1,
                    `order`         INT          NOT NULL,
                    `templateId`    INT          NOT NULL,
                    CONSTRAINT `fk_sti_template`
                        FOREIGN KEY (`templateId`) REFERENCES `StageTemplate`(`id`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()
            log.append("  [OK] Tabela `StageTemplateItem` criada.")
        else:
            log.append("  [--] Tabela `StageTemplateItem` já existe.")

        # ── 7. Tabela `task` ──────────────────────────────────────────────────
        log.append("\n[task]:")
        if not table_exists(inspector, 'task'):
            conn.execute(text("""
                CREATE TABLE `task` (
                    `id`            INT AUTO_INCREMENT PRIMARY KEY,
                    `titulo`        VARCHAR(200) NOT NULL,
                    `project_id`    INT,
                    `created_by_id` INT          NOT NULL,
                    `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    `is_finalized`  BOOLEAN      NOT NULL DEFAULT 0,
                    `finalized_at`  DATETIME     NULL,
                    CONSTRAINT `fk_task_project`
                        FOREIGN KEY (`project_id`) REFERENCES `project`(`id`) ON DELETE SET NULL,
                    CONSTRAINT `fk_task_user`
                        FOREIGN KEY (`created_by_id`) REFERENCES `user`(`id`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.execute(text("CREATE INDEX `ix_task_is_finalized` ON `task` (`is_finalized`)"))
            conn.commit()
            log.append("  [OK] Tabela `task` criada.")
        else:
            ensure_column(inspector, conn, 'task', 'is_finalized', 'BOOLEAN NOT NULL DEFAULT 0', log)
            ensure_column(inspector, conn, 'task', 'finalized_at', 'DATETIME NULL', log)
            try:
                indexes = {idx['name'] for idx in inspector.get_indexes('task')}
            except Exception:
                indexes = set()
            if 'ix_task_is_finalized' not in indexes:
                conn.execute(text("CREATE INDEX `ix_task_is_finalized` ON `task` (`is_finalized`)"))
                conn.commit()
                log.append("  [OK] Índice task.ix_task_is_finalized criado.")
            else:
                log.append("  [--] Índice task.ix_task_is_finalized já existe.")

        # ── 8. Tabela `task_item` ─────────────────────────────────────────────
        log.append("\n[task_item]:")
        if not table_exists(inspector, 'task_item'):
            conn.execute(text("""
                CREATE TABLE `task_item` (
                    `id`          INT AUTO_INCREMENT PRIMARY KEY,
                    `descricao`   TEXT         NOT NULL,
                    `status`      VARCHAR(20)  NOT NULL DEFAULT 'programado',
                    `responsavel` VARCHAR(100),
                    `ordem`       INT          NOT NULL DEFAULT 0,
                    `task_id`     INT          NOT NULL,
                    `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    `prioridade`  VARCHAR(20),
                    `tipo_pedido` VARCHAR(30),
                    CONSTRAINT `fk_ti_task`
                        FOREIGN KEY (`task_id`) REFERENCES `task`(`id`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()
            log.append("  [OK] Tabela `task_item` criada (com prioridade e tipo_pedido).")
        else:
            # Tabela existe — garantir colunas novas
            for col, typ in [('prioridade', 'VARCHAR(20)'), ('tipo_pedido', 'VARCHAR(30)')]:
                ensure_column(inspector, conn, 'task_item', col, typ, log)

        # ── 9. Tabela `task_item_comment` ─────────────────────────────────────
        log.append("\n[task_item_comment]:")
        if not table_exists(inspector, 'task_item_comment'):
            conn.execute(text("""
                CREATE TABLE `task_item_comment` (
                    `id`           INT AUTO_INCREMENT PRIMARY KEY,
                    `content`      TEXT     NOT NULL,
                    `user_id`      INT      NOT NULL,
                    `task_item_id` INT      NOT NULL,
                    `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    `updated_at`   DATETIME ON UPDATE CURRENT_TIMESTAMP,
                    CONSTRAINT `fk_tic_user`
                        FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE,
                    CONSTRAINT `fk_tic_item`
                        FOREIGN KEY (`task_item_id`) REFERENCES `task_item`(`id`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()
            log.append("  [OK] Tabela `task_item_comment` criada.")
        else:
            log.append("  [--] Tabela `task_item_comment` já existe.")

        # ── 10. Tabela `task_item_anexo` ──────────────────────────────────────
        log.append("\n[task_item_anexo]:")
        if not table_exists(inspector, 'task_item_anexo'):
            conn.execute(text("""
                CREATE TABLE `task_item_anexo` (
                    `id`              INT AUTO_INCREMENT PRIMARY KEY,
                    `task_item_id`    INT          NOT NULL,
                    `filename`        VARCHAR(255) NOT NULL,
                    `stored_filename` VARCHAR(255) NOT NULL,
                    `content_type`    VARCHAR(100),
                    `uploaded_by_id`  INT          NOT NULL,
                    `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT `fk_tia_item`
                        FOREIGN KEY (`task_item_id`) REFERENCES `task_item`(`id`) ON DELETE CASCADE,
                    CONSTRAINT `fk_tia_user`
                        FOREIGN KEY (`uploaded_by_id`) REFERENCES `user`(`id`) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()
            log.append("  [OK] Tabela `task_item_anexo` criada.")
        else:
            log.append("  [--] Tabela `task_item_anexo` já existe.")

    return log


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Migração de produção — MySQL")
    print("=" * 60)

    try:
        engine = build_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Conexão com banco de dados: OK\n")
    except Exception as exc:
        print(f"ERRO ao conectar: {exc}")
        sys.exit(1)

    try:
        log = run_migrations(engine)
        for line in log:
            print(line)
        print("\n" + "=" * 60)
        print("  Migração concluída com sucesso.")
        print("=" * 60)
    except Exception as exc:
        print(f"\nERRO durante a migração: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
