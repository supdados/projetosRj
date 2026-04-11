from flask import g, jsonify, request, url_for

from models import CadernoBlock, Etapa, Project, Task
from models.base import db
from models.caderno import CADERNO_BLOCK_TYPES

from ..blueprint import main_bp
from ..decorators import login_required


def _next_position(user_id):
    max_pos = db.session.query(db.func.max(CadernoBlock.position)).filter(
        CadernoBlock.user_id == user_id
    ).scalar()
    return (max_pos or 0.0) + 1000.0


def _serialize_block(block):
    base = {
        'id':           block.id,
        'block_type':   block.block_type,
        'content':      block.content or '',
        'reference_id': block.reference_id,
        'position':     block.position,
        'created_at':   block.created_at.isoformat() if block.created_at else None,
        'updated_at':   block.updated_at.isoformat() if block.updated_at else None,
        'ref_data':     None,
    }

    if block.block_type == 'project' and block.reference_id:
        proj = db.session.get(Project, block.reference_id)
        if proj:
            base['ref_data'] = {
                'id':                proj.id,
                'titulo':            proj.titulo,
                'status':            proj.status,
                'area':              proj.area_responsavel or '',
                'orgao':             proj.orgao or '',
                'prioridade':        proj.prioridade or '',
                'url':               url_for('main.project_detail', project_id=proj.id),
                'total_etapas':      proj.total_workflow_etapas,
                'etapas_concluidas': sum(1 for e in proj.workflow_etapas if e.done),
            }

    elif block.block_type == 'etapa' and block.reference_id:
        etapa = db.session.get(Etapa, block.reference_id)
        if etapa:
            base['ref_data'] = {
                'id':             etapa.id,
                'descricao':      etapa.descricao,
                'done':           etapa.done,
                'iniciada':       etapa.iniciada,
                'data_inicio':    etapa.data_inicio.isoformat() if etapa.data_inicio else None,
                'data_fim':       etapa.data_fim.isoformat() if etapa.data_fim else None,
                'responsavel':    etapa.responsavel or '',
                'project_titulo': etapa.project.titulo if etapa.project else '',
                'url':            url_for('main.project_detail', project_id=etapa.project_id, _anchor=f'etapa-{etapa.id}'),
            }

    elif block.block_type == 'tarefa' and block.reference_id:
        task = db.session.get(Task, block.reference_id)
        if task:
            base['ref_data'] = {
                'id':             task.id,
                'descricao':      task.descricao,
                'status':         task.status,
                'prioridade':     task.prioridade or '',
                'responsavel':    task.responsavel or '',
                'project_titulo': task.project.titulo if task.project else 'Sem projeto',
                'url':            url_for('main.task_detail', task_id=task.id),
            }

    return base


@main_bp.route('/api/caderno/blocks', methods=['GET'])
@login_required
def caderno_api_blocks():
    blocks = (
        CadernoBlock.query
        .filter(CadernoBlock.user_id == g.user.id)
        .order_by(CadernoBlock.position.asc(), CadernoBlock.id.asc())
        .all()
    )
    return jsonify({'blocks': [_serialize_block(b) for b in blocks]})


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
        elif block_type == 'etapa' and not db.session.get(Etapa, reference_id):
            return jsonify({'error': 'Etapa não encontrada.'}), 404
        elif block_type == 'tarefa' and not db.session.get(Task, reference_id):
            return jsonify({'error': 'Tarefa não encontrada.'}), 404
    else:
        reference_id = None

    position = data.get('position')
    if position is None:
        position = _next_position(g.user.id)

    block = CadernoBlock(
        user_id=g.user.id,
        block_type=block_type,
        content=data.get('content', ''),
        reference_id=reference_id,
        position=float(position),
    )
    db.session.add(block)
    db.session.commit()
    return jsonify({'block': _serialize_block(block)}), 201


@main_bp.route('/api/caderno/blocks/reorder', methods=['POST'])
@login_required
def caderno_api_blocks_reorder():
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'error': 'Nenhum item fornecido.'}), 400

    ids = [item['id'] for item in items if isinstance(item.get('id'), int)]
    blocks_map = {
        b.id: b
        for b in CadernoBlock.query.filter(
            CadernoBlock.user_id == g.user.id,
            CadernoBlock.id.in_(ids),
        ).all()
    }

    updated = 0
    for item in items:
        block_id = item.get('id')
        pos = item.get('position')
        if block_id in blocks_map and pos is not None:
            blocks_map[block_id].position = float(pos)
            updated += 1

    db.session.commit()
    return jsonify({'success': True, 'updated': updated})


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

    db.session.commit()
    return jsonify({'block': _serialize_block(block)})


@main_bp.route('/api/caderno/blocks/<int:block_id>', methods=['DELETE'])
@login_required
def caderno_api_block_delete(block_id):
    block = db.session.get(CadernoBlock, block_id)
    if not block or block.user_id != g.user.id:
        return jsonify({'error': 'Bloco não encontrado.'}), 404

    db.session.delete(block)
    db.session.commit()
    return jsonify({'success': True, 'id': block_id})
