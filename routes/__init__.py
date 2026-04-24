from .blueprint import main_bp
from .shared import inject_current_year

# Importa módulos para registrar rotas no blueprint compartilhado
from . import admin_orgaos  # noqa: F401,E402
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
from . import tasks  # noqa: F401,E402
from . import caderno  # noqa: F401
from . import tutorial  # noqa: F401,E402

__all__ = ["main_bp", "inject_current_year"]
