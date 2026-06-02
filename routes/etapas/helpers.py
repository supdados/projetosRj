from flask import current_app, g, request

from models import UserCalendarConnection
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
    _serialize_etapa_payload,
)
from routes.orgao_scope import user_can_access_project


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


def _current_user_can_edit_project(project):
    return user_can_access_project(g.user, project)
