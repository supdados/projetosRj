import os

from flask import send_from_directory

from .blueprint import main_bp


@main_bp.route("/favicon.ico")
def favicon():
    response = send_from_directory(
        os.path.join(main_bp.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
        max_age=0,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
