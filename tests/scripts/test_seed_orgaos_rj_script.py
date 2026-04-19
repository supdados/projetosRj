"""Smoke-tests do script scripts/catalog/seed_orgaos_rj.py.

Cobre o fluxo idempotente: cria hierarquia em banco vazio, honra --dry-run
(rollback) e reconhece unidades já existentes (atualiza vs ignora). Não
toca DB de produção — reaproveita a fixture `app` do pytest que faz
drop_all + create_all em SQLite temporário.
"""

from types import SimpleNamespace

from models import OrgaoUnidade, db
from scripts.catalog import seed_orgaos_rj


def _patch_app(monkeypatch, app):
    monkeypatch.setattr(seed_orgaos_rj, 'app', app)
    monkeypatch.setattr(seed_orgaos_rj, 'db', db)


def _patch_args(monkeypatch, *, dry_run=False):
    monkeypatch.setattr(
        seed_orgaos_rj, 'parse_args',
        lambda: SimpleNamespace(dry_run=dry_run),
    )


def test_masked_db_uri_hides_password():
    masked = seed_orgaos_rj._masked_db_uri(
        'mysql+pymysql://usuario:segredo@db.example.com/base'
    )
    assert masked == 'mysql+pymysql://usuario:***@db.example.com/base'
    # Sem credenciais, retorna a string inalterada.
    assert seed_orgaos_rj._masked_db_uri('sqlite:///local.db') == 'sqlite:///local.db'


def test_seed_populates_hierarchy_in_empty_db(app, monkeypatch, capsys):
    _patch_app(monkeypatch, app)
    _patch_args(monkeypatch, dry_run=False)

    result = seed_orgaos_rj.main()

    output = capsys.readouterr().out
    assert result == 0
    assert 'commit: alterações persistidas' in output

    with app.app_context():
        rj = OrgaoUnidade.query.filter_by(sigla='RJ').one()
        assert rj.pai_id is None
        assert rj.tipo == 'Estado'
        setd = OrgaoUnidade.query.filter_by(sigla='SETD').one()
        assert setd.pai_id == rj.id
        assert setd.tipo == 'Secretaria'
        supdados = OrgaoUnidade.query.filter_by(sigla='SUPDADOS').one()
        assert supdados.pai_id == setd.id
        cda = OrgaoUnidade.query.filter_by(sigla='CDA').one()
        assert cda.pai_id == supdados.id
        # Total esperado = tamanho da HIERARQUIA definida no script.
        assert OrgaoUnidade.query.count() == len(seed_orgaos_rj.HIERARQUIA)


def test_seed_dry_run_does_not_persist(app, monkeypatch, capsys):
    _patch_app(monkeypatch, app)
    _patch_args(monkeypatch, dry_run=True)

    result = seed_orgaos_rj.main()

    output = capsys.readouterr().out
    assert result == 0
    assert 'Modo dry-run: SIM' in output
    assert 'dry-run: rollback executado' in output

    with app.app_context():
        # Nenhuma linha persistida após rollback.
        assert OrgaoUnidade.query.count() == 0


def test_seed_is_idempotent_when_rerun(app, monkeypatch, capsys):
    _patch_app(monkeypatch, app)
    _patch_args(monkeypatch, dry_run=False)

    seed_orgaos_rj.main()
    capsys.readouterr()  # descarta saída da primeira chamada

    result = seed_orgaos_rj.main()
    output = capsys.readouterr().out

    assert result == 0
    with app.app_context():
        # Na segunda execução não há novas linhas.
        assert OrgaoUnidade.query.count() == len(seed_orgaos_rj.HIERARQUIA)
    # Nenhuma nova criação na segunda passada.
    assert '[ADD]' not in output


def test_seed_updates_when_name_differs(app, monkeypatch, capsys):
    _patch_app(monkeypatch, app)
    _patch_args(monkeypatch, dry_run=False)

    # Primeira rodada cria a hierarquia.
    seed_orgaos_rj.main()
    capsys.readouterr()

    # Altera o nome de uma unidade para forçar branch de UPD.
    with app.app_context():
        rj = OrgaoUnidade.query.filter_by(sigla='RJ').one()
        rj.nome = 'Nome Antigo'
        db.session.commit()

    result = seed_orgaos_rj.main()
    output = capsys.readouterr().out

    assert result == 0
    assert '[UPD] RJ' in output
    with app.app_context():
        rj = OrgaoUnidade.query.filter_by(sigla='RJ').one()
        assert rj.nome == 'Estado do Rio de Janeiro'


def test_seed_reports_error_when_exception_raised(app, monkeypatch, capsys):
    _patch_app(monkeypatch, app)
    _patch_args(monkeypatch, dry_run=False)

    def _boom(*args, **kwargs):
        raise RuntimeError('falha controlada')

    monkeypatch.setattr(seed_orgaos_rj, 'find_existing', _boom)

    result = seed_orgaos_rj.main()
    output = capsys.readouterr().out

    assert result == 1
    assert 'ERRO: falha controlada' in output
