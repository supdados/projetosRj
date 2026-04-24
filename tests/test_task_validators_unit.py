"""Testes unitários para routes/tasks/validators.py.

``extract_edit_inputs`` não depende de Flask context: recebe form e payload
como dicts, portanto todos os casos aqui são testes puros sem DB nem app.
"""

from dataclasses import dataclass

from routes.tasks.validators import extract_edit_inputs

# ── FakeTask ──────────────────────────────────────────────────────────────────


@dataclass
class FakeTask:
    descricao: str = "Desc atual"
    status: str = "nao_iniciada"
    responsavel: str | None = None
    prioridade: str | None = None
    tipo_pedido: str | None = None


# ── descricao ─────────────────────────────────────────────────────────────────


def test_extract_descricao_from_form():
    inputs = extract_edit_inputs(FakeTask(), {"descricao": "Form desc"}, {})
    assert inputs.descricao == "Form desc"


def test_extract_descricao_from_payload_when_absent_in_form():
    inputs = extract_edit_inputs(FakeTask(), {}, {"descricao": "Payload desc"})
    assert inputs.descricao == "Payload desc"


def test_extract_descricao_falls_back_to_titulo_in_form():
    inputs = extract_edit_inputs(FakeTask(), {"titulo": "Titulo form"}, {})
    assert inputs.descricao == "Titulo form"


def test_extract_descricao_falls_back_to_task_descricao():
    task = FakeTask(descricao="Descricao da tarefa")
    inputs = extract_edit_inputs(task, {}, {})
    assert inputs.descricao == "Descricao da tarefa"


def test_extract_descricao_strips_whitespace():
    inputs = extract_edit_inputs(FakeTask(), {"descricao": "  Texto  "}, {})
    assert inputs.descricao == "Texto"


def test_extract_form_descricao_wins_over_payload():
    inputs = extract_edit_inputs(
        FakeTask(), {"descricao": "Form"}, {"descricao": "Payload"}
    )
    assert inputs.descricao == "Form"


# ── status ────────────────────────────────────────────────────────────────────


def test_extract_valid_status_from_form():
    inputs = extract_edit_inputs(FakeTask(), {"status": "em_andamento"}, {})
    assert inputs.status == "em_andamento"


def test_extract_invalid_status_falls_back_to_task_status():
    task = FakeTask(status="para_validacao")
    inputs = extract_edit_inputs(task, {"status": "invalido"}, {})
    assert inputs.status == "para_validacao"


def test_extract_status_falls_back_to_task_when_absent():
    task = FakeTask(status="para_ajustes")
    inputs = extract_edit_inputs(task, {}, {})
    assert inputs.status == "para_ajustes"


# ── responsavel ───────────────────────────────────────────────────────────────


def test_extract_responsavel_from_form():
    inputs = extract_edit_inputs(FakeTask(), {"responsavel": "Ana Silva"}, {})
    assert inputs.responsavel_raw == "Ana Silva"


def test_extract_responsavel_falls_back_to_task_when_key_absent():
    task = FakeTask(responsavel="Bruno Costa")
    inputs = extract_edit_inputs(task, {}, {})
    assert inputs.responsavel_raw == "Bruno Costa"


def test_extract_responsavel_uses_empty_string_when_key_present_but_empty():
    task = FakeTask(responsavel="Carlos")
    inputs = extract_edit_inputs(task, {"responsavel": ""}, {})
    assert inputs.responsavel_raw == ""


def test_extract_responsavel_from_payload_when_absent_in_form():
    inputs = extract_edit_inputs(FakeTask(), {}, {"responsavel": "Diana"})
    assert inputs.responsavel_raw == "Diana"


# ── prioridade ────────────────────────────────────────────────────────────────


def test_extract_valid_prioridade_from_form():
    inputs = extract_edit_inputs(FakeTask(), {"prioridade": "alta"}, {})
    assert inputs.prioridade == "alta"


def test_extract_invalid_prioridade_becomes_none():
    inputs = extract_edit_inputs(FakeTask(), {"prioridade": "maxima"}, {})
    assert inputs.prioridade is None


def test_extract_prioridade_falls_back_to_task_when_key_absent():
    task = FakeTask(prioridade="urgente")
    inputs = extract_edit_inputs(task, {}, {})
    assert inputs.prioridade == "urgente"


def test_extract_empty_prioridade_becomes_none():
    inputs = extract_edit_inputs(FakeTask(), {"prioridade": ""}, {})
    assert inputs.prioridade is None


# ── tipo_pedido ───────────────────────────────────────────────────────────────


def test_extract_valid_tipo_from_form():
    inputs = extract_edit_inputs(FakeTask(), {"tipo_pedido": "bug"}, {})
    assert inputs.tipo_pedido == "bug"


def test_extract_invalid_tipo_becomes_none():
    inputs = extract_edit_inputs(FakeTask(), {"tipo_pedido": "desconhecido"}, {})
    assert inputs.tipo_pedido is None


def test_extract_tipo_falls_back_to_task_when_key_absent():
    task = FakeTask(tipo_pedido="melhoria")
    inputs = extract_edit_inputs(task, {}, {})
    assert inputs.tipo_pedido == "melhoria"


def test_extract_legacy_tipo_preserved_when_task_is_also_legacy():
    task = FakeTask(tipo_pedido="implementacao")
    inputs = extract_edit_inputs(task, {"tipo_pedido": "implementacao"}, {})
    assert inputs.tipo_pedido == "implementacao"


def test_extract_legacy_tipo_becomes_none_when_task_is_not_legacy():
    task = FakeTask(tipo_pedido="bug")
    inputs = extract_edit_inputs(task, {"tipo_pedido": "implementacao"}, {})
    assert inputs.tipo_pedido is None


# ── project_raw ───────────────────────────────────────────────────────────────


def test_extract_project_raw_from_form():
    inputs = extract_edit_inputs(FakeTask(), {"project": "token-abc"}, {})
    assert inputs.project_raw == "token-abc"


def test_extract_project_raw_none_when_absent():
    inputs = extract_edit_inputs(FakeTask(), {}, {})
    assert inputs.project_raw is None


def test_extract_project_raw_from_project_id_key():
    inputs = extract_edit_inputs(FakeTask(), {"project_id": "id-xyz"}, {})
    assert inputs.project_raw == "id-xyz"


def test_extract_project_raw_form_wins_over_payload():
    inputs = extract_edit_inputs(
        FakeTask(), {"project": "form-tok"}, {"project": "payload-tok"}
    )
    assert inputs.project_raw == "form-tok"
