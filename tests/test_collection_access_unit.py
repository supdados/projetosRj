"""Predicado único de acesso via coleção (services/collection_access.py).

Duas metades:

- Funções PURAS da regra (validade do share pela resposta, teto do item, item
  próprio, ramo do dono, quem remove) — sem banco.
- EQUIVALÊNCIA rank map (Python sobre candidatos) ⇔ EXISTS correlacionado
  (SQL das listagens) para TODOS os estados da spec: legado, pendente, aceito,
  recusado, saiu, revogado, órgão com membro aceito/pendente, teto 0, teto
  leitor, item próprio, dono derivando de item alheio — mais dono removido,
  Favoritos e o dono alcançado pelo próprio share de órgão. Divergir as duas
  formas é vazamento: toda listagem usa o EXISTS, todo gate usa o rank map.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from models import (
    PAPEL_SHARE_EDITOR,
    PAPEL_SHARE_VIEWER,
    STATUS_RESPOSTA_ACEITO,
    STATUS_RESPOSTA_RECUSADO,
    STATUS_RESPOSTA_SAIU,
    TIPO_COLECAO_CUSTOM,
    TIPO_COLECAO_FAVORITOS,
    OrgaoUnidade,
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    ProjectCollectionShare,
    ProjectCollectionShareResposta,
    User,
    UserOrgao,
    db,
)
from services.collection_access import (
    RANK_EDITOR,
    RANK_LEITOR,
    STATUS_LEGADO,
    STATUS_PENDENTE,
    CandidatoDoDono,
    CandidatoViaShare,
    construir_rank_map_de_colecoes,
    incluidor_do_item,
    papel_share_mais_alto,
    papel_share_rank,
    pode_remover_item,
    rank_teto_de_inclusao,
    rank_via_dono,
    rank_via_share,
    share_alcanca_usuario,
    share_pendente,
    share_vale,
    status_do_destinatario,
    teto_do_item,
    visibilidade_via_colecao_criterion,
)
from services.orgao_tree import rebuild_orgao_closure
from time_utils import utc_now

ME = 7
DONO = 3


# ── Fakes nomeados (regra pura) ───────────────────────────────────────────────


class FakeVinculo:
    """Substitui ``UserOrgao``: a regra só lê ``orgao_id``."""

    def __init__(self, orgao_id: int) -> None:
        self.orgao_id = orgao_id


class FakeUsuario:
    """Substitui ``User``: a regra só lê ``id`` e ``orgaos``."""

    def __init__(self, user_id: int, orgao_ids: tuple[int, ...] = ()) -> None:
        self.id = user_id
        self.orgaos = [FakeVinculo(orgao_id) for orgao_id in orgao_ids]


class FakeShare:
    """Substitui ``ProjectCollectionShare``: só ``user_id``/``orgao_id``."""

    def __init__(self, *, user_id: int | None = None, orgao_id: int | None = None):
        self.user_id = user_id
        self.orgao_id = orgao_id


def _via_share(**campos: object) -> CandidatoViaShare:
    base: dict[str, object] = {
        "project_id": 1,
        "rank_teto": None,
        "added_by_user_id": None,
        "owner_user_id": DONO,
        "tipo": TIPO_COLECAO_CUSTOM,
        "dono_vivo": True,
        "papel": PAPEL_SHARE_EDITOR,
        "exige_aceite": True,
        "status_resposta": STATUS_RESPOSTA_ACEITO,
    }
    base.update(campos)
    return CandidatoViaShare(**base)


def _do_dono(**campos: object) -> CandidatoDoDono:
    base: dict[str, object] = {
        "project_id": 1,
        "rank_teto": None,
        "added_by_user_id": 99,
        "owner_user_id": ME,
        "tipo": TIPO_COLECAO_CUSTOM,
    }
    base.update(campos)
    return CandidatoDoDono(**base)


# ── Regra pura ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("exige_aceite", "status", "vale", "pendente", "rotulo"),
    [
        (False, None, True, False, STATUS_LEGADO),
        (True, None, False, True, STATUS_PENDENTE),
        (True, STATUS_RESPOSTA_ACEITO, True, False, STATUS_RESPOSTA_ACEITO),
        (True, STATUS_RESPOSTA_RECUSADO, False, False, STATUS_RESPOSTA_RECUSADO),
        (True, STATUS_RESPOSTA_SAIU, False, False, STATUS_RESPOSTA_SAIU),
        (False, STATUS_RESPOSTA_SAIU, False, False, STATUS_RESPOSTA_SAIU),
        (True, "desconhecido", False, False, "desconhecido"),
    ],
)
def test_validade_do_share_pela_resposta(exige_aceite, status, vale, pendente, rotulo):
    """Status desconhecido falha FECHADO (nem vale, nem pendente)."""
    assert share_vale(exige_aceite, status) is vale
    assert share_pendente(exige_aceite, status) is pendente
    assert status_do_destinatario(exige_aceite, status) == rotulo


@pytest.mark.parametrize(
    ("rank_teto", "esperado"),
    [(None, RANK_EDITOR), (0, 0), (10, 10), (20, 20), (30, 20), (100, 20), (-5, 0)],
)
def test_teto_do_item_nunca_passa_de_editor(rank_teto, esperado):
    assert teto_do_item(rank_teto) == esperado


@pytest.mark.parametrize(("area", "gravado"), [(0, 0), (10, 10), (30, 20), (100, 20)])
def test_rank_teto_de_inclusao_limita_o_rank_de_area(area, gravado):
    assert rank_teto_de_inclusao(area) == gravado


def test_papel_do_share_e_o_mais_alto():
    assert papel_share_rank(PAPEL_SHARE_EDITOR) == RANK_EDITOR
    assert papel_share_rank(PAPEL_SHARE_VIEWER) == RANK_LEITOR
    assert papel_share_rank("gestor") == RANK_LEITOR  # adulterado nunca sobe
    assert papel_share_mais_alto(PAPEL_SHARE_VIEWER, PAPEL_SHARE_EDITOR) == (
        PAPEL_SHARE_EDITOR
    )
    assert papel_share_mais_alto(None, PAPEL_SHARE_VIEWER) == PAPEL_SHARE_VIEWER
    assert papel_share_mais_alto(None, None) is None


def test_incluidor_legado_e_o_dono():
    assert incluidor_do_item(None, DONO) == DONO
    assert incluidor_do_item(ME, DONO) == ME


def test_alcance_por_pessoa_e_por_orgao_exato():
    usuario = FakeUsuario(ME, orgao_ids=(40,))
    assert share_alcanca_usuario(FakeShare(user_id=ME), usuario) is True
    assert share_alcanca_usuario(FakeShare(user_id=ME + 1), usuario) is False
    assert share_alcanca_usuario(FakeShare(orgao_id=40), usuario) is True
    assert share_alcanca_usuario(FakeShare(orgao_id=41), usuario) is False


@pytest.mark.parametrize(
    ("campos", "esperado"),
    [
        ({}, RANK_EDITOR),
        ({"papel": PAPEL_SHARE_VIEWER}, RANK_LEITOR),
        ({"rank_teto": 10}, RANK_LEITOR),
        ({"rank_teto": 0}, 0),
        ({"exige_aceite": True, "status_resposta": None}, 0),
        ({"exige_aceite": False, "status_resposta": None}, RANK_EDITOR),
        ({"status_resposta": STATUS_RESPOSTA_RECUSADO}, 0),
        ({"status_resposta": STATUS_RESPOSTA_SAIU}, 0),
        ({"added_by_user_id": ME}, 0),
        ({"owner_user_id": ME}, 0),
        ({"dono_vivo": False}, 0),
        ({"tipo": TIPO_COLECAO_FAVORITOS}, 0),
    ],
)
def test_rank_via_share(campos, esperado):
    assert rank_via_share(_via_share(**campos), ME) == esperado


@pytest.mark.parametrize(
    ("campos", "esperado"),
    [
        ({}, RANK_LEITOR),
        ({"rank_teto": 0}, 0),
        ({"rank_teto": 20}, RANK_LEITOR),
        ({"added_by_user_id": None}, 0),
        ({"added_by_user_id": ME}, 0),
        ({"owner_user_id": DONO}, 0),
        ({"tipo": TIPO_COLECAO_FAVORITOS}, 0),
    ],
)
def test_rank_via_dono_so_le_o_que_outros_incluiram(campos, esperado):
    assert rank_via_dono(_do_dono(**campos), ME) == esperado


@pytest.mark.parametrize(
    ("papel", "added_by", "esperado"),
    [
        ("dono", None, True),
        ("dono", 99, True),
        (PAPEL_SHARE_EDITOR, ME, True),
        (PAPEL_SHARE_EDITOR, 99, False),
        (PAPEL_SHARE_EDITOR, None, False),
        (PAPEL_SHARE_VIEWER, ME, False),
        (None, ME, False),
    ],
)
def test_pode_remover_item(papel, added_by, esperado):
    assert pode_remover_item(papel, added_by, ME) is esperado


# ── Equivalência rank map ⇔ EXISTS ────────────────────────────────────────────


@dataclass
class _Mundo:
    usuarios: dict[str, User]
    projetos: dict[str, int]


def _orgao(sigla: str) -> OrgaoUnidade:
    orgao = OrgaoUnidade(sigla=sigla, nome=sigla, tipo="Secretaria", ordem=0)
    db.session.add(orgao)
    db.session.flush()
    return orgao


def _usuario(nome: str, orgao: OrgaoUnidade | None = None) -> User:
    user = User(username=nome, name=nome.upper(), password_hash="x")
    db.session.add(user)
    db.session.flush()
    if orgao is not None:
        db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao.id, papel="gestor"))
        db.session.flush()
    return user


def _colecao_com_item(
    dono: User,
    projeto: Project,
    *,
    nome: str,
    added_by: User | None,
    rank_teto: int | None,
    tipo: str = TIPO_COLECAO_CUSTOM,
) -> ProjectCollection:
    colecao = ProjectCollection(owner_user_id=dono.id, nome=nome, tipo=tipo)
    db.session.add(colecao)
    db.session.flush()
    db.session.add(
        ProjectCollectionItem(
            collection_id=colecao.id,
            project_id=projeto.id,
            added_by_user_id=added_by.id if added_by else None,
            rank_teto=rank_teto,
        )
    )
    db.session.flush()
    return colecao


def _share(
    colecao: ProjectCollection,
    *,
    papel: str = PAPEL_SHARE_VIEWER,
    exige_aceite: bool = True,
    user: User | None = None,
    orgao: OrgaoUnidade | None = None,
) -> ProjectCollectionShare:
    share = ProjectCollectionShare(
        collection_id=colecao.id,
        user_id=user.id if user else None,
        orgao_id=orgao.id if orgao else None,
        papel=papel,
        created_by_user_id=colecao.owner_user_id,
        exige_aceite=exige_aceite,
    )
    db.session.add(share)
    db.session.flush()
    return share


def _responde(share: ProjectCollectionShare, user: User, status: str) -> None:
    db.session.add(
        ProjectCollectionShareResposta(
            share_id=share.id, user_id=user.id, status=status
        )
    )
    db.session.flush()


def _projeto(titulo: str, orgao: OrgaoUnidade) -> Project:
    projeto = Project(titulo=titulo, orgao_id=orgao.id, status="Vigente")
    db.session.add(projeto)
    db.session.flush()
    return projeto


_NOMES_PROJETOS = (
    "legado", "pendente", "aceito", "recusado", "saiu", "revogado", "orgao",
    "teto0", "teto_leitor", "dono_alheio", "dono_teto0", "dono_morto",
    "favoritos", "auto",
)  # fmt: skip


def _item(dono: User, projeto: Project, nome: str, **campos: object):
    campos.setdefault("added_by", dono)
    campos.setdefault("rank_teto", 20)
    return _colecao_com_item(dono, projeto, nome=nome, **campos)


def _estados_de_resposta(dono: User, leitor: User, p: dict[str, Project]) -> None:
    _share(_item(dono, p["legado"], "legado", added_by=None, rank_teto=None),
           user=leitor, exige_aceite=False)  # fmt: skip
    _share(_item(dono, p["pendente"], "pendente"), user=leitor)
    aceito = _share(_item(dono, p["aceito"], "aceito"), user=leitor,
                    papel=PAPEL_SHARE_EDITOR)  # fmt: skip
    _responde(aceito, leitor, STATUS_RESPOSTA_ACEITO)
    recusado = _share(_item(dono, p["recusado"], "recusado"), user=leitor)
    _responde(recusado, leitor, STATUS_RESPOSTA_RECUSADO)
    saiu = _share(_item(dono, p["saiu"], "saiu"), user=leitor, exige_aceite=False)
    _responde(saiu, leitor, STATUS_RESPOSTA_SAIU)
    revogado = _share(_item(dono, p["revogado"], "revogado"), user=leitor)
    _responde(revogado, leitor, STATUS_RESPOSTA_ACEITO)
    ProjectCollectionShareResposta.query.filter_by(share_id=revogado.id).delete()
    db.session.delete(revogado)


def _estados_de_orgao_e_teto(
    dono: User, leitor: User, membro: User, orgao_x: OrgaoUnidade,
    p: dict[str, Project],
) -> None:  # fmt: skip
    do_orgao = _share(_item(dono, p["orgao"], "orgao"), orgao=orgao_x)
    _responde(do_orgao, membro, STATUS_RESPOSTA_ACEITO)
    for nome, teto in (("teto0", 0), ("teto_leitor", 10)):
        share = _share(_item(dono, p[nome], nome, rank_teto=teto), user=leitor,
                       papel=PAPEL_SHARE_EDITOR)  # fmt: skip
        _responde(share, leitor, STATUS_RESPOSTA_ACEITO)


def _estados_de_autoria(
    dono: User, leitor: User, editor: User, area_dono: OrgaoUnidade,
    p: dict[str, Project], p_ext: Project,
) -> None:  # fmt: skip
    # Item próprio: o editor incluiu; ele não deriva, o leitor deriva.
    colecao = _item(dono, p_ext, "proprio", added_by=editor)
    for pessoa in (editor, leitor):
        share = _share(colecao, user=pessoa, papel=PAPEL_SHARE_EDITOR)
        _responde(share, pessoa, STATUS_RESPOSTA_ACEITO)
    # Dono lê o que o editor incluiu (teto 20 → leitor; teto 0 → nada).
    colecao = _item(dono, p["dono_alheio"], "dono_alheio", added_by=editor)
    db.session.add(ProjectCollectionItem(
        collection_id=colecao.id, project_id=p["dono_teto0"].id,
        added_by_user_id=editor.id, rank_teto=0,
    ))  # fmt: skip
    # Favoritos nunca concede, nem com item "alheio" adulterado.
    _item(dono, p["favoritos"], "Favoritos", added_by=editor,
          tipo=TIPO_COLECAO_FAVORITOS)  # fmt: skip
    # Dono alcançado pelo PRÓPRIO share de órgão legado: não deriva por ele.
    _share(_item(dono, p["auto"], "auto", added_by=editor), orgao=area_dono,
           exige_aceite=False, papel=PAPEL_SHARE_EDITOR)  # fmt: skip


def _estado_dono_removido(leitor: User, area: OrgaoUnidade, projeto: Project):
    morto = _usuario("dono_morto", area)
    _share(_item(morto, projeto, "morto", added_by=None, rank_teto=None),
           user=leitor, exige_aceite=False)  # fmt: skip
    morto.deleted_at = utc_now()


def _semear_estados() -> _Mundo:
    area_dono, area_ext, orgao_x = _orgao("DONO"), _orgao("EXT"), _orgao("ORGX")
    rebuild_orgao_closure()
    usuarios = {
        "dono": _usuario("dono", area_dono),
        "leitor": _usuario("leitor", area_ext),
        "editor": _usuario("editor", area_ext),
        "membro_aceito": _usuario("membro_aceito", orgao_x),
        "membro_pendente": _usuario("membro_pendente", orgao_x),
    }
    dono, leitor = usuarios["dono"], usuarios["leitor"]
    p = {nome: _projeto(nome, area_dono) for nome in _NOMES_PROJETOS}
    p_ext = _projeto("do_editor", area_ext)
    _estados_de_resposta(dono, leitor, p)
    _estados_de_orgao_e_teto(dono, leitor, usuarios["membro_aceito"], orgao_x, p)
    _estados_de_autoria(dono, leitor, usuarios["editor"], area_dono, p, p_ext)
    _estado_dono_removido(leitor, area_dono, p["dono_morto"])
    db.session.commit()
    projetos = {nome: projeto.id for nome, projeto in p.items()}
    projetos["do_editor"] = p_ext.id
    return _Mundo(usuarios=usuarios, projetos=projetos)


def _visiveis_por_exists(user: User) -> set[int]:
    rows = db.session.query(Project.id).filter(visibilidade_via_colecao_criterion(user))
    return {project_id for (project_id,) in rows}


@pytest.fixture
def mundo(app):
    with app.app_context():
        yield _semear_estados()


def test_rank_map_e_exists_sao_equivalentes_em_todos_os_estados(app, mundo):
    with app.test_request_context("/"):
        for nome, user in mundo.usuarios.items():
            rank_map = construir_rank_map_de_colecoes(user)
            assert all(rank > 0 for rank in rank_map.values()), nome
            assert set(rank_map) == _visiveis_por_exists(user), nome


def test_rank_derivado_de_cada_estado(app, mundo):
    """Trava os valores, não só a equivalência."""
    with app.test_request_context("/"):
        p = mundo.projetos
        assert construir_rank_map_de_colecoes(mundo.usuarios["leitor"]) == {
            p["legado"]: RANK_LEITOR,
            p["aceito"]: RANK_EDITOR,
            p["teto_leitor"]: RANK_LEITOR,
            p["do_editor"]: RANK_EDITOR,
        }
        assert construir_rank_map_de_colecoes(mundo.usuarios["membro_aceito"]) == {
            p["orgao"]: RANK_LEITOR
        }
        assert construir_rank_map_de_colecoes(mundo.usuarios["membro_pendente"]) == {}
        # Editor: não deriva do item que ELE incluiu.
        assert construir_rank_map_de_colecoes(mundo.usuarios["editor"]) == {}
        # Dono: lê o que o editor incluiu (até o teto), nunca por share próprio.
        assert construir_rank_map_de_colecoes(mundo.usuarios["dono"]) == {
            p["dono_alheio"]: RANK_LEITOR,
            p["auto"]: RANK_LEITOR,
            p["do_editor"]: RANK_LEITOR,
        }
