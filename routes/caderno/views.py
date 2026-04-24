from flask import render_template

from ..blueprint import main_bp
from ..decorators import login_required


@main_bp.route("/caderno")
@login_required
def caderno_page():
    return render_template("caderno/index.html")
