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
    ``GET /api/calendarios`` e o CRUD de evento usado pela SPA em
    ``/api/calendarios/eventos*`` (``routes/api/calendars_events.py``; ver
    ``frontend/src/lib/api/calendars.ts``). ``routes/calendars/events.py`` é o
    CRUD legado (form POST + redirect), morto para a SPA, mantido até a lane de
    projetos.
    """
    return _render_spa()
