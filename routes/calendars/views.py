from routes.blueprint import main_bp
from routes.decorators import login_required
from routes.spa import _render_spa


@main_bp.route("/calendarios", methods=["GET"])
@login_required
def calendars_hub():
    """Serve a SPA no path nativo ``/calendarios`` (cut-over KEEP-ENDPOINT).

    O endpoint ``main.calendars_hub`` permanece para que os ``url_for`` em
    ``routes/calendars/oauth.py`` e ``routes/search.py`` continuem validos; o
    corpo agora devolve a shell da SPA. A fonte de dados real do hub vive em
    ``GET /api/calendarios`` (consumido pela SPA); o CRUD de evento continua nas
    rotas ``routes/calendars/events.py`` (API de fato da SPA).
    """
    return _render_spa()
