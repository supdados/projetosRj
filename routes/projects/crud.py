"""Helper de resolução de órgão a partir do form de projeto.

As rotas Jinja de CRUD de projeto (``add_project``/``delete_project``/
``concluir_project``) foram cortadas na migração SPA — o CRUD vive em
``/api/projetos*`` (envelope). Resta apenas ``_resolve_orgao_from_form``,
importado por ``routes/api/projects_write.py``.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

from flask import g

from models import OrgaoUnidade, db
from services.authorization import can_assign_project_to_orgao

OrgaoErrorCode = Literal["forbidden", "not_found", "validation"]


class OrgaoResolutionError(NamedTuple):
    """Falha tipada da resolução de órgão: código estável + mensagem ao usuário.

    O código existe para o caller escolher o status HTTP sem inspecionar a
    mensagem (``"permissão" in msg``).

    Exemplo:
        >>> OrgaoResolutionError("forbidden", "Sem permissão.").code
        'forbidden'
    """

    code: OrgaoErrorCode
    message: str


def _resolve_orgao_from_form(
    form_value: object, *, current_orgao_id: int | None = None
) -> tuple[OrgaoUnidade | None, OrgaoResolutionError | None]:
    """Parseia project_orgao_id do form e valida o rank no orgao DESTINO.

    Retorna ``(orgao_unidade, erro)`` - um deles sempre None; ``erro`` é um
    ``OrgaoResolutionError`` (``code`` + ``message``).
    - Condicao (a) da §5.4: rank >= editor no destino via vinculo de area
      (``can_assign_project_to_orgao``); admin sempre pode.
    - Orgaos inativos são rejeitados — exceto quando ``current_orgao_id`` aponta para
      eles (caso de edição de projeto legado vinculado a orgao desligado): nesse
      cenário preservamos o vínculo se o admin não mexeu no campo.
    """
    if not form_value:
        return None, OrgaoResolutionError(
            "validation", "Você deve selecionar um órgão para o projeto."
        )
    try:
        orgao_id = int(form_value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, OrgaoResolutionError("validation", "Órgão inválido.")
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None:
        return None, OrgaoResolutionError("not_found", "Órgão não encontrado.")
    if not can_assign_project_to_orgao(g.user, orgao_id):
        return None, OrgaoResolutionError(
            "forbidden",
            "Você não tem permissão para criar/editar projetos neste órgão.",
        )
    if not orgao.ativo and orgao_id != current_orgao_id:
        return None, OrgaoResolutionError(
            "validation", "Este órgão está inativo e não pode receber novos projetos."
        )
    return orgao, None
