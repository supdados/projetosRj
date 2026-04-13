from models import CadernoBlock, CadernoState, db


def test_caderno_template_contains_grid_and_expand_contract(client_user):
    response = client_user.get('/caderno')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    required_hooks = [
        'id="cadernoComposer"',
        'id="cadernoPaper"',
        'id="cadernoCanvasWrap"',
        'id="cadernoSheetFooter"',
        'id="cadernoBlocks"',
        'id="cadernoExpandZone"',
        'id="cadernoExpandZoneLabel"',
        'apiStateUrl:',
    ]

    for hook in required_hooks:
        assert hook in html


def test_caderno_blocks_api_returns_sheet_and_layout_fields(app, client_user, seed_data):
    with app.app_context():
        db.session.add(CadernoState(user_id=seed_data['user_id'], expand_steps=2))
        db.session.add_all(
            [
                CadernoBlock(
                    user_id=seed_data['user_id'],
                    block_type='text',
                    content='Texto do caderno',
                    position=1000,
                    size_preset='G',
                    grid_x=0,
                    grid_y=0,
                    grid_w=12,
                    grid_h=6,
                ),
                CadernoBlock(
                    user_id=seed_data['user_id'],
                    block_type='project',
                    reference_id=seed_data['project_id'],
                    position=2000,
                    size_preset='M',
                    grid_x=0,
                    grid_y=6,
                    grid_w=6,
                    grid_h=5,
                ),
            ]
        )
        db.session.commit()

    response = client_user.get('/api/caderno/blocks')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['sheet'] == {'expand_steps': 2, 'max_expand_steps': 3}
    assert len(payload['blocks']) == 2

    first_block = payload['blocks'][0]
    assert {
        'id',
        'block_type',
        'content',
        'reference_id',
        'position',
        'size_preset',
        'grid_x',
        'grid_y',
        'grid_w',
        'grid_h',
        'ref_data',
    }.issubset(first_block.keys())
    assert first_block['size_preset'] == 'G'
    assert first_block['grid_w'] == 12
    assert first_block['grid_h'] == 6

    project_block = next(block for block in payload['blocks'] if block['block_type'] == 'project')
    assert project_block['ref_data']['id'] == seed_data['project_id']
    assert project_block['ref_data']['titulo'] == 'Projeto Auditoria'


def test_caderno_block_patch_updates_layout_contract(app, client_user, seed_data):
    with app.app_context():
        block = CadernoBlock(
            user_id=seed_data['user_id'],
            block_type='text',
            content='Ajustar tamanho',
            position=1000,
            size_preset='M',
            grid_x=0,
            grid_y=0,
            grid_w=6,
            grid_h=5,
        )
        db.session.add(block)
        db.session.commit()
        block_id = block.id

    response = client_user.patch(
        f'/api/caderno/blocks/{block_id}',
        json={
            'size_preset': 'P',
            'grid_x': 3,
            'grid_y': 4,
            'grid_w': 3,
            'grid_h': 7,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['block']['size_preset'] == 'P'
    assert payload['block']['grid_x'] == 3
    assert payload['block']['grid_y'] == 4
    assert payload['block']['grid_w'] == 3
    assert payload['block']['grid_h'] == 7

    with app.app_context():
        block = db.session.get(CadernoBlock, block_id)
        assert block.size_preset == 'P'
        assert block.grid_x == 3
        assert block.grid_y == 4
        assert block.grid_w == 3
        assert block.grid_h == 7


def test_caderno_state_patch_persists_expand_steps_and_rejects_invalid_values(app, client_user, seed_data):
    ok_response = client_user.patch('/api/caderno/state', json={'expand_steps': 3})

    assert ok_response.status_code == 200
    assert ok_response.get_json()['sheet'] == {'expand_steps': 3, 'max_expand_steps': 3}

    with app.app_context():
        state = CadernoState.query.filter_by(user_id=seed_data['user_id']).first()
        assert state is not None
        assert state.expand_steps == 3

    bad_response = client_user.patch('/api/caderno/state', json={'expand_steps': 4})
    assert bad_response.status_code == 400
    assert bad_response.get_json() == {'error': 'expand_steps deve estar entre 0 e 3.'}
