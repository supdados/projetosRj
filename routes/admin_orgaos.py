from flask import flash, jsonify, redirect, render_template, request, url_for

from models import OrgaoUnidade, db
from models.orgao import ALLOWED_TIPOS, MAX_DEPTH, TIPO_RANK

from .blueprint import main_bp
from .decorators import admin_required, login_required
from .orgao_tree import compute_orgao_depth, get_orgao_descendants, normalize_orgao_form, validate_orgao_move
from .shared import get_or_404


def _serialize_orgao(orgao):
    return {
        'id': orgao.id,
        'nome': orgao.nome,
        'sigla': orgao.sigla,
        'tipo': orgao.tipo,
        'pai_id': orgao.pai_id,
        'ordem': orgao.ordem,
        'ativo': orgao.ativo,
    }


def _wants_json():
    if request.is_json:
        return True
    accept = request.headers.get('Accept', '')
    if 'application/json' in accept and 'text/html' not in accept:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    return False


def _ancestrais(orgao):
    chain = []
    current = orgao
    seen = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        chain.insert(0, current)
        current = current.pai
    return chain


def _candidate_pais(orgao=None):
    """Retorna órgãos que podem ser pai do `orgao` (exclui ele e descendentes)."""
    excluded = set()
    if orgao is not None and orgao.id is not None:
        excluded.add(orgao.id)
        excluded.update(get_orgao_descendants(orgao.id))
    todos = OrgaoUnidade.query.order_by(OrgaoUnidade.pai_id.is_(None).desc(), OrgaoUnidade.sigla).all()
    return [o for o in todos if o.id not in excluded]


@main_bp.route('/admin/orgaos')
@login_required
@admin_required
def list_orgaos():
    raizes = (
        OrgaoUnidade.query.filter(OrgaoUnidade.pai_id.is_(None))
        .order_by(OrgaoUnidade.ordem, OrgaoUnidade.sigla)
        .all()
    )
    todos = OrgaoUnidade.query.order_by(OrgaoUnidade.sigla).all()
    return render_template(
        'admin/orgao_tree.html',
        raizes=raizes,
        todos=todos,
        total_unidades=len(todos),
        allowed_tipos=ALLOWED_TIPOS,
        max_depth=MAX_DEPTH,
        tipo_rank=TIPO_RANK,
    )


@main_bp.route('/admin/orgaos/new', methods=['GET', 'POST'])
@login_required
@admin_required
def add_orgao():
    has_root = OrgaoUnidade.query.filter(OrgaoUnidade.pai_id.is_(None)).first() is not None
    is_root = not has_root

    if request.method == 'POST':
        data, error = normalize_orgao_form(request.form, is_root=is_root)
        if error:
            flash(error, 'danger')
            return render_template(
                'admin/orgao_form.html',
                action_verb='Adicionar',
                orgao=request.form,
                is_root=is_root,
                candidate_pais=_candidate_pais(),
                allowed_tipos=ALLOWED_TIPOS,
                preselected_pai_id=request.form.get('pai_id'),
                tipo_rank=TIPO_RANK,
            )

        # Valida profundidade ao inserir
        if not is_root and data['pai_id'] is not None:
            pai = db.session.get(OrgaoUnidade, data['pai_id'])
            if pai is None:
                flash('Órgão pai não encontrado.', 'danger')
                return redirect(url_for('main.add_orgao'))
            if compute_orgao_depth(pai) + 1 > MAX_DEPTH:
                flash(f'Profundidade máxima de {MAX_DEPTH} níveis excedida.', 'danger')
                return redirect(url_for('main.add_orgao', pai_id=pai.id))

        try:
            novo = OrgaoUnidade(**data)
            db.session.add(novo)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            flash(f'Erro ao criar órgão: {exc}', 'danger')
            return redirect(url_for('main.add_orgao'))

        flash(f'Órgão "{novo.sigla}" criado com sucesso.', 'success')
        return redirect(url_for('main.list_orgaos') + f'#orgao-{novo.id}')

    pai_pre = request.args.get('pai_id')
    pai_pre_id = None
    if pai_pre:
        try:
            pai_pre_id = int(pai_pre)
        except (TypeError, ValueError):
            pai_pre_id = None

    return render_template(
        'admin/orgao_form.html',
        action_verb='Adicionar',
        orgao={'ativo': True, 'ordem': 0, 'pai_id': pai_pre_id, 'tipo': 'Estado' if is_root else ''},
        is_root=is_root,
        candidate_pais=_candidate_pais(),
        allowed_tipos=ALLOWED_TIPOS,
        preselected_pai_id=pai_pre_id,
        tipo_rank=TIPO_RANK,
    )


