from .blueprint import main_bp
from .shared import inject_current_year

# Importa módulos para registrar rotas no blueprint compartilhado.
# Ordem natural: o ciclo que exigia carregar `etapas` antes de `api` foi
# eliminado no débito técnico #11 — os serviços `etapas_mutation`/`etapas_cascade`
# agora importam os helpers puros de `services/etapas_dates.py` (não mais de
# `routes.etapas.helpers`), então `routes.api` não depende mais de `routes.etapas`
# em tempo de import.
from . import admin_templates  # noqa: F401,E402
from . import admin_users  # noqa: F401,E402
from . import api  # noqa: F401,E402
from . import auth  # noqa: F401,E402
from . import calendars  # noqa: F401,E402
from . import dashboard  # noqa: F401,E402
from . import etapas  # noqa: F401,E402
from . import maintenance  # noqa: F401,E402
from . import notifications  # noqa: F401,E402
from . import projects  # noqa: F401,E402
from . import search  # noqa: F401,E402
from . import spa  # noqa: F401,E402
from . import tasks  # noqa: F401,E402

__all__ = ["main_bp", "inject_current_year"]
