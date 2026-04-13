from flask import g, jsonify, request, url_for

from models import CadernoBlock, CadernoState, Etapa, Project, Task
from models.base import db
from models.caderno import CADERNO_BLOCK_TYPES, MAX_CADERNO_EXPAND_STEPS

from ..blueprint import main_bp
from ..decorators import login_required

GRID_COLUMNS = 12
DEFAULT_GRID_W = 6
TEXT_DEFAULT_GRID_H = 5
CARD_DEFAULT_GRID_H = 3
TEXT_MIN_GRID_H = 2
CARD_MIN_GRID_W = 3
CARD_MIN_GRID_H = 2


def _next_position(user_id):
    max_pos = db.session.query(db.func.max(CadernoBlock.position)).filter(
        CadernoBlock.user_id == user_id
    ).scalar()
    return (max_pos or 0.0) + 1000.0


def _coerce_int(value, *, default=None, minimum=None, maximum=None):
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and coerced < minimum:
        return minimum
    if maximum is not None and coerced > maximum:
        return maximum
    return coerced


def _default_layout_for_block_type(_block_type):
    block_type = str(_block_type or 'text')
    return {
        'grid_w': DEFAULT_GRID_W,
        'grid_h': TEXT_DEFAULT_GRID_H if block_type == 'text' else CARD_DEFAULT_GRID_H,
    }


def _minimum_grid_width(block_type):
    return CARD_MIN_GRID_W if block_type != 'text' else 1


def _minimum_grid_height(block_type):
    return CARD_MIN_GRID_H if block_type != 'text' else TEXT_MIN_GRID_H


def _clamp_grid_width(value, *, block_type='text', default=DEFAULT_GRID_W):
    return _coerce_int(
        value,
        default=default,
        minimum=_minimum_grid_width(block_type),
        maximum=GRID_COLUMNS,
    )


def _clamp_grid_height(value, *, block_type='text', default=TEXT_DEFAULT_GRID_H):
    return _coerce_int(
        value,
        default=default,
        minimum=_minimum_grid_height(block_type),
    )


def _occupy_cells(occupied, grid_x, grid_y, grid_w, grid_h):
    for offset_y in range(grid_h):
        for offset_x in range(grid_w):
            occupied.add((grid_x + offset_x, grid_y + offset_y))


def _find_next_available_slot(blocks, grid_w, grid_h):
    occupied = set()
    for block in sorted(blocks, key=lambda item: (item.grid_y, item.grid_x, item.id)):
        if block.block_type == 'nota':
            continue
        _occupy_cells(
            occupied,
            max(0, _coerce_int(block.grid_x, default=0) or 0),
            max(0, _coerce_int(block.grid_y, default=0) or 0),
            _clamp_grid_width(block.grid_w),
            _clamp_grid_height(block.grid_h),
        )

    y = 0
    max_x = max(0, GRID_COLUMNS - grid_w)
    while True:
        for x in range(0, max_x + 1):
            fits = True
            for offset_y in range(grid_h):
                for offset_x in range(grid_w):
                    if (x + offset_x, y + offset_y) in occupied:
                        fits = False
                        break
                if not fits:
                    break
            if fits:
                return x, y
        y += 1


def _build_layout_payload(data, *, block_type='text', current_block=None, for_create=False):
    resolved_block_type = current_block.block_type if current_block is not None else block_type
    defaults = _default_layout_for_block_type(resolved_block_type)

    grid_w = _clamp_grid_width(
        data.get('grid_w', current_block.grid_w if current_block else defaults['grid_w']),
        block_type=resolved_block_type,
        default=defaults['grid_w'],
    )
    grid_h = _clamp_grid_height(
        data.get('grid_h', current_block.grid_h if current_block else defaults['grid_h']),
        block_type=resolved_block_type,
        default=defaults['grid_h'],
    )

    grid_x = _coerce_int(
        data.get('grid_x', current_block.grid_x if current_block else None),
        default=None,
        minimum=0,
    )
    max_grid_x = max(0, GRID_COLUMNS - grid_w)
    if grid_x is not None:
        grid_x = min(grid_x, max_grid_x)

    grid_y = _coerce_int(
        data.get('grid_y', current_block.grid_y if current_block else None),
        default=None,
        minimum=0,
    )

    if current_block is None and (grid_x is None or grid_y is None):
        existing_blocks = CadernoBlock.query.filter(
            CadernoBlock.user_id == g.user.id
        ).all()
        next_grid_x, next_grid_y = _find_next_available_slot(existing_blocks, grid_w, grid_h)
        grid_x = next_grid_x if grid_x is None else grid_x
        grid_y = next_grid_y if grid_y is None else grid_y

    return {
        'grid_x': grid_x if grid_x is not None else 0,
        'grid_y': grid_y if grid_y is not None else 0,
        'grid_w': grid_w,
        'grid_h': grid_h,
    }


