import os
from flask import Blueprint

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
main_bp = Blueprint('main', __name__, root_path=PROJECT_ROOT)
