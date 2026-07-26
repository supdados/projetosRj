"""Helper de resolução de órgão a partir do form de projeto.

As rotas Jinja de CRUD de projeto (``add_project``/``delete_project``/
``concluir_project``) foram cortadas na migração SPA — o CRUD vive em
``/api/projetos*`` (envelope). Resta apenas ``_resolve_orgao_from_form``,
importado por ``routes/api/projects_write.py``.
"""

from flask import g

from models import OrgaoUnidade, db
from services.authorization import can_assign_project_to_orgao


def _resolve_orgao_from_form(form_value, *, current_orgao_id=None):
    """Parseia project_orgao_id do form e valida o rank no orgao DESTINO.

    Retorna ``(orgao_unidade, erro_msg)`` - um deles sempre None.
    - Condicao (a) da §5.4: rank >= editor no destino via vinculo de area
      (``can_assign_project_to_orgao``); admin sempre pode.
    - Orgaos inativos são rejeitados — exceto quando ``current_orgao_id`` aponta para
      eles (caso de edição de projeto legado vinculado a orgao desligado): nesse
      cenário preservamos o vínculo se o admin não mexeu no campo.
    """
    if not form_value:
        return None, "Você deve selecionar um órgão para o projeto."
    try:
        orgao_id = int(form_value)
    except (TypeError, ValueError):
        return None, "Órgão inválido."
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None:
        return None, "Órgão não encontrado."
    if not can_assign_project_to_orgao(g.user, orgao_id):
        return (
            None,
            "Você não tem permissão para criar/editar projetos neste órgão.",
        )
    if not orgao.ativo and orgao_id != current_orgao_id:
        return None, "Este órgão está inativo e não pode receber novos projetos."
    return orgao, None