def _build_attachment_payload(data, *, block_type='text', current_block=None):
    resolved_block_type = current_block.block_type if current_block is not None else block_type
    if resolved_block_type != 'nota':
        return {
            'attached_to_block_id': None,
            'attached_offset_x': 0,
            'attached_offset_y': 0,
        }

    attached_to_block_id = _coerce_int(
        data.get(
            'attached_to_block_id',
            current_block.attached_to_block_id if current_block is not None else None,
        ),
        default=None,
        minimum=1,
    )

    if attached_to_block_id is None:
        return {
            'attached_to_block_id': None,
            'attached_offset_x': 0,
            'attached_offset_y': 0,
        }

    if current_block is not None and attached_to_block_id == current_block.id:
        return {
            'attached_to_block_id': None,
            'attached_offset_x': 0,
            'attached_offset_y': 0,
        }

    parent_block = CadernoBlock.query.filter(
        CadernoBlock.user_id == g.user.id,
        CadernoBlock.id == attached_to_block_id,
    ).first()
    if parent_block is None or parent_block.block_type == 'nota':
        return {
            'attached_to_block_id': None,
            'attached_offset_x': 0,
            'attached_offset_y': 0,
        }

    return {
        'attached_to_block_id': parent_block.id,
        'attached_offset_x': _coerce_int(
            data.get(
                'attached_offset_x',
                current_block.attached_offset_x if current_block is not None else 0,
            ),
            default=0,
        ),
        'attached_offset_y': _coerce_int(
            data.get(
                'attached_offset_y',
                current_block.attached_offset_y if current_block is not None else 0,
            ),
            default=0,
        ),
    }


def _serialize_sheet(state):
    expand_steps = 0
    if state is not None:
        expand_steps = _coerce_int(state.expand_steps, default=0, minimum=0, maximum=MAX_CADERNO_EXPAND_STEPS)
    return {
        'expand_steps': expand_steps,
        'max_expand_steps': MAX_CADERNO_EXPAND_STEPS,
    }


