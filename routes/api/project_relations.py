"""Endpoints JSON dos PROJETOS RELACIONADOS (vínculo simétrico).

Três rotas no envelope canônico, anexadas ao ``main_bp`` ÚNICO:

    - ``POST   /api/projetos/<pid>/relacionados``              — vincula.
    - ``DELETE /api/projetos/<pid>/relacionados/<rid>``        — desvincula.
    - ``GET    /api/projetos/<pid>/relacionados/candidatos?q=`` — autocomplete.

Gates: POST exige editor na ORIGEM + leitor no alvo via ``project_access_verdict``
(alvo invisível/inexistente → ``fail_not_found()`` idêntico, anti-enumeração);
DELETE exige editor SOMENTE no projeto da URL (o editor do outro lado remove
chamando a rota com o projeto dele); candidatos exige leitor na origem e aplica
``apply_project_visibility`` no SQL. Regra em ``services/project_relations.py``;
commit/rollback nesta camada.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import Response, g, request
from sqlalchemy.orm import joinedload

from models import Project, db
from services.authorization import (
    ACCESS_OK,
    PAPEL_EDITOR,
    PAPEL_LEITOR,
    apply_project_visibility,
    project_access_verdict,
    require_project_rank,
)
from services.project_relations import (
    RelacaoForaDoEscopo,
    RelacaoInvalida,
    RelacaoSemPermissao,
    desrelacionar_projetos,
    relacionar_projetos,
    relacoes_do_projeto_ids,
)

from ..blueprint import main_bp
from .envelope import fail, fail_internal, fail_not_found, ok
from .negotiation import api_login_required

_ApiResponse = Response | tuple[Response, int]

_MIN_CANDIDATO_QUERY = 2
_MAX_CANDIDATOS = 10

_SEM_PERMISSAO = "Você não tem permissão para esta ação neste projeto."


def _erro_de_relacao(exc: RelacaoInvalida) -> tuple[Response, int]:
    """Projeto fora do escopo vira 404; papel insuficiente 403; o resto é 422."""
    if isinstance(exc, RelacaoForaDoEscopo):
        return fail_not_found()
    if isinstance(exc, RelacaoSemPermissao):
        return fail(_SEM_PERMISSAO, status=403, code="forbidden")
    return fail(str(exc), status=422, code="validation")


def _mutar(acao: Callable[[], _ApiResponse], log_label: str) -> _ApiResponse:
    """Monta a resposta dentro da transação e comita; traduz erros de domínio."""
    try:
        resposta = acao()
        db.session.commit()
    except RelacaoInvalida as exc:
        db.session.rollback()
        return _erro_de_relacao(exc)
    except Exception as exc:
        db.session.rollback()
        return fail_internal(exc, log_label)
    return resposta


def _load_origem(project_id: int, min_papel: str) -> tuple[Project | None, Any]:
    project = db.session.get(Project, project_id)
    denied = require_project_rank(project, min_papel)
    if denied:
        return None, denied
    return project, None


def _parse_related_project_id(payload: Any) -> int:
    if not isinstance(payload, dict):
        raise RelacaoInvalida(
            f"corpo inválido: {payload!r}; esperado objeto JSON com related_project_id"
        )
    raw = payload.get("related_project_id")
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise RelacaoInvalida(
            f"related_project_id inválido: {raw!r}; esperado o id inteiro do projeto"
        )
    return raw


def _load_alvo_visivel(related_project_id: int) -> Project:
    alvo = db.session.get(Project, related_project_id)
    verdict = project_access_verdict(g.user, alvo, PAPEL_LEITOR)
    if verdict != ACCESS_OK:
        raise RelacaoForaDoEscopo(
            f"projeto alvo id={related_project_id} fora do escopo do usuário"
        )
    return alvo


def _serialize_candidato(project: Project) -> dict[str, Any]:
    orgao_ref = project.orgao_ref
    return {
        "id": project.id,
        "titulo": project.titulo,
        "status": project.status,
        "orgao_sigla": orgao_ref.sigla if orgao_ref is not None else None,
    }


def _escape_like(query: str) -> str:
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@main_bp.route("/api/projetos/<int:project_id>/relacionados", methods=["POST"])
@api_login_required
def api_projeto_relacionar(project_id: int) -> _ApiResponse:
    """Vincula o projeto da URL a outro projeto (par canônico único).

    Returns:
        ``ok({})`` (200); 404 origem/alvo inexistente ou invisível; 403 rank
        abaixo de editor na origem; 422 auto-vínculo/duplicata/teto/corpo
        inválido; 401 sem sessão.
    """
    origem, error = _load_origem(project_id, PAPEL_EDITOR)
    if error is not None:
        return error

    def acao() -> _ApiResponse:
        related_project_id = _parse_related_project_id(request.get_json(silent=True))
        alvo = _load_alvo_visivel(related_project_id)
        relacionar_projetos(origem, alvo, g.user)
        return ok({})

    return _mutar(acao, "api_projeto_relacionar")


@main_bp.route(
    "/api/projetos/<int:project_id>/relacionados/<int:related_project_id>",
    methods=["DELETE"],
)
@api_login_required
def api_projeto_desrelacionar(project_id: int, related_project_id: int) -> _ApiResponse:
    """Desfaz o vínculo entre o projeto da URL e ``related_project_id``.

    Gate SOMENTE no projeto da URL (anti-enumeração do outro lado).

    Returns:
        ``ok({})`` (200); 404 origem invisível/inexistente OU par sem vínculo;
        403 rank abaixo de editor; 401 sem sessão.
    """
    origem, error = _load_origem(project_id, PAPEL_EDITOR)
    if error is not None:
        return error

    def acao() -> _ApiResponse:
        if not desrelacionar_projetos(origem, related_project_id, g.user):
            return fail_not_found()
        return ok({})

    return _mutar(acao, "api_projeto_desrelacionar")


@main_bp.route(
    "/api/projetos/<int:project_id>/relacionados/candidatos", methods=["GET"]
)
@api_login_required
def api_projeto_relacionados_candidatos(project_id: int) -> _ApiResponse:
    """Autocomplete de projetos vinculáveis, com visibilidade aplicada no SQL.

    Query params:
        ``q``: trecho do título (mínimo 2 caracteres; ``%``/``_`` escapados).

    Returns:
        ``ok([{id, titulo, status, orgao_sigla}])`` com no máximo 10 itens
        (lista vazia sob o piso); 404 origem invisível/inexistente; 401 sem
        sessão.
    """
    origem, error = _load_origem(project_id, PAPEL_LEITOR)
    if error is not None:
        return error

    termo = (request.args.get("q") or "").strip()
    if len(termo) < _MIN_CANDIDATO_QUERY:
        return ok([])

    excluidos = relacoes_do_projeto_ids(origem.id) | {origem.id}
    query = apply_project_visibility(db.session.query(Project), g.user)
    candidatos = (
        query.filter(
            Project.titulo.ilike(f"%{_escape_like(termo)}%", escape="\\"),
            Project.id.notin_(excluidos),
        )
        .options(joinedload(Project.orgao_ref))
        .order_by(Project.titulo.asc(), Project.id.asc())
        .limit(_MAX_CANDIDATOS)
        .all()
    )
    return ok([_serialize_candidato(projeto) for projeto in candidatos])
