"""Round-trip export → import do modo com etapas.

O contrato é que os cabeçalhos do export sejam sinônimos exatos dos campos do
import: exportar um lote, reimportá-lo com o mapeamento sugerido a partir dos
próprios cabeçalhos e obter os mesmos projetos e etapas. Cobre
``services/project_export.py``, ``services/import_columns.py`` e
``routes/projects/import_stages.py``.
"""

from __future__ import annotations

import datetime
from typing import NamedTuple

from models import Etapa, OrgaoUnidade, Project, db
from routes.projects.import_csv import ImportOutcome, parse_import_rows
from routes.projects.import_stages import _persist_imported_projects_with_stages
from services.etapa_responsaveis import apply_responsaveis_entries, responsavel_display
from services.import_columns import (
    IMPORT_FIELDS,
    IMPORT_FIELDS_COM_ETAPAS,
    suggest_column_mapping,
)
from services.project_export import (
    DEFAULT_EXPORT_STAGE_SLUGS,
    EXPORT_COLUMNS,
    EXPORT_STAGE_COLUMNS,
    build_export_headers_with_stages,
    build_export_rows_with_stages,
    write_tabular_bytes,
)
from services.sei_process import replace_project_sei_numbers
from tests._orgao_helpers import ensure_orgao

_SLUGS_PROJETO: tuple[str, ...] = (
    "titulo",
    "descricao",
    "status",
    "prioridade",
    "tipo_entrega",
    "projeto_especial",
    "area",
    "orgao",
    "observacao",
    "sei",
)

_CAMPO_POR_CABECALHO: dict[str, str] = {
    "Ref Projeto": "ref_projeto",
    "Título": "titulo",
    "Descrição": "descricao",
    "Status": "status",
    "Prioridade": "prioridade",
    "Tipo de entrega": "delivery_type",
    "Projeto especial": "special_project",
    "Área responsável": "area",
    "Órgão": "orgao",
    "Observação": "observacao",
    "Processos SEI": "sei",
    "Etapa": "etapa",
    "Etapa Data de início": "etapa_data_inicio",
    "Etapa Data de fim": "etapa_data_fim",
    "Etapa Responsável": "etapa_responsavel",
    "Etapa Situação": "etapa_situacao",
    "Etapa Comentários": "etapa_comentarios",
}

_SEI_NUMEROS: list[str] = ["SEI-380001/000664/2026", "SEI-380001/000665/2026"]


class _SementeEtapa(NamedTuple):
    descricao: str
    data_inicio: datetime.date | None
    data_fim: datetime.date | None
    iniciada: bool
    done: bool
    siglas: tuple[str, ...]
    comentarios: str


_ETAPAS_SEMENTE: tuple[_SementeEtapa, ...] = (
    _SementeEtapa(
        "Levantamento de requisitos",
        datetime.date(2026, 1, 5),
        datetime.date(2026, 1, 20),
        True,
        True,
        ("VPD",),
        "Ata publicada",
    ),
    _SementeEtapa(
        "Desenvolvimento",
        datetime.date(2026, 2, 2),
        datetime.date(2026, 3, 31),
        True,
        False,
        ("VPD", "COODADOS"),
        "",
    ),
    _SementeEtapa("Homologação", None, None, False, False, (), "Depende do fornecedor"),
)

_ETAPA_PLACEHOLDER: tuple[object, ...] = (
    0,
    "Etapas a definir",
    None,
    None,
    False,
    False,
    "",
    "",
)


def test_cabecalhos_do_export_com_etapas_auto_mapeiam_nos_campos_certos() -> None:
    cabecalhos = build_export_headers_with_stages(
        _SLUGS_PROJETO, DEFAULT_EXPORT_STAGE_SLUGS
    )
    sugestoes = suggest_column_mapping(cabecalhos, IMPORT_FIELDS_COM_ETAPAS)
    assert {s.cabecalho: s.campo for s in sugestoes} == _CAMPO_POR_CABECALHO
    assert {s.confianca for s in sugestoes} == {"exato"}


def test_datas_de_projeto_e_de_etapa_nao_se_confundem() -> None:
    cabecalhos = [
        EXPORT_COLUMNS["data_inicio"].header,
        EXPORT_COLUMNS["data_fim"].header,
        EXPORT_STAGE_COLUMNS["etapa_data_inicio"].header,
        EXPORT_STAGE_COLUMNS["etapa_data_fim"].header,
    ]
    sugestoes = suggest_column_mapping(cabecalhos, IMPORT_FIELDS)
    assert [s.campo for s in sugestoes] == [
        "data_inicio",
        "data_fim",
        "etapa_data_inicio",
        "etapa_data_fim",
    ]