def _serialize_block(block):
    base = {
        'id': block.id,
        'block_type': block.block_type,
        'content': block.content or '',
        'reference_id': block.reference_id,
        'position': block.position,
        'grid_x': _coerce_int(block.grid_x, default=0, minimum=0),
        'grid_y': _coerce_int(block.grid_y, default=0, minimum=0),
        'grid_w': _clamp_grid_width(block.grid_w, block_type=block.block_type),
        'grid_h': _clamp_grid_height(block.grid_h, block_type=block.block_type),
        'attached_to_block_id': _coerce_int(block.attached_to_block_id, default=None, minimum=1),
        'attached_offset_x': _coerce_int(block.attached_offset_x, default=0),
        'attached_offset_y': _coerce_int(block.attached_offset_y, default=0),
        'created_at': block.created_at.isoformat() if block.created_at else None,
        'updated_at': block.updated_at.isoformat() if block.updated_at else None,
        'ref_data': None,
    }

    if block.block_type == 'project' and block.reference_id:
        proj = db.session.get(Project, block.reference_id)
        if proj:
            base['ref_data'] = {
                'id': proj.id,
                'titulo': proj.titulo,
                'status': proj.status,
                'area': proj.area_responsavel or '',
                'orgao': proj.orgao or '',
                'prioridade': proj.prioridade or '',
                'url': url_for('main.project_detail', project_id=proj.id),
                'total_etapas': proj.total_workflow_etapas,
                'etapas_concluidas': sum(1 for etapa in proj.workflow_etapas if etapa.done),
            }

    elif block.block_type == 'etapa' and block.reference_id:
        etapa = db.session.get(Etapa, block.reference_id)
        if etapa:
            base['ref_data'] = {
                'id': etapa.id,
                'descricao': etapa.descricao,
                'done': etapa.done,
                'iniciada': etapa.iniciada,
                'data_inicio': etapa.data_inicio.isoformat() if etapa.data_inicio else None,
                'data_fim': etapa.data_fim.isoformat() if etapa.data_fim else None,
                'responsavel': etapa.responsavel or '',
                'project_titulo': etapa.project.titulo if etapa.project else '',
                'url': url_for('main.project_detail', project_id=etapa.project_id, _anchor=f'etapa-{etapa.id}'),
            }

    elif block.block_type == 'tarefa' and block.reference_id:
        task = db.session.get(Task, block.reference_id)
        if task:
            base['ref_data'] = {
                'id': task.id,
                'descricao': task.descricao,
                'status': task.status,
                'prioridade': task.prioridade or '',
                'responsavel': task.responsavel or '',
                'project_titulo': task.project.titulo if task.project else 'Sem projeto',
                'url': url_for('main.task_detail', task_id=task.id),
            }

    return base


def _get_or_create_state():
    state = CadernoState.query.filter_by(user_id=g.user.id).first()
    if state is None:
        state = CadernoState(user_id=g.user.id, expand_steps=0)
        db.session.add(state)
        db.session.flush()
    return state


@main_bp.route('/api/caderno/blocks', methods=['GET'])
@login_required
def caderno_api_blocks():
    blocks = (
        CadernoBlock.query
        .filter(CadernoBlock.user_id == g.user.id)
        .order_by(CadernoBlock.grid_y.asc(), CadernoBlock.grid_x.asc(), CadernoBlock.id.asc())
        .all()
    )
    state = CadernoState.query.filter_by(user_id=g.user.id).first()
    return jsonify({
        'sheet': _serialize_sheet(state),
        'blocks': [_serialize_block(block) for block in blocks],
    })


@main_bp.route('/api/caderno/blocks', methods=['POST'])
@login_required
def caderno_api_blocks_create():
    data = request.get_json(silent=True) or {}
    block_type = data.get('block_type', 'text')

    if block_type not in CADERNO_BLOCK_TYPES:
        return jsonify({'error': 'Tipo de bloco inválido.'}), 400

    if block_type in ('project', 'etapa', 'tarefa'):
        reference_id = data.get('reference_id')
        if not reference_id or not isinstance(reference_id, int) or reference_id <= 0:
            return jsonify({'error': 'reference_id obrigatório para este tipo de bloco.'}), 400

        if block_type == 'project' and not db.session.get(Project, reference_id):
            return jsonify({'error': 'Projeto não encontrado.'}), 404
        if block_type == 'etapa' and not db.session.get(Etapa, reference_id):
            return jsonify({'error': 'Etapa não encontrada.'}), 404
        if block_type == 'tarefa' and not db.session.get(Task, reference_id):
            return jsonify({'error': 'Tarefa não encontrada.'}), 404
    else:
        reference_id = None

    layout = _build_layout_payload(data, block_type=block_type, for_create=True)
    position = data.get('position')
    if position is None:
        position = _next_position(g.user.id)

    block = CadernoBlock(
        user_id=g.user.id,
        block_type=block_type,
        content=data.get('content', ''),
        reference_id=reference_id,
        position=float(position),
        grid_x=layout['grid_x'],
        grid_y=layout['grid_y'],
        grid_w=layout['grid_w'],
        grid_h=layout['grid_h'],
    )
    attachment = _build_attachment_payload(data, block_type=block_type)
    block.attached_to_block_id = attachment['attached_to_block_id']
    block.attached_offset_x = attachment['attached_offset_x']
    block.attached_offset_y = attachment['attached_offset_y']
    db.session.add(block)
    db.session.commit()
    return jsonify({'block': _serialize_block(block), 'sheet': _serialize_sheet(None)}), 201


