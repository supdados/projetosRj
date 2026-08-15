"""Unit de ``services/task_creation.py`` (sprint 3.2).

Cobre o parse/normalização puros (sem banco) e o caminho de orquestração com
``g.user`` real, garantindo que as recusas mantêm mensagem/status/code do
contrato HTTP de ``POST /api/tarefas``.
"""

from flask import g

from models import Task, User, db
from services.task_creation import (
    TaskCreationInput,
    _allowed_assignee_ids,
    _build_input,
    _next_task_ordem,
    _normalized_choice,
    _parse_assignee_ids,
    _refusal_code,
    _token_value,
    create_task_record,
    resolve_task_creation,
)


class FakeProjectRef:
    """Projeto mínimo aceito pelo builder (só ``id`` é lido)."""

    def __init__(self, project_id: int) -> None:
        self.id = project_id


class FakeEtapaRef:
    """Etapa mínima aceita pelo builder (só ``id`` é lido)."""

    def __init__(self, etapa_id: int) -> None:
        self.id = etapa_id


# ── Parse/normalização puros ────────────────────────────────────────────────


def test_token_value_usa_alias_quando_chave_principal_ausente():
    assert _token_value({"project_id": 7}, "project", "project_id") == 7
    assert _token_value({"project": 3, "project_id": 7}, "project", "project_id") == 3
    assert _token_value({}, "etapa", "etapa_id") is None


def test_refusal_code_traduz_status_dos_resolvers():
    assert _refusal_code(403) == "forbidden"
    assert _refusal_code(404) == "not_found"
    assert _refusal_code(400) == "validation"
    assert _refusal_code(422) == "validation"


def test_normalized_choice_descarta_valor_fora_do_conjunto():
    assert _normalized_choice("  alta  ", {"alta", "baixa"}) == "alta"
    assert _normalized_choice("inexistente", {"alta"}) is None
    assert _normalized_choice(None, {"alta"}) is None


def test_parse_assignee_ids_ignora_nao_inteiros_e_nao_listas():
    assert _parse_assignee_ids([1, "2", None, "x", 3.9]) == [1, 2, 3]
    assert _parse_assignee_ids("1,2") == []
    assert _parse_assignee_ids(None) == []


def test_build_input_cai_nos_defaults_quando_enums_sao_invalidos():
    data = _build_input(
        {"status": "inventado", "prioridade": "altissima", "tipo_pedido": ""},
        FakeProjectRef(9),
        FakeEtapaRef(4),
        "Descricao",
        "Fulano",
    )

    assert data.status == "nao_iniciada"
    assert data.prioridade is None
    assert data.tipo_pedido is None
    assert data.responsavel == "Fulano"
    assert data.project.id == 9 and data.etapa.id == 4


def test_build_input_preserva_enums_validos():
    data = _build_input(
        {
            "status": "em_andamento",
            "prioridade": "urgente",
            "tipo_pedido": "bug",
            "assignee_ids": [5],
        },
        None,
        None,
        "Avulsa",
        "",
    )

    assert (data.status, data.prioridade, data.tipo_pedido) == (
        "em_andamento",
        "urgente",
        "bug",
    )
    assert data.responsavel is None
    assert data.assignee_ids == [5]


# ── Recusas de validação (mesmas mensagens do endpoint) ─────────────────────


def test_resolve_recusa_descricao_vazia(app, seed_data):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["user_id"])
        data, refusal = resolve_task_creation(
            {"project_id": seed_data["project_id"], "descricao": "   "}
        )

    assert data is None
    assert (refusal.message, refusal.status, refusal.code) == (
        "Descrição é obrigatória.",
        422,
        "validation",
    )


def test_resolve_recusa_projeto_invisivel_com_404(app, seed_data):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["outsider_id"])
        _, refusal = resolve_task_creation(
            {"project_id": seed_data["project_id"], "descricao": "Fora de escopo"}
        )

    assert (refusal.status, refusal.code) == (404, "not_found")


def test_resolve_recusa_responsavel_fora_do_orgao(app, seed_data):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["user_id"])
        _, refusal = resolve_task_creation(
            {
                "project_id": seed_data["project_id"],
                "descricao": "Com responsavel",
                "responsavel": "Usuario VPD",
            }
        )

    assert (refusal.status, refusal.code) == (422, "validation")
    assert "Usuario VPD" in refusal.message


def test_resolve_canoniza_responsavel_valido(app, seed_data):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["user_id"])
        data, refusal = resolve_task_creation(
            {
                "project_id": seed_data["project_id"],
                "titulo": "Via alias titulo",
                "responsavel": "usuario auditoria",
            }
        )

    assert refusal is None
    assert data.descricao == "Via alias titulo"
    assert data.responsavel == "Usuario Auditoria"


# ── Criação ─────────────────────────────────────────────────────────────────


def test_create_task_record_persiste_campos_e_ordem_sequencial(app, seed_data):
    with app.test_request_context():
        author = db.session.get(User, seed_data["user_id"])
        g.user = author
        data, _ = resolve_task_creation(
            {
                "project_id": seed_data["project_id"],
                "etapa_id": seed_data["etapa_id"],
                "descricao": "Tarefa do service",
                "status": "em_andamento",
                "prioridade": "alta",
            }
        )
        ordem_anterior = _next_task_ordem(seed_data["project_id"])
        task = create_task_record(data, author=author)
        db.session.commit()
        task_id = task.id

    with app.app_context():
        persisted = db.session.get(Task, task_id)
        assert persisted.descricao == "Tarefa do service"
        assert persisted.status == "em_andamento"
        assert persisted.prioridade == "alta"
        assert persisted.project_id == seed_data["project_id"]
        assert persisted.etapa_id == seed_data["etapa_id"]
        assert persisted.created_by_id == seed_data["user_id"]
        assert persisted.ordem == ordem_anterior + 1


def test_create_task_record_avulsa_sem_projeto(app, seed_data):
    with app.test_request_context():
        author = db.session.get(User, seed_data["user_id"])
        g.user = author
        data, refusal = resolve_task_creation({"descricao": "Avulsa"})
        task = create_task_record(data, author=author)
        db.session.commit()
        task_id = task.id

    assert refusal is None
    with app.app_context():
        persisted = db.session.get(Task, task_id)
        assert persisted.project_id is None
        assert persisted.etapa_id is None


def test_allowed_assignee_ids_descarta_usuario_sem_acesso(app, seed_data):
    with app.test_request_context():
        g.user = db.session.get(User, seed_data["user_id"])
        project = db.session.get(Task, seed_data["task_id"]).project
        data = TaskCreationInput(
            descricao="Com responsaveis",
            project=project,
            assignee_ids=[seed_data["user_id"], seed_data["outsider_id"]],
        )
        allowed = _allowed_assignee_ids(data)

    assert seed_data["user_id"] in allowed
    assert seed_data["outsider_id"] not in allowed