def test_roundtrip_export_com_etapas_preserva_projetos_e_etapas(app) -> None:
    with app.app_context():
        areas = {sigla: ensure_orgao(sigla) for sigla in ("VPD", "COODADOS", "SETD")}
        com_etapas, sem_etapa = _semear_lote(areas)
        campos_antes = [_snapshot_campos(com_etapas), _snapshot_campos(sem_etapa)]
        etapas_antes = _snapshot_etapas(com_etapas)
        ids_antes = [com_etapas.id, sem_etapa.id]

        resultado = _reimportar([com_etapas, sem_etapa], areas["SETD"])

        assert (resultado.imported, resultado.ignored) == (2, 0)
        assert resultado.etapas_criadas == 4
        assert resultado.adjusted == 0
        novo_com_etapas, novo_sem_etapa = _projetos_novos(ids_antes)
        assert [
            _snapshot_campos(novo_com_etapas),
            _snapshot_campos(novo_sem_etapa),
        ] == campos_antes
        assert _snapshot_etapas(novo_com_etapas) == etapas_antes
        assert _snapshot_etapas(novo_sem_etapa) == [_ETAPA_PLACEHOLDER]


def _semear_lote(areas: dict[str, OrgaoUnidade]) -> tuple[Project, Project]:
    """Cria via ORM o projeto com 3 etapas variadas e o projeto sem etapa."""
    com_etapas = _projeto_com_etapas(areas["VPD"])
    for ordem, semente in enumerate(_ETAPAS_SEMENTE):
        _criar_etapa(com_etapas, ordem, semente, areas)
    sem_etapa = _projeto_sem_etapa(areas["COODADOS"])
    db.session.commit()
    return com_etapas, sem_etapa


def _projeto_com_etapas(area: OrgaoUnidade) -> Project:
    projeto = Project(
        titulo="Portal Único do Servidor",
        short_description="Unifica o atendimento ao servidor",
        status="Vigente",
        prioridade="alta",
        delivery_type="Sistema",
        special_project="TCE",
        observacao="Acompanhamento semanal",
        orgao="Secretaria de Estado de Fazenda",
        orgao_id=area.id,
    )
    db.session.add(projeto)
    db.session.flush()
    replace_project_sei_numbers(projeto, _SEI_NUMEROS)
    return projeto


def _projeto_sem_etapa(area: OrgaoUnidade) -> Project:
    projeto = Project(
        titulo="Cadastro Base do Cidadão",
        short_description="Base única de cadastro",
        status="Suspenso",
        prioridade="baixa",
        delivery_type="Painel",
        special_project="ABEP",
        observacao="Aguardando repactuação",
        orgao="Casa Civil",
        orgao_id=area.id,
    )
    db.session.add(projeto)
    db.session.flush()
    return projeto


def _criar_etapa(
    projeto: Project,
    ordem: int,
    semente: _SementeEtapa,
    areas: dict[str, OrgaoUnidade],
) -> None:
    etapa = Etapa(
        project_id=projeto.id,
        descricao=semente.descricao,
        ordem=ordem,
        data_inicio=semente.data_inicio,
        data_fim=semente.data_fim,
        iniciada=semente.iniciada,
        done=semente.done,
        comentarios=semente.comentarios or None,
    )
    db.session.add(etapa)
    db.session.flush()
    entries = [{"area_id": areas[sigla].id, "label": sigla} for sigla in semente.siglas]
    if entries:
        apply_responsaveis_entries(etapa, entries)


def _mapeamento_sugerido(cabecalhos: list[str]) -> dict[int, str]:
    """Mapeamento derivado só dos cabeçalhos do export, sem correção manual."""
    sugestoes = suggest_column_mapping(cabecalhos, IMPORT_FIELDS_COM_ETAPAS)
    return {
        sugestao.indice: sugestao.campo
        for sugestao in sugestoes
        if sugestao.campo is not None
    }


def _reimportar(projetos: list[Project], area_padrao: OrgaoUnidade) -> ImportOutcome:
    """Exporta com etapas, serializa e reimporta o arquivo no modo com etapas."""
    cabecalhos = build_export_headers_with_stages(
        _SLUGS_PROJETO, DEFAULT_EXPORT_STAGE_SLUGS
    )
    linhas = build_export_rows_with_stages(
        projetos, _SLUGS_PROJETO, DEFAULT_EXPORT_STAGE_SLUGS
    )
    conteudo = write_tabular_bytes(cabecalhos, linhas)
    rows = parse_import_rows(conteudo, _mapeamento_sugerido(cabecalhos))
    return _persist_imported_projects_with_stages(
        rows, area_padrao, "Finalizado", None, None
    )


def _projetos_novos(ids_antes: list[int]) -> list[Project]:
    return Project.query.filter(Project.id.notin_(ids_antes)).order_by(Project.id).all()


def _snapshot_campos(projeto: Project) -> tuple[object, ...]:
    return (
        projeto.titulo,
        projeto.short_description,
        projeto.status,
        projeto.prioridade,
        projeto.delivery_type,
        projeto.special_project,
        projeto.observacao,
        projeto.orgao,
        projeto.orgao_id,
        [item.numero for item in projeto.sei_processes],
    )


def _snapshot_etapas(projeto: Project) -> list[tuple[object, ...]]:
    return [_snapshot_etapa(etapa) for etapa in projeto.workflow_etapas]


def _snapshot_etapa(etapa: Etapa) -> tuple[object, ...]:
    return (
        etapa.ordem,
        etapa.descricao,
        etapa.data_inicio,
        etapa.data_fim,
        etapa.iniciada,
        etapa.done,
        etapa.comentarios or "",
        responsavel_display(etapa),
    )