@main_bp.route('/api/caderno/blocks/reorder', methods=['POST'])
@login_required
def caderno_api_blocks_reorder():
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'error': 'Nenhum item fornecido.'}), 400

    ids = [item['id'] for item in items if isinstance(item.get('id'), int)]
    blocks_map = {
        block.id: block
        for block in CadernoBlock.query.filter(
            CadernoBlock.user_id == g.user.id,
            CadernoBlock.id.in_(ids),
        ).all()
    }

    updated = 0
    for item in items:
        block = blocks_map.get(item.get('id'))
        if block is None:
            continue

        layout = _build_layout_payload(item, current_block=block)
        block.grid_x = layout['grid_x']
        block.grid_y = layout['grid_y']
        block.grid_w = layout['grid_w']
        block.grid_h = layout['grid_h']
        attachment = _build_attachment_payload(item, current_block=block)
        block.attached_to_block_id = attachment['attached_to_block_id']
        block.attached_offset_x = attachment['attached_offset_x']
        block.attached_offset_y = attachment['attached_offset_y']

        if item.get('position') is not None:
            block.position = float(item['position'])
        updated += 1

    db.session.commit()
    return jsonify({'success': True, 'updated': updated})


@main_bp.route('/api/caderno/state', methods=['PATCH'])
@login_required
def caderno_api_state_update():
    data = request.get_json(silent=True) or {}
    if 'expand_steps' not in data:
        return jsonify({'error': 'expand_steps é obrigatório.'}), 400

    expand_steps = _coerce_int(data.get('expand_steps'))
    if expand_steps is None or expand_steps < 0 or expand_steps > MAX_CADERNO_EXPAND_STEPS:
        return jsonify({'error': f'expand_steps deve estar entre 0 e {MAX_CADERNO_EXPAND_STEPS}.'}), 400

    state = _get_or_create_state()
    state.expand_steps = expand_steps
    db.session.commit()
    return jsonify({'sheet': _serialize_sheet(state)})


@main_bp.route('/api/caderno/blocks/<int:block_id>', methods=['PATCH'])
@login_required
def caderno_api_block_update(block_id):
    block = db.session.get(CadernoBlock, block_id)
    if not block or block.user_id != g.user.id:
        return jsonify({'error': 'Bloco não encontrado.'}), 404

    data = request.get_json(silent=True) or {}
    if 'content' in data:
        block.content = data['content']
    if 'position' in data:
        block.position = float(data['position'])

    if {'grid_x', 'grid_y', 'grid_w', 'grid_h'} & set(data.keys()):
        layout = _build_layout_payload(data, current_block=block)
        block.grid_x = layout['grid_x']
        block.grid_y = layout['grid_y']
        block.grid_w = layout['grid_w']
        block.grid_h = layout['grid_h']

    if {'attached_to_block_id', 'attached_offset_x', 'attached_offset_y'} & set(data.keys()):
        attachment = _build_attachment_payload(data, current_block=block)
        block.attached_to_block_id = attachment['attached_to_block_id']
        block.attached_offset_x = attachment['attached_offset_x']
        block.attached_offset_y = attachment['attached_offset_y']

    db.session.commit()
    return jsonify({'block': _serialize_block(block)})


@main_bp.route('/api/caderno/blocks/<int:block_id>', methods=['DELETE'])
@login_required
def caderno_api_block_delete(block_id):
    block = db.session.get(CadernoBlock, block_id)
    if not block or block.user_id != g.user.id:
        return jsonify({'error': 'Bloco não encontrado.'}), 404

    if block.block_type != 'nota':
        attached_notes = CadernoBlock.query.filter(
            CadernoBlock.user_id == g.user.id,
            CadernoBlock.block_type == 'nota',
            CadernoBlock.attached_to_block_id == block.id,
        ).all()
        for attached_note in attached_notes:
            attached_note.attached_to_block_id = None
            attached_note.attached_offset_x = 0
            attached_note.attached_offset_y = 0

    db.session.delete(block)
    db.session.commit()
    return jsonify({'success': True, 'id': block_id})
