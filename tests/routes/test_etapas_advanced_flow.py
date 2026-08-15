import datetime

from models import Etapa, ProjectHistory, db


def test_import_model_creates_stages_with_sequential_dates_and_history(
    app, client_user, seed_data
):
    response = client_user.post(
        f"/project/{seed_data['project_id']}/import_model",
        data={
            "template_id": str(seed_data["template_id"]),
            "start_date": "2026-03-10",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert f"/project/{seed_data['project_id']}" in response.headers["Location"]

    with app.app_context():
        etapas = (
            Etapa.query.filter_by(project_id=seed_data["project_id"])
            .order_by(Etapa.ordem.asc(), Etapa.id.asc())
            .all()
        )

        assert [etapa.descricao for etapa in etapas] == [
            "Etapa Planejada",
            "Etapa Iniciada",
            "Planejamento",
            "Execucao",
        ]
        # Planejamento (2 dias úteis) não cruza fim de semana: inicio/fim iguais ao cálculo corrido.
        assert etapas[2].ordem == 2
        assert etapas[2].data_inicio == datetime.date(2026, 3, 10)
        assert etapas[2].data_fim == datetime.date(2026, 3, 11)
        # Execucao (3 dias úteis) começa numa quinta; dias úteis são qui/sex/seg — bate
        # com o preview (addBusinessDays) do ImportModelModal, nunca cai em sábado/domingo.
        assert etapas[3].ordem == 3
        assert etapas[3].data_inicio == datetime.date(2026, 3, 12)
        assert etapas[3].data_fim == datetime.date(2026, 3, 16)

        history = (
            ProjectHistory.query.filter_by(
                project_id=seed_data["project_id"], action_type="import_model"
            )
            .order_by(ProjectHistory.id.desc())
            .first()
        )
        assert history is not None
        assert (
            'Importou 2 etapa(s) do modelo "Template Base"'
            in history.action_description
        )


def test_import_model_stage_dates_always_fall_on_business_days(
    app, client_user, seed_data
):
    """Regressão: import_template_stages somava dias corridos e podia persistir
    data_fim em fim de semana, divergindo do preview do frontend (addBusinessDays
    em ImportModelModal.svelte). Início em sexta força a 1ª etapa a cruzar o fim
    de semana; nenhuma data gerada pode cair em sábado/domingo.
    """
    response = client_user.post(
        f"/project/{seed_data['project_id']}/import_model",
        data={
            "template_id": str(seed_data["template_id"]),
            "start_date": "2026-03-13",  # sexta-feira
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        etapas = (
            Etapa.query.filter_by(project_id=seed_data["project_id"])
            .order_by(Etapa.ordem.asc(), Etapa.id.asc())
            .all()
        )
        planejamento, execucao = etapas[-2], etapas[-1]

        for etapa in (planejamento, execucao):
            assert etapa.data_inicio.weekday() < 5
            assert etapa.data_fim.weekday() < 5

        # Idêntico ao cálculo do preview: Planejamento (2 dias úteis) sex->seg;
        # Execucao (3 dias úteis) ter->qui, encadeada no dia útil seguinte.
        assert planejamento.data_inicio == datetime.date(2026, 3, 13)
        assert planejamento.data_fim == datetime.date(2026, 3, 16)
        assert execucao.data_inicio == datetime.date(2026, 3, 17)
        assert execucao.data_fim == datetime.date(2026, 3, 19)


def test_reorder_etapas_updates_order_for_project_only(app, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas/reordenar",
        json={"etapa_ids": [seed_data["etapa_started_id"], seed_data["etapa_id"]]},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True

    with app.app_context():
        etapa_a = db.session.get(Etapa, seed_data["etapa_id"])
        etapa_b = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa_a is not None
        assert etapa_b is not None
        assert etapa_b.ordem == 0
        assert etapa_a.ordem == 1


def test_reorder_etapas_pins_google_meeting_order(app, client_user, seed_data):
    """Bug 2.17: reordenar pina a reunião Google no RANK visual atual (aqui a
    última posição, ordem 5 no layout etapa=0 < started=2 < reunião=5) e
    renumera todas 0..n-1; a posição da reunião no payload é ignorada. Com o
    código antigo (ordem = índice do payload) a reunião cairia em 1; congelando
    o valor bruto ficaria 5 — ambos falham o assert de rank compactado."""
    with app.app_context():
        etapa_started = db.session.get(Etapa, seed_data["etapa_started_id"])
        etapa_started.ordem = 2
        meeting = Etapa(
            descricao="Reunião Google",
            entry_type="google_meeting",
            project_id=seed_data["project_id"],
            ordem=5,
        )
        db.session.add(meeting)
        db.session.commit()
        meeting_id = meeting.id

    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/etapas/reordenar",
        json={
            "etapa_ids": [
                seed_data["etapa_started_id"],
                meeting_id,
                seed_data["etapa_id"],
            ]
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True

    with app.app_context():
        meeting = db.session.get(Etapa, meeting_id)
        etapa = db.session.get(Etapa, seed_data["etapa_id"])
        etapa_started = db.session.get(Etapa, seed_data["etapa_started_id"])
        # Reunião fica no rank atual (última); regulares seguem o payload.
        assert etapa_started.ordem == 0
        assert etapa.ordem == 1
        assert meeting.ordem == 2
        assert [e["id"] for e in payload["data"]["etapas"]] == [
            seed_data["etapa_started_id"],
            seed_data["etapa_id"],
            meeting_id,
        ]


def test_toggle_iniciada_clears_done_when_stage_is_reopened(
    app, client_user, seed_data
):
    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa is not None
        etapa.iniciada = True
        etapa.done = True
        db.session.commit()

    response = client_user.post(
        f"/api/etapas/{seed_data['etapa_started_id']}/toggle-iniciada"
    )

    assert response.status_code == 200
    etapa_payload = response.get_json()["data"]["etapa"]
    assert etapa_payload["iniciada"] is False
    assert etapa_payload["done"] is False

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa.iniciada is False
        assert etapa.done is False


def test_toggle_done_requires_started_stage_and_toggles_successfully(
    app, client_user, seed_data
):
    blocked = client_user.post(f"/api/etapas/{seed_data['etapa_id']}/toggle")
    assert blocked.status_code == 422
    assert "não foi iniciada" in blocked.get_json()["error"]["message"]

    allowed = client_user.post(f"/api/etapas/{seed_data['etapa_started_id']}/toggle")
    assert allowed.status_code == 200
    assert allowed.get_json()["data"]["etapa"]["done"] is True

    with app.app_context():
        assert db.session.get(Etapa, seed_data["etapa_id"]).done is False
        assert db.session.get(Etapa, seed_data["etapa_started_id"]).done is True


def test_update_etapa_comentario_can_save_and_remove_comment(
    app, client_user, seed_data
):
    save_response = client_user.post(
        f"/api/etapas/{seed_data['etapa_id']}/comentario",
        json={"comentario": "Comentario atualizado via modal"},
    )

    assert save_response.status_code == 200
    assert "salvo com sucesso" in save_response.get_json()["data"]["message"].lower()

    remove_response = client_user.post(
        f"/api/etapas/{seed_data['etapa_id']}/comentario",
        json={"comentario": "   "},
    )

    assert remove_response.status_code == 200
    assert (
        "removido com sucesso" in remove_response.get_json()["data"]["message"].lower()
    )

    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_id"])
        assert etapa is not None
        assert etapa.comentarios is None


def test_update_etapa_comentario_blocks_done_stage(app, client_user, seed_data):
    with app.app_context():
        etapa = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa is not None
        etapa.comentarios = "Em andamento"
        etapa.done = True
        db.session.commit()

    response = client_user.post(
        f"/api/etapas/{seed_data['etapa_started_id']}/comentario",
        json={"comentario": "Tentativa inválida"},
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["ok"] is False
    assert "etapa concluída" in payload["error"]["message"].lower()

    with app.app_context():
        assert (
            db.session.get(Etapa, seed_data["etapa_started_id"]).comentarios
            == "Em andamento"
        )


def test_cascade_date_update_shifts_only_subsequent_stages(app, client_user, seed_data):
    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/cascade",
        json={"etapa_id": seed_data["etapa_id"], "days_diff": 3},
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    with app.app_context():
        etapa_base = db.session.get(Etapa, seed_data["etapa_id"])
        etapa_subsequente = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa_base is not None
        assert etapa_subsequente is not None
        assert etapa_base.data_inicio == datetime.date(2026, 1, 10)
        assert etapa_base.data_fim == datetime.date(2026, 1, 15)
        assert etapa_subsequente.data_inicio == datetime.date(2026, 1, 21)
        assert etapa_subsequente.data_fim == datetime.date(2026, 1, 23)


def test_cascade_date_update_moves_weekend_end_to_next_business_day(
    app, client_user, seed_data
):
    with app.app_context():
        etapa_subsequente = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa_subsequente is not None
        etapa_subsequente.data_fim = datetime.date(2026, 1, 24)  # sábado
        db.session.commit()

    response = client_user.post(
        f"/api/projetos/{seed_data['project_id']}/cascade",
        json={"etapa_id": seed_data["etapa_id"], "days_diff": 1},
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    with app.app_context():
        etapa_subsequente = db.session.get(Etapa, seed_data["etapa_started_id"])
        assert etapa_subsequente is not None
        assert etapa_subsequente.data_inicio == datetime.date(2026, 1, 19)
        assert etapa_subsequente.data_fim == datetime.date(2026, 1, 26)
