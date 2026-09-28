"""Dados sintéticos determinísticos para medir os itens 16–18 da revisão."""

from datetime import date, datetime, timedelta

from models import (
    Etapa,
    EtapaResponsavel,
    OrgaoUnidade,
    Project,
    ProjectCollection,
    ProjectCollectionItem,
    ProjectCollectionShare,
    Task,
    TaskAnexo,
    TaskAssignee,
    TaskComment,
    User,
    UserOrgao,
    db,
)

REFERENCE_DAY = date(2026, 9, 28)
FIXED_TIME = datetime(2026, 9, 1, 12)


def seed_read_workload(project_count: int) -> int:
    """Semeia projetos/etapas/tarefas e coleções; devolve o usuário da medição."""
    area = OrgaoUnidade(nome="Área sintética", sigla="PERF", tipo="Secretaria", ordem=0)
    viewer = User(
        username="benchmark",
        name="Leitor sintético",
        orgao="PERF",
        password_hash="!benchmark-disabled",
        is_admin=False,
    )
    db.session.add_all([area, viewer])
    db.session.flush()
    db.session.add(UserOrgao(user_id=viewer.id, orgao_id=area.id, papel="gestor"))
    db.session.add(
        ProjectCollection(
            owner_user_id=viewer.id,
            nome="Favoritos",
            tipo="favoritos",
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )
    )
    for index in range(project_count):
        _seed_project(index, area, viewer)
    _seed_shared_collections(min(project_count, 30), viewer)
    db.session.commit()
    return viewer.id


def _seed_project(index: int, area: OrgaoUnidade, viewer: User) -> None:
    title = ("Água", "água", "Zeta", "Alpha")[index % 4]
    project = Project(
        titulo=f"{title} {index:04}",
        orgao_id=area.id,
        prioridade=("alta", "media")[index % 2],
    )
    db.session.add(project)
    db.session.flush()
    offsets = (-8 - index % 13, 0, 7, 14, 21, 30, None, -2)
    for order, offset in enumerate(offsets):
        end = REFERENCE_DAY + timedelta(days=offset) if offset is not None else None
        stage = Etapa(
            project_id=project.id,
            descricao=f"Etapa medição {index}-{order}",
            data_inicio=REFERENCE_DAY - timedelta(days=20) if order % 2 else None,
            data_fim=end,
            iniciada=order % 3 == 0,
            done=order == 7,
            ordem=order,
            entry_type="manual",
            comentarios="Contexto sintético " * 10,
        )
        stage.responsaveis = [EtapaResponsavel(area_id=area.id, label="PERF", ordem=0)]
        db.session.add(stage)
        db.session.flush()
        if order < 2:
            _seed_task(project, stage, viewer, order)


def _seed_task(project: Project, stage: Etapa, viewer: User, order: int) -> None:
    task = Task(
        project_id=project.id,
        etapa_id=stage.id,
        descricao=f"Tarefa {project.id}-{order}",
        created_by_id=viewer.id,
        created_at=FIXED_TIME,
        ordem=order,
        prioridade="alta",
        status="nao_iniciada" if order == 0 else "finalizada",
    )
    task.assignees = [TaskAssignee(user_id=viewer.id, created_at=FIXED_TIME)]
    db.session.add(task)
    db.session.flush()
    task.comments = [
        TaskComment(
            user_id=viewer.id,
            content="Comentário sintético " * 25,
            created_at=FIXED_TIME,
        )
        for _ in range(8)
    ]
    task.anexos = [
        TaskAnexo(
            filename=f"arquivo-{i}.txt",
            stored_filename=f"fixture-{task.id}-{i}.txt",
            uploaded_by_id=viewer.id,
            created_at=FIXED_TIME,
        )
        for i in range(6)
    ]


def _seed_shared_collections(count: int, viewer: User) -> None:
    for index in range(count):
        owner = User(
            username=f"owner-{index}",
            name=f"Dono sintético {index}",
            orgao="PERF",
            password_hash="!benchmark-disabled",
            is_admin=False,
        )
        db.session.add(owner)
        db.session.flush()
        collection = ProjectCollection(
            owner_user_id=owner.id,
            nome=f"Coleção {index}",
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )
        db.session.add(collection)
        db.session.flush()
        db.session.add(
            ProjectCollectionItem(
                collection_id=collection.id, project_id=index + 1, created_at=FIXED_TIME
            )
        )
        db.session.add(
            ProjectCollectionShare(
                collection_id=collection.id,
                user_id=viewer.id,
                papel="viewer",
                created_by_user_id=owner.id,
                created_at=FIXED_TIME,
            )
        )
