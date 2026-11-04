"""Guardas da inclusão de projeto em coleção (``adicionar_projeto``).

Extraído de ``services/project_collections.py`` (já acima de 500 linhas) por
ser regra de CURADORIA, não de CRUD da coleção:

- ``exigir_editor_apos_inclusao``: o papel é decidido no gate, ANTES do INSERT;
  uma revogação/rebaixamento que commite entre o gate e o INSERT poda sem
  enxergar o item, que nasceria órfão (expondo o projeto sem ninguém
  autorizado por trás). Relê o papel DEPOIS de gravar e desfaz pela rota.
- ``reincluir_item``: re-incluir o MESMO projeto era no-op silencioso; quem
  incluiu com teto baixo (ex.: 0, projeto visto só por convite) e depois
  ganhou área ficava preso — o item nunca passava a ser visto pelos membros.

Não commita (a rota commita/desfaz via ``mutar``).
"""

from __future__ import annotations

from sqlalchemy import update

from models import (
    PAPEL_SHARE_EDITOR,
    TIPO_COLECAO_CUSTOM,
    ProjectCollection,
    ProjectCollectionItem,
    User,
    db,
)
from services.authorization import invalidate_collection_rank_cache
from services.collection_access import incluidor_do_item
from services.collection_errors import ColecaoSemPermissao, ConviteIndisponivel
from services.collection_participation import papeis_validos_por_colecao
from services.collection_shares import auditar_item_se_compartilhada


def exigir_editor_apos_inclusao(colecao: ProjectCollection, ator: User) -> None:
    """Revalida, já com o item gravado, que o ator NÃO-dono segue editor.

    Rebaixado no meio → ``ColecaoSemPermissao`` (403); sem papel nenhum
    (revogado, saiu) → ``ConviteIndisponivel`` (o MESMO 404 de
    ``carregar_acesso``: revogado é indistinguível de inexistente). Nos dois
    casos a rota faz rollback e o item não nasce. Releitura SEM trava: no
    SQLite a transação só começa no INSERT e enxerga o commit concorrente; no
    MySQL (REPEATABLE READ) ela lê o snapshot da 1ª leitura do request, então
    lá a janela continua — o item que escapar vira órfão, aparece em
    ``itens_orfaos`` e sai na próxima poda. Exemplo:
    ``exigir_editor_apos_inclusao(colecao, g.user)`` logo após o ``add``.
    """
    if ator.id == colecao.owner_user_id:
        return
    db.session.flush()
    # Direto do banco (o papel não passa pelo cache de rank do request).
    papel = papeis_validos_por_colecao(ator, [colecao.id]).get(colecao.id)
    if papel == PAPEL_SHARE_EDITOR:
        return
    if papel is None:
        raise ConviteIndisponivel(
            f"usuário id={ator.id} perdeu o acesso à coleção id={colecao.id} "
            "durante a inclusão (revogado ou saiu); esperado papel 'editor'"
        )
    raise ColecaoSemPermissao(
        f"papel do usuário id={ator.id} na coleção id={colecao.id} mudou durante "
        f"a inclusão: {papel!r}; esperado {PAPEL_SHARE_EDITOR!r}"
    )


def reincluir_item(
    colecao: ProjectCollection,
    item: ProjectCollectionItem,
    ator: User,
    teto: int,
) -> bool:
    """Re-inclusão idempotente: sobe ``rank_teto`` para max(atual, ``teto``).

    Só para quem incluiu o item (o dono responde pelo item próprio/legado);
    item de outra pessoa fica intocado. Legado (NULL = editor) já é o máximo.
    ``True`` quando o teto subiu (cache invalidado, trilha registrada).
    Exemplo: ``reincluir_item(colecao, existente, g.user, teto_de_agora)``.
    """
    if colecao.tipo != TIPO_COLECAO_CUSTOM:
        return False
    if incluidor_do_item(item.added_by_user_id, colecao.owner_user_id) != ator.id:
        return False
    if item.rank_teto is None or item.rank_teto >= teto or not _subir_teto(item, teto):
        return False
    exigir_editor_apos_inclusao(colecao, ator)
    auditar_item_se_compartilhada(
        colecao, item.project_id, "colecao_projeto_adicionado", ator
    )
    invalidate_collection_rank_cache()
    return True


def _subir_teto(item: ProjectCollectionItem, teto: int) -> bool:
    # Condicional: item podado por um request concorrente casa 0 linhas (nada
    # a subir) em vez de virar StaleDataError (500) no flush ORM.
    resultado = db.session.execute(
        update(ProjectCollectionItem)
        .where(
            ProjectCollectionItem.id == item.id,
            ProjectCollectionItem.rank_teto < teto,
        )
        .values(rank_teto=teto)
    )
    return resultado.rowcount == 1
