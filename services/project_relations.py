"""Regras de domínio dos vínculos simétricos entre projetos.

Domínio de ``ProjectRelation``: canonicalização ``low < high``, teto de
vínculos contado SÓ no projeto de origem, remoção idempotente e leitura com
filtro de visibilidade do viewer. O service NÃO commita: valida, muta a sessão
e deixa o commit/rollback para a rota — padrão ``services/project_collections``.

Histórico (``log_project_action``) é gravado SOMENTE no projeto de origem; os
action types entram em ``IGNORED_PROJECT_ACTION_TYPES`` (sem notificações).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from models import Project, ProjectRelation, User, db
from routes.shared import log_project_action
from services.authorization import apply_project_visibility

RELATED_MAX_PER_PROJECT = 12


class RelacaoInvalida(ValueError):
    """Payload de vínculo recusado (auto-vínculo, duplicata, teto) — 422."""


class RelacaoForaDoEscopo(RelacaoInvalida):
    """Projeto inexistente OU invisível ao ator — a rota mapeia para 404."""


class RelacaoSemPermissao(RelacaoInvalida):
    """Ator vê o projeto mas o papel não cobre a ação — a rota mapeia para 403."""


def relacionar_projetos(origem: Project, alvo: Project, ator: User) -> ProjectRelation:
    """Cria o vínculo origem~alvo (linha canônica única); erros de domínio em 422.

    Exemplo: ``relacionar_projetos(projeto_a, projeto_b, g.user)``.
    """
    low_id, high_id = _par_canonico(origem.id, alvo.id)
    _exigir_cota_da_origem(origem)
    if _relacao_existente(low_id, high_id) is not None:
        raise RelacaoInvalida(
            f"vínculo já existe entre os projetos {low_id} e {high_id}; "
            "esperado par ainda não relacionado"
        )
    relacao = _inserir_relacao(low_id, high_id, ator)
    _log_vinculo(
        origem, "relacionar_projeto", f'Relacionou o projeto "{alvo.titulo}"', ator
    )
    return relacao


def desrelacionar_projetos(
    origem: Project, related_project_id: int, ator: User
) -> bool:
    """Remove o vínculo se existir (idempotente). ``False`` → 404 na rota."""
    low_id = min(origem.id, related_project_id)
    high_id = max(origem.id, related_project_id)
    relacao = _relacao_existente(low_id, high_id)
    if relacao is None:
        return False
    db.session.delete(relacao)
    _log_vinculo(
        origem,
        "desrelacionar_projeto",
        f"Desfez o vínculo com o projeto id={related_project_id}",
        ator,
    )
    return True


def listar_relacionados_payload(
    projeto: Project, viewer: User | None
) -> list[dict[str, Any]]:
    """Payload dos relacionados VISÍVEIS ao viewer (linha invisível é filtrada).

    JOIN único ``ProjectRelation ⨝ Project`` + ``joinedload(orgao_ref)``; a
    visibilidade entra na própria query (``apply_project_visibility``) — custo
    de leitura constante, sem checagem por item.
    """
    return [
        serialize_projeto_relacionado(outro)
        for outro in _projetos_relacionados(projeto.id, viewer)
    ]


def remover_relacoes_do_projeto(project_id: int) -> int:
    """Apaga todos os vínculos do projeto (chamar ANTES do delete do projeto).

    O ``ondelete="CASCADE"`` do banco é inerte em SQLite (dev/CI/testes) e
    ``ProjectRelation`` não tem relationship em ``Project``.
    """
    return ProjectRelation.query.filter(_envolve_projeto(project_id)).delete(
        synchronize_session=False
    )


def relacoes_do_projeto_ids(project_id: int) -> set[int]:
    """Ids dos projetos já vinculados (para excluir do autocomplete)."""
    rows = (
        db.session.query(
            ProjectRelation.project_low_id, ProjectRelation.project_high_id
        )
        .filter(_envolve_projeto(project_id))
        .all()
    )
    return {low if low != project_id else high for low, high in rows}


def serialize_projeto_relacionado(project: Project) -> dict[str, Any]:
    orgao_ref = project.orgao_ref
    return {
        "id": project.id,
        "titulo": project.titulo,
        "status": project.status,
        "prioridade": project.prioridade,
        "orgao_sigla": orgao_ref.sigla if orgao_ref is not None else None,
    }


def _par_canonico(project_id: int, related_project_id: int) -> tuple[int, int]:
    if project_id == related_project_id:
        raise RelacaoInvalida(
            f"related_project_id inválido: {related_project_id}; "
            "esperado id de projeto diferente do projeto de origem"
        )
    return min(project_id, related_project_id), max(project_id, related_project_id)


def _exigir_cota_da_origem(origem: Project) -> None:
    total = (
        db.session.query(func.count(ProjectRelation.id))
        .filter(_envolve_projeto(origem.id))
        .scalar()
        or 0
    )
    if total < RELATED_MAX_PER_PROJECT:
        return
    raise RelacaoInvalida(
        f"projeto id={origem.id} já tem {total} vínculos; "
        f"esperado menos que {RELATED_MAX_PER_PROJECT} para vincular outro"
    )


def _inserir_relacao(low_id: int, high_id: int, ator: User) -> ProjectRelation:
    relacao = ProjectRelation(
        project_low_id=low_id,
        project_high_id=high_id,
        created_by_user_id=ator.id,
    )
    try:
        with db.session.begin_nested():
            db.session.add(relacao)
    except IntegrityError:
        # Corrida entre dois POSTs: quem perdeu o INSERT relê o vencedor e
        # responde como duplicata, em vez de estourar 500.
        if _relacao_existente(low_id, high_id) is None:
            raise
        raise RelacaoInvalida(
            f"vínculo já existe entre os projetos {low_id} e {high_id}; "
            "esperado par ainda não relacionado"
        )
    return relacao


def _relacao_existente(low_id: int, high_id: int) -> ProjectRelation | None:
    return ProjectRelation.query.filter_by(
        project_low_id=low_id, project_high_id=high_id
    ).first()


def _envolve_projeto(project_id: int) -> Any:
    return or_(
        ProjectRelation.project_low_id == project_id,
        ProjectRelation.project_high_id == project_id,
    )


def _projetos_relacionados(project_id: int, viewer: User | None) -> list[Project]:
    query = (
        db.session.query(Project)
        .join(
            ProjectRelation,
            or_(
                and_(
                    ProjectRelation.project_low_id == project_id,
                    ProjectRelation.project_high_id == Project.id,
                ),
                and_(
                    ProjectRelation.project_high_id == project_id,
                    ProjectRelation.project_low_id == Project.id,
                ),
            ),
        )
        .options(joinedload(Project.orgao_ref))
        .order_by(ProjectRelation.id.asc())
    )
    return apply_project_visibility(query, viewer).all()


def _log_vinculo(origem: Project, action_type: str, descricao: str, ator: User) -> None:
    log_project_action(
        project_id=origem.id,
        action_type=action_type,
        description=descricao,
        actor_user_id=ator.id,
    )
