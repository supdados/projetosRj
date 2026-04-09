from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

from models import db

migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
