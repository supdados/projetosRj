"""Pacote da API JSON consumida pela SPA SvelteKit.

Importado por ``routes/__init__.py`` (``from . import api``) durante o registro
do blueprint. Anexa endpoints ao ``main_bp`` ÚNICO (``routes/blueprint.py``);
NÃO cria blueprint novo, para preservar os ``url_for("main.xxx")`` existentes.

Conteúdo:
    - ``envelope``    — ``ok``/``fail`` (envelope canônico ``{ok, data}`` /
                        ``{ok, error}``).
    - ``negotiation`` — ``wants_json`` único + ``api_login_required`` /
                        ``api_admin_required`` (401/403 JSON).
    - ``serializers`` — ``serialize_user`` / ``serialize_project_card`` (campos
                        reais; sem segredos).
    - ``legacy``      — endpoints JSON pré-existentes (rotas ``/api/*`` que já
                        existiam em ``routes/api.py``), preservados sem mudança.

À medida que as próximas etapas existirem (``session``, ``dashboard``, ...),
seus submódulos devem ser importados aqui para que as rotas se registrem em
``main_bp``.

O index da SPA é servido por ``routes/spa.py`` (catch-all ``/spa``), importado em
``routes/__init__.py`` (``from . import spa``) para registrar a rota no
``main_bp``; ele NÃO mora neste pacote ``api`` por servir HTML (Jinja +
``csp_nonce``), não JSON.
"""

# Reexports de conveniência para os consumidores da API.
from .envelope import fail, ok  # noqa: F401
from .negotiation import (  # noqa: F401
    api_admin_required,
    api_login_required,
    wants_json,
)
from .serializers import (  # noqa: F401
    serialize_admin_user,
    serialize_etapa_card,
    serialize_etapa_detail,
    serialize_orgao_form,
    serialize_orgao_node,
    serialize_orgao_option,
    serialize_orgao_tipo,
    serialize_pending_project_row,
    serialize_project_card,
    serialize_project_detail,
    serialize_project_history_entry,
    serialize_task_card,
    serialize_task_detail,
    serialize_template_detail,
    serialize_template_row,
    serialize_template_stage_item,
    serialize_user,
)

# Importa submódulos com rotas para registrá-las no main_bp.
from . import legacy  # noqa: F401,E402
from . import session  # noqa: F401,E402
from . import dashboard  # noqa: F401,E402
from . import projects  # noqa: F401,E402
from . import project_detail  # noqa: F401,E402
from . import etapas  # noqa: F401,E402
from . import tasks  # noqa: F401,E402
from . import board  # noqa: F401,E402
from . import task_drawer  # noqa: F401,E402
from . import task_comments  # noqa: F401,E402
from . import task_attachments  # noqa: F401,E402
from . import calendars  # noqa: F401,E402
from . import search  # noqa: F401,E402
from . import admin_users  # noqa: F401,E402
from . import admin_orgaos  # noqa: F401,E402
from . import admin_templates  # noqa: F401,E402

__all__ = [
    "ok",
    "fail",
    "wants_json",
    "api_login_required",
    "api_admin_required",
    "serialize_user",
    "serialize_admin_user",
    "serialize_project_card",
    "serialize_project_detail",
    "serialize_task_card",
    "serialize_task_detail",
    "serialize_etapa_card",
    "serialize_etapa_detail",
    "serialize_orgao_option",
    "serialize_orgao_node",
    "serialize_orgao_form",
    "serialize_orgao_tipo",
    "serialize_pending_project_row",
    "serialize_project_history_entry",
    "serialize_template_detail",
    "serialize_template_row",
    "serialize_template_stage_item",
]
