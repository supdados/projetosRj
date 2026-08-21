"""drop legacy area columns and tables

Remove a camada legada de `area_responsavel` apos a migracao completa para
`OrgaoUnidade`. Rodar apenas apos `run_backfill_orgaos()` ter sido executado
em producao e confirmado que todos os projects e user_orgao estao vinculados.

Revision ID: c5f8a1b2d9e0
Revises: b2c4d6e8f0a1
Create Date: 2026-04-23 18:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "c5f8a1b2d9e0"
down_revision = "b2c4d6e8f0a1"
branch_labels = None
depends_on = None

_COMANDO_SNAPSHOT = "scripts/migrations/migrar_producao_v5.py --stage snapshot --apply"


def _contar(bind, tabela, filtro=""):
    """Conta registros de uma tabela legada, opcionalmente filtrando (ex.: coluna NOT NULL).

    Exemplo: `_contar(bind, 'project', 'area_responsavel IS NOT NULL')` -> 1231.
    """
    where = f" WHERE {filtro}" if filtro else ""
    return bind.execute(sa.text(f"SELECT COUNT(*) FROM {tabela}{where}")).scalar() or 0


def _exigir_snapshot(origem, registros, snapshot, copiados):
    """Aborta o upgrade se o backup dos dados legados faltar ou estiver incompleto.

    Espelho com MENOS linhas que a origem é ensaio interrompido: contar só a
    existência da tabela deixaria o drop levar o resto embora.

    Exemplo: `_exigir_snapshot('user_areas', 218, 'legacy_user_areas', 12)` -> RuntimeError.
    """
    if registros == 0 or copiados >= registros:
        return
    raise RuntimeError(
        f"Migration c5f8a1b2d9e0 apagaria {registros} registro(s) de {origem} sem backup "
        f"completo: snapshot {snapshot} tem {copiados} registro(s). "
        f"Rode `{_COMANDO_SNAPSHOT}` antes de `alembic upgrade head`."
    )


def _copiados(bind, tabelas, snapshot):
    """Linhas já congeladas no espelho; 0 quando a tabela nem existe."""
    return _contar(bind, snapshot) if snapshot in tabelas else 0


def _checar_snapshots(bind, inspector):
    tabelas = set(inspector.get_table_names())
    for origem, snapshot in (
        ("user_areas", "legacy_user_areas"),
        ("area_catalog", "legacy_area_catalog"),
    ):
        if origem in tabelas:
            _exigir_snapshot(
                origem,
                _contar(bind, origem),
                snapshot,
                _copiados(bind, tabelas, snapshot),
            )

    colunas = {col["name"] for col in inspector.get_columns("project")}
    if "area_responsavel" not in colunas:
        return
    preenchidos = _contar(bind, "project", "area_responsavel IS NOT NULL")
    _exigir_snapshot(
        "project.area_responsavel",
        preenchidos,
        "legacy_project_area",
        _copiados(bind, tabelas, "legacy_project_area"),
    )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # tabela ausente = instalação limpa: a baseline de catch-up cria tudo (Sprint 5.3)
    if "project" not in inspector.get_table_names():
        return

    _checar_snapshots(bind, inspector)

    project_columns = {col["name"] for col in inspector.get_columns("project")}
    if "area_responsavel" in project_columns:
        with op.batch_alter_table("project") as batch_op:
            batch_op.drop_column("area_responsavel")

    # drop_table já remove os índices nos dois engines; dropá-los antes quebra o
    # MySQL com ERROR 1553 (a KEY user_id sustenta a FK user_areas_ibfk_1).
    table_names = set(inspector.get_table_names())
    if "user_areas" in table_names:
        op.drop_table("user_areas")

    if "area_catalog" in table_names:
        op.drop_table("area_catalog")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_names = set(inspector.get_table_names())

    if "area_catalog" not in table_names:
        op.create_table(
            "area_catalog",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if "user_areas" not in table_names:
        op.create_table(
            "user_areas",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("area", sa.String(length=100), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    project_columns = {col["name"] for col in inspector.get_columns("project")}
    if "area_responsavel" not in project_columns:
        with op.batch_alter_table("project") as batch_op:
            batch_op.add_column(
                sa.Column("area_responsavel", sa.String(length=100), nullable=True)
            )
