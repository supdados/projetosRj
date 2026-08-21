"""Renderiza o shell Jinja autenticado (base.html + app_topnav) fora de rota.

Com o corte de /profile/change-password (Passo 1b do mapa do legado), nenhuma
rota viva renderiza base.html com usuário logado — as telas de auth restantes
são anônimas. Os contratos de UI do topnav/notificações seguem válidos até o
Passo 6 da faxina, então os testes os exercitam por render direto num request
context de teste (os context processors reais de app.py/routes/shared.py rodam
normalmente a partir de ``g.user``).
"""

from __future__ import annotations

from typing import Mapping

from flask import Flask, g, render_template

from models import User, db


def render_authenticated_shell(
    app: Flask,
    seed_data: Mapping[str, object],
    *,
    user_key: str = "user_id",
    path: str = "/dashboard",
) -> str:
    """Renderiza base.html como o usuário ``seed_data[user_key]`` em ``path``.

    Exemplo:
        >>> html = render_authenticated_shell(app, seed_data, user_key="admin_id")
    """
    with app.test_request_context(path):
        g.user = db.session.get(User, seed_data[user_key])
        return render_template("base.html")
