from models import OrgaoUnidade, db


def _reset_orgaos(app):
    with app.app_context():
        OrgaoUnidade.query.delete()
        db.session.commit()


def _create_chain(app, tipos, parent_id=None, base_depth=0):
    """Cria uma cadeia linear de órgãos com os tipos informados.

    Retorna a lista de ids (da raiz para a folha da cadeia criada).
    """
    created = []
    with app.app_context():
        current_parent = parent_id
        for idx, tipo in enumerate(tipos):
            depth = base_depth + idx
            sigla = f"N{depth}"
            node = OrgaoUnidade(
                nome=f"Nivel {depth} {tipo}",
                sigla=sigla,
                tipo=tipo,
                pai_id=current_parent,
                ordem=0,
                ativo=True,
            )
            db.session.add(node)
            db.session.flush()
            created.append(node.id)
            current_parent = node.id
        db.session.commit()
    return created


def test_create_root_orgao_when_tree_is_empty(client_admin, app):
    _reset_orgaos(app)

    response = client_admin.post(
        "/admin/orgaos/new",
        data={
            "nome": "Estado do Rio de Janeiro",
            "sigla": "ERJ",
            "tipo": "Estado",
            "pai_id": "",
            "ordem": "0",
            "ativo": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        root = OrgaoUnidade.query.filter_by(tipo="Estado").one()
        assert root.sigla == "ERJ"
        assert root.pai_id is None


def test_create_child_with_valid_parent(client_admin, app, seed_data):
    response = client_admin.post(
        "/admin/orgaos/new",
        data={
            "nome": "Subsecretaria X",
            "sigla": "SUBX",
            "tipo": "Subsecretaria",
            "pai_id": str(seed_data["orgao_child_id"]),  # Secretaria
            "ordem": "0",
            "ativo": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        novo = OrgaoUnidade.query.filter_by(sigla="SUBX").one()
        assert novo.tipo == "Subsecretaria"
        assert novo.pai_id == seed_data["orgao_child_id"]


def test_create_superintendencia_below_subsecretaria(client_admin, app, seed_data):
    with app.app_context():
        sub = OrgaoUnidade(
            nome="Subsecretaria Base",
            sigla="SUBB",
            tipo="Subsecretaria",
            pai_id=seed_data["orgao_child_id"],
            ordem=0,
            ativo=True,
        )
        db.session.add(sub)
        db.session.commit()
        sub_id = sub.id

    response = client_admin.post(
        "/admin/orgaos/new",
        data={
            "nome": "Superintendencia X",
            "sigla": "SUPX",
            "tipo": "Superintendência",
            "pai_id": str(sub_id),
            "ordem": "0",
            "ativo": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        novo = OrgaoUnidade.query.filter_by(sigla="SUPX").one()
        assert novo.tipo == "Superintendência"
        assert novo.pai_id == sub_id


def test_create_rejects_invalid_parent_rank(client_admin, app, seed_data):
    # Tenta criar Secretaria (rank 1) como filho de Secretaria (rank 1) — inválido.
    response = client_admin.post(
        "/admin/orgaos/new",
        data={
            "nome": "Secretaria Filha Invalida",
            "sigla": "SFIN",
            "tipo": "Secretaria",
            "pai_id": str(seed_data["orgao_child_id"]),
            "ordem": "0",
            "ativo": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "não pode ser pai" in html
    with app.app_context():
        assert OrgaoUnidade.query.filter_by(sigla="SFIN").count() == 0


def test_create_rejects_when_max_depth_exceeded(client_admin, app, seed_data):
    # Cria cadeia descendente até o limite, depois tenta exceder.
    # Raiz (ERJ, Estado, depth=1) → Secretaria (depth=2) já existem no seed.
    # Continuamos: Subsecretaria (3) → Coordenação (4) → Departamento (5)  [chega no MAX_DEPTH=5]
    chain_ids = _create_chain(
        app,
        ["Subsecretaria", "Coordenação", "Departamento"],
        parent_id=seed_data["orgao_child_id"],
        base_depth=3,
    )
    deepest_id = chain_ids[-1]

    # Tentar criar Núcleo (rank 6) filho da folha (depth=5) → depth 6 > MAX_DEPTH.
    response = client_admin.post(
        "/admin/orgaos/new",
        data={
            "nome": "Nucleo Alem Do Limite",
            "sigla": "NCL",
            "tipo": "Núcleo",
            "pai_id": str(deepest_id),
            "ordem": "0",
            "ativo": "1",
        },
        follow_redirects=True,
    )

    html = response.get_data(as_text=True)
    assert "Profundidade máxima" in html
    with app.app_context():
        assert OrgaoUnidade.query.filter_by(sigla="NCL").count() == 0


def test_edit_preserves_fields_and_updates(client_admin, app, seed_data):
    response = client_admin.post(
        f'/admin/orgaos/{seed_data["orgao_child_id"]}/edit',
        data={
            "nome": "Secretaria Renomeada",
            "sigla": "SREN",
            "tipo": "Secretaria",
            "pai_id": str(seed_data["orgao_root_id"]),
            "ordem": "2",
            "ativo": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        orgao = db.session.get(OrgaoUnidade, seed_data["orgao_child_id"])
        assert orgao.nome == "Secretaria Renomeada"
        assert orgao.sigla == "SREN"
        assert orgao.ordem == 2


def test_edit_allows_changing_type_and_parent_together(client_admin, app, seed_data):
    with app.app_context():
        sub_pai = OrgaoUnidade(
            nome="Subsecretaria Pai",
            sigla="SUBP",
            tipo="Subsecretaria",
            pai_id=seed_data["orgao_child_id"],
            ordem=0,
            ativo=True,
        )
        sub_filha = OrgaoUnidade(
            nome="Subsecretaria Filha",
            sigla="SUBF",
            tipo="Subsecretaria",
            pai_id=seed_data["orgao_child_id"],
            ordem=1,
            ativo=True,
        )
        db.session.add_all([sub_pai, sub_filha])
        db.session.commit()
        sub_pai_id = sub_pai.id
        sub_filha_id = sub_filha.id

    response = client_admin.post(
        f"/admin/orgaos/{sub_filha_id}/edit",
        data={
            "nome": "Superintendencia Filha",
            "sigla": "SUBF",
            "tipo": "Superintendência",
            "pai_id": str(sub_pai_id),
            "ordem": "1",
            "ativo": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        orgao = db.session.get(OrgaoUnidade, sub_filha_id)
        assert orgao is not None
        assert orgao.tipo == "Superintendência"
        assert orgao.pai_id == sub_pai_id


def test_move_orgao_prevents_cycle(client_admin, app, seed_data):
    # Cria cadeia root → child → grandchild (Subsecretaria).
    chain_ids = _create_chain(
        app,
        ["Subsecretaria"],
        parent_id=seed_data["orgao_child_id"],
        base_depth=3,
    )
    grandchild_id = chain_ids[-1]

    # Tentar mover o pai (Secretaria) para dentro do filho (Subsecretaria).
    response = client_admin.post(
        f'/admin/orgaos/{seed_data["orgao_child_id"]}/move',
        json={"pai_id": grandchild_id},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload and payload.get("ok") is False
    assert "dentro de si" in payload.get("error", "")


def test_move_orgao_json_happy_path(client_admin, app, seed_data):
    # Criar uma segunda Secretaria para mover o filho atual para ela.
    with app.app_context():
        alt = OrgaoUnidade(
            nome="Secretaria Alternativa",
            sigla="SALT",
            tipo="Secretaria",
            pai_id=seed_data["orgao_root_id"],
            ordem=1,
            ativo=True,
        )
        db.session.add(alt)
        db.session.commit()
        alt_id = alt.id

    # Cria uma Subsecretaria filha da original para movê-la para a alternativa.
    with app.app_context():
        sub = OrgaoUnidade(
            nome="Subsecretaria Movel",
            sigla="SUMO",
            tipo="Subsecretaria",
            pai_id=seed_data["orgao_child_id"],
            ordem=0,
            ativo=True,
        )
        db.session.add(sub)
        db.session.commit()
        sub_id = sub.id

    response = client_admin.post(
        f"/admin/orgaos/{sub_id}/move",
        json={"pai_id": alt_id},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["orgao"]["pai_id"] == alt_id


def test_delete_blocked_when_has_children(client_admin, app, seed_data):
    # Secretaria (child) não tem filhos ainda; criar um para garantir.
    with app.app_context():
        sub = OrgaoUnidade(
            nome="Sub Temporaria",
            sigla="STMP",
            tipo="Subsecretaria",
            pai_id=seed_data["orgao_child_id"],
            ordem=0,
            ativo=True,
        )
        db.session.add(sub)
        db.session.commit()

    response = client_admin.post(
        f'/admin/orgaos/{seed_data["orgao_child_id"]}/delete',
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Mova as subunidades" in html
    with app.app_context():
        assert db.session.get(OrgaoUnidade, seed_data["orgao_child_id"]) is not None


def test_delete_blocks_root(client_admin, app, seed_data):
    # Remover o filho primeiro para liberar o root do bloqueio de filhos.
    with app.app_context():
        child = db.session.get(OrgaoUnidade, seed_data["orgao_child_id"])
        db.session.delete(child)
        db.session.commit()

    response = client_admin.post(
        f'/admin/orgaos/{seed_data["orgao_root_id"]}/delete',
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "raiz" in html.lower()
    with app.app_context():
        assert db.session.get(OrgaoUnidade, seed_data["orgao_root_id"]) is not None


def test_reorder_swaps_siblings(client_admin, app, seed_data):
    with app.app_context():
        second = OrgaoUnidade(
            nome="Secretaria B",
            sigla="SECB",
            tipo="Secretaria",
            pai_id=seed_data["orgao_root_id"],
            ordem=1,
            ativo=True,
        )
        db.session.add(second)
        db.session.commit()
        second_id = second.id
        first_id = seed_data["orgao_child_id"]

    response = client_admin.post(
        f"/admin/orgaos/{second_id}/reorder",
        data={"direction": "up"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        first = db.session.get(OrgaoUnidade, first_id)
        second = db.session.get(OrgaoUnidade, second_id)
        assert second.ordem < first.ordem


def test_toggle_ativo_flips_state(client_admin, app, seed_data):
    with app.app_context():
        before = db.session.get(OrgaoUnidade, seed_data["orgao_child_id"]).ativo

    response = client_admin.post(
        f'/admin/orgaos/{seed_data["orgao_child_id"]}/toggle-ativo',
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        after = db.session.get(OrgaoUnidade, seed_data["orgao_child_id"]).ativo
    assert after is not before
