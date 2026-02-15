from functools import wraps

from flask import flash, g, redirect, request, session, url_for


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('main.login_page', next=request.url))
        if not g.user:
            session.clear()
            flash('Sua sessão é inválida ou o usuário não existe. Por favor, faça login novamente.', 'warning')
            return redirect(url_for('main.login_page'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user or not g.user.is_admin:
            flash('Você não tem permissão para acessar esta página.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)

    return decorated_function