@main_bp.route('/admin/orgaos/<int:orgao_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_orgao(orgao_id):
    orgao = get_or_404(OrgaoUnidade, orgao_id)
    is_root = orgao.pai_id is None

    if request.method == 'POST':
        data, error = normalize_orgao_form(request.form, is_root=is_root)
        if error:
            flash(error, 'danger')
            return render_template(
                'admin/orgao_form.html',
                action_verb='Editar',
                orgao=request.form,
                is_root=is_root,
                candidate_pais=_candidate_pais(orgao),
                allowed_tipos=ALLOWED_TIPOS,
                preselected_pai_id=request.form.get('pai_id'),
                editing_id=orgao.id,
                tipo_rank=TIPO_RANK,
            )

        if not is_root and data['pai_id'] != orgao.pai_id:
            move_error = validate_orgao_move(orgao, data['pai_id'], child_tipo=data['tipo'])
            if move_error:
                flash(move_error, 'danger')
                return redirect(url_for('main.edit_orgao', orgao_id=orgao.id))

        try:
            orgao.nome = data['nome']
            orgao.sigla = data['sigla']
            orgao.tipo = data['tipo']
            if not is_root:
                orgao.pai_id = data['pai_id']
            orgao.ordem = data['ordem']
            orgao.ativo = data['ativo']
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            flash(f'Erro ao atualizar órgão: {exc}', 'danger')
            return redirect(url_for('main.edit_orgao', orgao_id=orgao.id))

        flash(f'Órgão "{orgao.sigla}" atualizado com sucesso.', 'success')
        return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')

    return render_template(
        'admin/orgao_form.html',
        action_verb='Editar',
        orgao=orgao,
        is_root=is_root,
        candidate_pais=_candidate_pais(orgao),
        allowed_tipos=ALLOWED_TIPOS,
        preselected_pai_id=orgao.pai_id,
        editing_id=orgao.id,
        tipo_rank=TIPO_RANK,
    )


@main_bp.route('/admin/orgaos/<int:orgao_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_orgao(orgao_id):
    orgao = get_or_404(OrgaoUnidade, orgao_id)

    if orgao.filhos:
        flash('Mova as subunidades antes de excluir.', 'warning')
        return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')

    if orgao.pai_id is None:
        flash('Não é possível excluir o órgão raiz.', 'warning')
        return redirect(url_for('main.list_orgaos'))

    sigla = orgao.sigla
    parent_id = orgao.pai_id
    try:
        db.session.delete(orgao)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Erro ao excluir órgão: {exc}', 'danger')
        return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')

    flash(f'Órgão "{sigla}" excluído com sucesso.', 'success')
    return redirect(url_for('main.list_orgaos') + f'#orgao-{parent_id}')


@main_bp.route('/admin/orgaos/<int:orgao_id>/move', methods=['POST'])
@login_required
@admin_required
def move_orgao(orgao_id):
    orgao = get_or_404(OrgaoUnidade, orgao_id)

    payload = request.get_json(silent=True) or {}
    raw_pai = payload.get('pai_id') if 'pai_id' in payload else request.form.get('pai_id')

    if raw_pai in (None, '', 'None', 'null'):
        new_pai_id = None
    else:
        try:
            new_pai_id = int(raw_pai)
        except (TypeError, ValueError):
            msg = 'Órgão pai inválido.'
            if _wants_json():
                return jsonify({'ok': False, 'error': msg}), 400
            flash(msg, 'danger')
            return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')

    error = validate_orgao_move(orgao, new_pai_id)
    if error:
        if _wants_json():
            return jsonify({'ok': False, 'error': error}), 400
        flash(error, 'danger')
        return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')

    try:
        orgao.pai_id = new_pai_id
        if new_pai_id is not None:
            siblings_count = (
                OrgaoUnidade.query.filter(OrgaoUnidade.pai_id == new_pai_id)
                .filter(OrgaoUnidade.id != orgao.id)
                .count()
            )
            orgao.ordem = siblings_count
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if _wants_json():
            return jsonify({'ok': False, 'error': str(exc)}), 500
        flash(f'Erro ao mover órgão: {exc}', 'danger')
        return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')

    if _wants_json():
        return jsonify({'ok': True, 'orgao': _serialize_orgao(orgao)})

    flash(f'Órgão "{orgao.sigla}" movido com sucesso.', 'success')
    return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')


@main_bp.route('/admin/orgaos/<int:orgao_id>/reorder', methods=['POST'])
@login_required
@admin_required
def reorder_orgao(orgao_id):
    orgao = get_or_404(OrgaoUnidade, orgao_id)
    direction = (request.form.get('direction') or '').lower()

    if direction not in ('up', 'down'):
        flash('Direção inválida.', 'danger')
        return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')

    siblings = (
        OrgaoUnidade.query.filter(OrgaoUnidade.pai_id == orgao.pai_id)
        .order_by(OrgaoUnidade.ordem, OrgaoUnidade.sigla)
        .all()
    )
    indices = {s.id: i for i, s in enumerate(siblings)}
    idx = indices.get(orgao.id)
    if idx is None:
        return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')

    target_idx = idx - 1 if direction == 'up' else idx + 1
    if target_idx < 0 or target_idx >= len(siblings):
        return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')

    other = siblings[target_idx]
    try:
        orgao.ordem, other.ordem = other.ordem, orgao.ordem
        if orgao.ordem == other.ordem:
            orgao.ordem = target_idx
            other.ordem = idx
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Erro ao reordenar: {exc}', 'danger')

    return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')


@main_bp.route('/admin/orgaos/<int:orgao_id>/toggle-ativo', methods=['POST'])
@login_required
@admin_required
def toggle_orgao_ativo(orgao_id):
    orgao = get_or_404(OrgaoUnidade, orgao_id)
    try:
        orgao.ativo = not orgao.ativo
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Erro ao alterar status: {exc}', 'danger')
        return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')

    estado = 'ativado' if orgao.ativo else 'desativado'
    flash(f'Órgão "{orgao.sigla}" {estado}.', 'success')
    return redirect(url_for('main.list_orgaos') + f'#orgao-{orgao.id}')
