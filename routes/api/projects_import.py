"""Endpoint JSON de importação de projetos via CSV (Admin) consumido pela SPA.

Sucessor da rota Jinja ``/projects/import`` (``routes/projects/import_csv.py``):
reusa a MESMA lógica pura de parsing (``parse_import_rows``) e persistência
(``_persist_imported_projects``), apenas trocando o ``flash`` + redirect do fluxo
Jinja pelo envelope canônico (``ok``/``fail``). Restrito a admin via
``api_admin_required``.
"""

from __future__ import annotations

from flask import Response, request
from sqlalchemy.exc import SQLAlchemyError

from catalogs.inventario import sanitize_special_project_for_orgao
from models import OrgaoUnidade, db

from ..blueprint import main_bp
from ..projects.import_csv import (
    ALLOWED_IMPORT_STATUSES,
    _persist_imported_projects,
    parse_import_rows,
)
from .envelope import fail, ok
from .negotiation import api_admin_required


@main_bp.route("/api/projetos/importar-csv", methods=["POST"])
@api_admin_required
def api_projetos_importar_csv() -> Response | tuple[Response, int]:
    """Importa projetos em lote de um CSV (colunas ``titulo``/``descricao``).

    Aceita ``multipart/form-data`` com o arquivo em ``arquivo`` e os atributos
    comuns aplicados a todas as linhas: ``orgao_id`` (obrigatório), ``status``,
    ``special_project`` e ``delivery_type``. Validações espelham a rota Jinja.

    Returns:
        ``ok({"imported_count": N})`` em sucesso; ``fail(..., 422, "validation")``
        para entradas inválidas; ``fail(..., 500)`` em erro de persistência.
        ``api_admin_required`` devolve 401/403 conforme a sessão.
    """
    orgao_id_raw = request.form.get("orgao_id")
    if not orgao_id_raw:
        return fail(
            "Selecione o órgão de destino dos projetos.",
            status=422,
            code="validation",
        )
    try:
        orgao_id = int(orgao_id_raw)
    except (TypeError, ValueError):
        return fail(
            f"Órgão inválido: {orgao_id_raw!r} (esperado id numérico).",
            status=422,
            code="validation",
        )
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None or not orgao.ativo:
        return fail(
            "O órgão selecionado é inválido ou não está mais disponível.",
            status=422,
            code="validation",
        )

    status = request.form.get("status") or "Vigente"
    if status not in ALLOWED_IMPORT_STATUSES:
        return fail(
            f"Status inválido: {status!r}. Use um de {ALLOWED_IMPORT_STATUSES}.",
            status=422,
            code="validation",
        )

    special_project = sanitize_special_project_for_orgao(
        request.form.get("special_project") or None, orgao.sigla
    )
    delivery_type = request.form.get("delivery_type") or None

    upload = request.files.get("arquivo")
    if not upload or not upload.filename:
        return fail(
            "Selecione um arquivo CSV para importar.", status=422, code="validation"
        )

    try:
        rows = parse_import_rows(upload.read())
    except ValueError as parse_error:
        return fail(f"Falha ao ler o CSV: {parse_error}", status=422, code="validation")

    if not rows:
        return fail(
            'Nenhum projeto válido encontrado no CSV (verifique a coluna "titulo").',
            status=422,
            code="validation",
        )

    try:
        _persist_imported_projects(rows, orgao, status, special_project, delivery_type)
    except SQLAlchemyError:
        db.session.rollback()
        return fail(
            "Erro ao salvar os projetos importados.", status=500, code="server_error"
        )

    return ok({"imported_count": len(rows)})
