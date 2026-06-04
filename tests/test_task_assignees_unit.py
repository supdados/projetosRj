"""Testes unitários para os helpers de responsáveis (routes/tasks/queries).

``assignee_initials`` e ``serialize_assignee`` são puros (não dependem de Flask
nem de DB): recebem string/objeto-usuário e devolvem dados serializáveis. Por
isso todos os casos aqui rodam sem app context. A mutação ``set_task_assignees``
e a notificação são cobertas pela verificação de integração (browser + DB).
"""

from dataclasses import dataclass

from routes.tasks.queries import assignee_initials, serialize_assignee


@dataclass
class FakeUser:
    """Usuário falso nomeado para os testes de serialização (sem ORM/DB)."""

    id: int = 1
    name: str = "Alex Johnson"
    username: str = "ajohnson"
    orgao: str | None = "SETD"


# ── assignee_initials ─────────────────────────────────────────────────────────


def test_initials_two_names_uses_first_letter_of_each():
    assert assignee_initials("Alex Johnson") == "AJ"


def test_initials_three_names_uses_first_and_last():
    assert assignee_initials("Ana Paula Souza") == "AS"


def test_initials_single_name_uses_first_two_letters():
    assert assignee_initials("Maria") == "MA"


def test_initials_empty_or_whitespace_returns_placeholder():
    assert assignee_initials("") == "?"
    assert assignee_initials("   ") == "?"
    assert assignee_initials(None) == "?"


def test_initials_collapses_extra_spaces():
    assert assignee_initials("  Bruno   Lima  ") == "BL"


# ── serialize_assignee ────────────────────────────────────────────────────────


def test_serialize_assignee_full_shape():
    assert serialize_assignee(FakeUser()) == {
        "id": 1,
        "name": "Alex Johnson",
        "initials": "AJ",
        "subtitle": "SETD",
    }


def test_serialize_subtitle_falls_back_to_username_when_no_orgao():
    assert serialize_assignee(FakeUser(orgao=None))["subtitle"] == "@ajohnson"


def test_serialize_subtitle_falls_back_when_orgao_blank():
    assert serialize_assignee(FakeUser(orgao="   "))["subtitle"] == "@ajohnson"


def test_serialize_name_falls_back_to_username_and_initials_from_it():
    out = serialize_assignee(FakeUser(name=""))
    assert out["name"] == "ajohnson"
    assert out["initials"] == "AJ"
