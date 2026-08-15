from flask import current_app, g, jsonify, request

from models import Etapa, Project, UserCalendarConnection, db
from services.calendar_sync import hydrate_google_connection_identity
from services.google_calendar import is_google_calendar_enabled

# Helpers PUROS de datas/serialização moram em ``services/etapas_dates.py``
# (débito técnico #11 — desacoplar serviço de rota). Re-exportados aqui apenas
# para o código legado que ainda importa estes nomes de ``routes.etapas.helpers``
# (ex.: tests/test_etapas_business_days_unit.py); a fonte de verdade é o serviço.
from services.etapas_dates import (  # noqa: F401
    _add_business_days,
    _business_days_between,
    _is_business_day,
    _next_etapa_order,
    _normalize_to_business_day,
)
from services.authorization import (
    AccessVerdict,
    PAPEL_EDITOR,
    project_access_verdict,
)


def _is_ajax_request():
    requested_with = (
        request.headers.get("X-Requested-With", "").lower() == "xmlhttprequest"
    )
    accepts_json = "application/json" in request.headers.get("Accept", "").lower()
    return requested_with or accepts_json


def _connection_for_current_user():
    if not getattr(g, "user", None):
        return None
    connection = UserCalendarConnection.query.filter_by(user_id=g.user.id).first()
    if (
        connection is not None
        and not (connection.google_account_id or "").strip()
        and is_google_calendar_enabled(current_app.config)
    ):
        try:
            hydrate_google_connection_identity(current_app.config, connection)
        except Exception as exc:
            current_app.logger.warning(
                "Nao foi possivel hidratar a identidade Google da conexao %s para a rota de etapas: %s",
                connection.id,
                exc,
            )
    return connection


def _legacy_not_found():
    """404 anti-enumeração das rotas legadas de etapa/reunião (S5/F4-2b).

    Recurso inexistente e recurso invisível (rank 0 no projeto) devem sair por
    aqui — mesmo status, mesmo corpo, sem mensagem própria que revele qual dos
    dois é o caso.

    Exemplo:
        >>> if verdict == ACCESS_NOT_FOUND:
        ...     return _legacy_not_found()
    """
    # Import local: `routes.api.envelope` dispara `routes/api/__init__`, que
    # importa este módulo de volta — no topo o ciclo estoura no boot.
    from routes.api.envelope import NOT_FOUND_MESSAGE

    return jsonify({"success": False, "message": NOT_FOUND_MESSAGE}), 404


def _project_write_verdict(project: "Project | None") -> AccessVerdict:
    """Veredito 404-vs-403 das escritas de etapa/reunião (rank >= editor)."""
    return project_access_verdict(getattr(g, "user", None), project, PAPEL_EDITOR)


def _load_project_for_etapa_write(
    project_id: int,
) -> "tuple[Project | None, AccessVerdict]":
    """Projeto + veredito de escrita: ``ACCESS_NOT_FOUND`` cobre id inexistente E rank 0.

    O chamador responde ``_legacy_not_found()`` nos dois casos, sem distinguir.

    Exemplo:
        >>> project, verdict = _load_project_for_etapa_write(7)
    """
    project = db.session.get(Project, project_id)
    return project, _project_write_verdict(project)


def _load_etapa_for_write(etapa_id: int) -> "tuple[Etapa | None, AccessVerdict]":
    """Etapa + veredito de escrita no projeto dela (mesma regra de ``_load_project_for_etapa_write``).

    Exemplo:
        >>> etapa, verdict = _load_etapa_for_write(42)
    """
    etapa = db.session.get(Etapa, etapa_id)
    project = etapa.project if etapa is not None else None
    return etapa, _project_write_verdict(project)
