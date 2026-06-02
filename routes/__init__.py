from .blueprint import main_bp
from .shared import inject_current_year

# Importa módulos para registrar rotas no blueprint compartilhado.
# `etapas` precede `api`: os endpoints de `routes/api/etapas.py` reusam serviços
# (etapas_mutation/etapas_cascade) que dependem de `routes.etapas.helpers`; carregar
# `routes.etapas` primeiro evita import circular ao inicializar `routes.api`.
from . import admin_orgaos  # noqa: F401,E402
from . import admin_templates  # noqa: F401,E402
from . import admin_users  # noqa: F401,E402
from . import etapas  # noqa: F401,E402
from . import api  # noqa: F401,E402
from . import auth  # noqa: F401,E402
from . import calendars  # noqa: F401,E402
from . import dashboard  # noqa: F401,E402
from . import maintenance  # noqa: F401,E402
from . import notifications  # noqa: F401,E402
from . import projects  # noqa: F401,E402
from . import search  # noqa: F401,E402
from . import spa  # noqa: F401,E402
from . import tasks  # noqa: F401,E402
from . import tutorial  # noqa: F401,E402

__all__ = ["main_bp", "inject_current_year"]
