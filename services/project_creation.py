"""Criação de projeto reusável por Jinja (``add_project``) e API (``POST /api/projetos``).

Extrai a lógica de montagem de ``Project`` + etapas (com cálculo sequencial de
datas a partir de ``start_date`` e durações em dias), indicadores e
``StageTemplateUsage`` que antes vivia inline em ``routes/projects/crud.py``
(item 6 da sequência de refatoração do CLAUDE.md). NÃO faz commit nem flash:
isso fica a cargo do chamador (rota Jinja vs. envelope JSON), preservando a
fonte de verdade única das REGRAS de criação.

Não trata permissão de órgão aqui — o chamador resolve o ``OrgaoUnidade`` via
``_resolve_orgao_from_form`` (mesma validação de escopo) e passa a instância.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from catalogs.abep import normalize_abep_indicator
from catalogs.objectives import normalize_goal_selection
from models import (
    Etapa,
    IndicadorProjeto,
    OrgaoUnidade,
    Project,
    StageTemplate,
    StageTemplateUsage,
    db,
)


@dataclass
class StageDraft:
    """Etapa importada de um modelo no momento da criação (descrição + duração).

    ``duration_days`` é opcional; quando ausente, a etapa é criada sem datas
    calculadas (mesmo comportamento do form Jinja quando não há ``start_date``).
    """

    descricao: str
    duration_days: Optional[int] = None


@dataclass
class ProjectCreationInput:
    """Campos normalizados para criar um projeto (espelha o form Jinja).

    ``titulo`` e ``orgao_unidade`` são obrigatórios e validados pelo chamador.
    Os demais espelham 1:1 os campos de ``add_project`` no form.
    """

    titulo: str
    orgao_unidade: OrgaoUnidade
    orgao: Optional[str] = None
    prioridade: Optional[str] = None
    objetivo_id: Optional[int] = None
    resultado_esperado_id: Optional[int] = None
    indicador_ids: list[int] = field(default_factory=list)
    observacao: Optional[str] = None
    special_project: Optional[str] = None
    sei_process: Optional[str] = None
    short_description: Optional[str] = None
    delivery_type: Optional[str] = None
    abep_indicator: Optional[str] = None
    github_link: Optional[str] = None
    documentation_link: Optional[str] = None
    product_link: Optional[str] = None
    etapas: list[StageDraft] = field(default_factory=list)
    start_date: Optional[datetime.date] = None
    template_id: Optional[int] = None
    is_tutorial: bool = False


def create_project_record(data: ProjectCreationInput, *, created_by_id: int | None):
    """Cria o ``Project`` + etapas + indicadores + usage SEM commit.

    Reusa ``normalize_goal_selection``/``normalize_abep_indicator`` (já aplicados
    pelo chamador) e replica o cálculo sequencial de datas das etapas de
    ``add_project``: cada etapa começa no dia seguinte ao fim da anterior, com
    ``data_fim = data_inicio + (duração - 1)`` (o início conta como dia 1).

    Args:
        data: Campos normalizados do projeto.
        created_by_id: ID do usuário criador (para ``StageTemplateUsage``).

    Returns:
        O ``Project`` recém-adicionado à sessão (com ``flush`` já aplicado para
        obter ``id``). O chamador deve registrar histórico e dar ``commit``.

    Exemplo:
        >>> proj = create_project_record(payload, created_by_id=g.user.id)
        >>> db.session.commit()
    """
    new_project = Project(
        titulo=data.titulo,
        orgao_id=data.orgao_unidade.id,
        orgao=data.orgao,
        prioridade=data.prioridade,
        objetivo_id=data.objetivo_id,
        resultado_esperado_id=data.resultado_esperado_id,
        observacao=data.observacao,
        status="Vigente",
        is_tutorial=data.is_tutorial,
        special_project=data.special_project,
        sei_process=data.sei_process,
        short_description=data.short_description,
        delivery_type=data.delivery_type,
        abep_indicator=data.abep_indicator,
        github_link=data.github_link,
        documentation_link=data.documentation_link,
        product_link=data.product_link,
    )
    db.session.add(new_project)
    db.session.flush()

    _add_sequential_stages(new_project, data.etapas, data.start_date)

    for indicador_id in data.indicador_ids:
        db.session.add(
            IndicadorProjeto(project_id=new_project.id, indicador_id=indicador_id)
        )

    _register_template_usage(data.template_id, new_project.id, created_by_id)
    return new_project


def _add_sequential_stages(
    project: Project, etapas: list[StageDraft], start_date: datetime.date | None
) -> None:
    """Adiciona as etapas do modelo em sequência, calculando datas por duração."""
    current_date = start_date
    for index, draft in enumerate(etapas):
        descricao = (draft.descricao or "").strip()
        if not descricao:
            continue
        data_inicio = None
        data_fim = None
        if current_date is not None and draft.duration_days:
            data_inicio = current_date
            data_fim = current_date + datetime.timedelta(days=draft.duration_days - 1)
            current_date = data_fim + datetime.timedelta(days=1)
        db.session.add(
            Etapa(
                descricao=descricao,
                project_id=project.id,
                ordem=index,
                data_inicio=data_inicio,
                data_fim=data_fim,
            )
        )


def _register_template_usage(
    template_id: int | None, project_id: int, created_by_id: int | None
) -> None:
    """Registra ``StageTemplateUsage`` quando o projeto nasce de um modelo válido."""
    if not template_id:
        return
    if db.session.get(StageTemplate, template_id) is None:
        return
    db.session.add(
        StageTemplateUsage(
            template_id=template_id,
            project_id=project_id,
            created_by_id=created_by_id,
            source="creation",
        )
    )
