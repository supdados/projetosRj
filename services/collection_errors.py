"""Erros de domínio e guardas comuns das coleções de projetos.

Folha sem dependência de service: ``services.project_collections`` importa
``services.collection_shares``, e ambos levantam os MESMOS erros — morar aqui
evita o ciclo. A rota (``routes/api/collections.py::_erro_de_colecao``) traduz
pela hierarquia: ``ProjetoForaDoEscopo`` (e subclasses) → 404 anti-enumeração,
``ColecaoSemPermissao`` → 403, o resto de ``ColecaoInvalida`` → 422.
"""

from __future__ import annotations

from models import TIPO_COLECAO_FAVORITOS, ProjectCollection, User

PAPEL_COLECAO_DONO = "dono"


class ColecaoInvalida(ValueError):
    """Payload de coleção recusado (nome, ícone/cor, limite, Favoritos)."""


class ProjetoForaDoEscopo(ColecaoInvalida):
    """Projeto inexistente OU invisível ao ator — a rota mapeia para 404."""


class ConviteIndisponivel(ProjetoForaDoEscopo):
    """Sem convite pendente/participação para o ator — MESMO 404 da rota.

    Coleção inexistente, sem convite para mim, convite revogado, já respondido
    ou perdido numa corrida são indistinguíveis de fora (anti-enumeração):
    herda de ``ProjetoForaDoEscopo`` justamente para cair no ``fail_not_found``.
    """


class ColecaoSemPermissao(ColecaoInvalida):
    """Ator VÊ a coleção mas o papel não cobre a ação — a rota mapeia para 403."""


class ProjetoSoPorConvite(ColecaoInvalida):
    """Editor tentou incluir projeto que só vê por convite de projeto (422).

    Incluir exporia a N pessoas um projeto que o editor recebeu pontualmente,
    contornando "só gestor convida" (decisão 3 da spec).
    """


def bloquear_favoritos(colecao: ProjectCollection, acao: str) -> None:
    """Favoritos é coleção de sistema: nem editar, apagar ou compartilhar.

    Exemplo: ``bloquear_favoritos(colecao, "compartilhar")``.
    """
    if colecao.tipo != TIPO_COLECAO_FAVORITOS:
        return
    raise ColecaoInvalida(
        f"não é possível {acao} a coleção Favoritos (coleção de sistema)"
    )


def exigir_dono(colecao: ProjectCollection, ator: User) -> None:
    """Gestão de shares/convites é privativa do dono (403 para os demais).

    Exemplo: ``exigir_dono(colecao, g.user)``.
    """
    if colecao.owner_user_id == ator.id:
        return
    raise ColecaoSemPermissao(
        f"somente o dono gerencia compartilhamentos da coleção id={colecao.id}"
    )
