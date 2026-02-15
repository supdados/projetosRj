from flask import flash, g, redirect, render_template, request, session, url_for

from models import User, db

from .blueprint import main_bp
from .decorators import login_required
@main_bp.route('/', methods=['GET'])
def home():
    if 'user_id' in session and g.user: # Se logado e usuário válido
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login_page'))

@main_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    if 'user_id' in session and g.user: # Se já logado e usuário válido
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Usuário e senha são obrigatórios.', 'warning')
            # Não precisa passar 'error' aqui, o flash já cuida da mensagem
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.clear() # Limpa qualquer sessão antiga
            session['user_id'] = user.id
            # Outras informações como username, nome, is_admin, area, orgao
            # serão primariamente acessadas via g.user (carregado no @app.before_request)
            # ou pelo context_processor que injeta current_user_obj e is_admin_user.
            # Não é estritamente necessário colocar tudo na session se g.user está disponível.
            
            g.user = user # Garante que g.user esteja populado para este request imediato

            flash(f'Login bem-sucedido, {user.name}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        else:
            flash('Credenciais inválidas. Tente novamente.', 'danger')
            # Não precisa passar 'error' aqui, o flash já cuida da mensagem
            return render_template('login.html')
    return render_template('login.html')

@main_bp.route('/logout')
@login_required # Só pode fazer logout se estiver logado
def logout():
    session.clear()
    g.user = None # Limpa g.user também
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('main.login_page'))

@main_bp.route('/profile/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_new_password = request.form.get('confirm_new_password')

        if not current_password or not new_password or not confirm_new_password:
            flash('Todos os campos são obrigatórios.', 'danger')
            return render_template('change_password.html')

        if not g.user.check_password(current_password):
            flash('Senha atual incorreta.', 'danger')
            return render_template('change_password.html')

        if new_password != confirm_new_password:
            flash('A nova senha e a confirmação não correspondem.', 'danger')
            return render_template('change_password.html')
        
        if len(new_password) < 6:
            flash('A nova senha deve ter no mínimo 6 caracteres.', 'danger')
            return render_template('change_password.html')

        g.user.set_password(new_password)
        db.session.commit()
        flash('Senha alterada com sucesso!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('change_password.html')
