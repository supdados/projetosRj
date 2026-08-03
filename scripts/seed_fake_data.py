#!/usr/bin/env python3
"""
Gera dados fake para visualizacao e testes funcionais.

Padrao:
- reseta e recria o banco atual;
- cria 100 projetos;
- 5 etapas por projeto;
- 2 tarefas por projeto;
- 4 itens por tarefa;
- 1 comentario por item.
"""

import argparse
import datetime
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from catalogs.abep import ABEP_INDICADORES_OPTIONS
from app import create_app
from models import (
    Etapa,
    IndicadorProjeto,
    OrgaoUnidade,
    Project,
    ProjectHistory,
    ProjectSeiProcess,
    Task,
    TaskItem,
    TaskItemComment,
    User,
    UserOrgao,
    db,
)
from catalogs.objectives import GOAL_CATALOG, sync_goal_catalog_to_db
from scripts.migrations.run_migrations import elect_initial_super_admin

SEED_ORGAO_SIGLAS = [
    "Auditoria",
    "CHEGAB",
    "SUPDADOS",
    "SUBDGD",
    "SUPEST",
    "SUPIM",
    "SUPPAE",
    "PRODERJ",
    "ASSESP",
    "ECENTRAL",
    "SUBEDD",
    "VPD",
    "VPE",
    "VPT",
]


def _ensure_seed_orgaos():
    setd = OrgaoUnidade.query.filter_by(sigla="SETD").first()
    if setd is None:
        setd = OrgaoUnidade(
            sigla="SETD",
            nome="SETD",
            tipo="Secretaria",
            pai_id=None,
            ordem=0,
            ativo=True,
        )
        db.session.add(setd)
        db.session.flush()
    orgaos = []
    for idx, sigla in enumerate(SEED_ORGAO_SIGLAS):
        existing = OrgaoUnidade.query.filter_by(sigla=sigla).first()
        if existing is None:
            existing = OrgaoUnidade(
                sigla=sigla,
                nome=sigla,
                tipo="Subsecretaria",
                pai_id=setd.id,
                ordem=idx,
                ativo=True,
            )
            db.session.add(existing)
            db.session.flush()
        orgaos.append(existing)
    return orgaos


PRIORITIES = ["urgente", "alta", "media", "baixa"]
PROJECT_STATUSES = ["Vigente", "Vigente", "Vigente", "Finalizado", "Suspenso"]
DELIVERY_TYPES = [
    "Sistema",
    "Painel",
    "Norma",
    "Instrumento de parceria",
    "Fluxo Processual",
    "Outro",
]
SPECIAL_PROJECTS = [None, None, "ABEP", "TCE"]
TASK_ITEM_STATUSES = [
    "nao_iniciada",
    "em_andamento",
    "para_validacao",
    "para_ajustes",
    "finalizada",
]


def _sanitize_username_suffix(value):
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _choose_goal_ids(index):
    objetivo = GOAL_CATALOG[index % len(GOAL_CATALOG)]
    resultados = objetivo["resultados"]
    resultado = resultados[index % len(resultados)]
    indicador_ids = [item["id"] for item in resultado["indicadores"][:2]]
    return objetivo["id"], resultado["id"], indicador_ids


def _create_seed_users(orgaos):
    admin = User(
        username="admin_seed",
        name="Administrador Seed",
        orgao="SEED",
        is_admin=True,
    )
    admin.set_password("seed123")
    db.session.add(admin)
    db.session.flush()
    # Sem isto a base semeada não tem super admin e ninguém consegue conceder
    # is_admin até um restart rodar a eleição da migração.
    elect_initial_super_admin()
    db.session.add(UserOrgao(user_id=admin.id, orgao_id=orgaos[0].id))

    users_by_sigla = {}
    for index, orgao in enumerate(orgaos, start=1):
        suffix = _sanitize_username_suffix(orgao.sigla) or f"orgao{index:02d}"
        user = User(
            username=f"user_seed_{index:02d}_{suffix}",
            name=f"Responsavel {orgao.sigla}",
            orgao="SEED",
            is_admin=False,
        )
        user.set_password("seed123")
        db.session.add(user)
        db.session.flush()
        db.session.add(UserOrgao(user_id=user.id, orgao_id=orgao.id))
        users_by_sigla[orgao.sigla] = user

    db.session.flush()
    return admin, users_by_sigla


def seed_fake_data(
    app,
    *,
    reset=True,
    projects=100,
    stages_per_project=5,
    tasks_per_project=2,
    items_per_task=4,
    comments_per_item=1,
    orphan_tasks=10,
    rng_seed=42,
):
    random.seed(rng_seed)
    counters = {
        "projects": 0,
        "stages": 0,
        "project_tasks": 0,
        "orphan_tasks": 0,
        "task_items": 0,
        "task_item_comments": 0,
        "project_history": 0,
    }

    with app.app_context():
        if reset:
            db.drop_all()

        db.create_all()
        sync_goal_catalog_to_db(commit=True)

        orgaos = _ensure_seed_orgaos()
        admin, users_by_sigla = _create_seed_users(orgaos)
        base_date = datetime.date(2026, 1, 1)

        for project_index in range(projects):
            orgao = orgaos[project_index % len(orgaos)]
            owner = users_by_sigla[orgao.sigla]
            objetivo_id, resultado_id, indicador_ids = _choose_goal_ids(project_index)
            project_status = PROJECT_STATUSES[project_index % len(PROJECT_STATUSES)]
            priority = PRIORITIES[project_index % len(PRIORITIES)]
            delivery_type = DELIVERY_TYPES[project_index % len(DELIVERY_TYPES)]
            special_project = SPECIAL_PROJECTS[project_index % len(SPECIAL_PROJECTS)]
            abep_indicator = ABEP_INDICADORES_OPTIONS[
                project_index % len(ABEP_INDICADORES_OPTIONS)
            ]["value"]

            project = Project(
                titulo=f"Projeto Fake {project_index + 1:03d}",
                orgao_id=orgao.id,
                orgao=f"Orgao {(project_index % 12) + 1:02d}",
                prioridade=priority,
                status=project_status,
                observacao="Projeto gerado automaticamente para testes.",
                objetivo_id=objetivo_id,
                resultado_esperado_id=resultado_id,
                special_project=special_project,
                short_description=f"Projeto fake {project_index + 1:03d} do orgao {orgao.sigla}.",
                delivery_type=delivery_type,
                abep_indicator=abep_indicator,
                github_link=f"https://github.com/fake-org/projeto-{project_index + 1:03d}",
                documentation_link=f"https://docs.example.com/projeto-{project_index + 1:03d}",
            )
            db.session.add(project)
            db.session.flush()
            counters["projects"] += 1

            # ~1/3 dos projetos com 2-3 números para exercitar o chip "+N".
            sei_count = {2: 2, 5: 3}.get(project_index % 6, 1)
            for sei_index in range(sei_count):
                db.session.add(
                    ProjectSeiProcess(
                        project_id=project.id,
                        numero=(
                            f"SEI-{380000 + project_index:06d}"
                            f"/{sei_index + 1:06d}/2026"
                        ),
                        ordem=sei_index,
                    )
                )

            for indicador_id in indicador_ids:
                db.session.add(
                    IndicadorProjeto(project_id=project.id, indicador_id=indicador_id)
                )

            stage_start = base_date + datetime.timedelta(days=project_index)
            for stage_index in range(stages_per_project):
                duration_days = 2 + (stage_index % 4)
                stage_end = stage_start + datetime.timedelta(days=duration_days - 1)

                if project_status == "Finalizado":
                    iniciada = True
                    done = True
                elif project_status == "Suspenso":
                    iniciada = stage_index < 2
                    done = stage_index == 0
                else:
                    iniciada = stage_index < 3
                    done = stage_index == 0

                db.session.add(
                    Etapa(
                        descricao=f"Etapa {stage_index + 1} do Projeto {project_index + 1:03d}",
                        data_inicio=stage_start,
                        data_fim=stage_end,
                        responsavel=owner.name,
                        iniciada=iniciada,
                        done=done,
                        comentarios=f"Etapa fake {stage_index + 1}",
                        project_id=project.id,
                        ordem=stage_index,
                    )
                )
                counters["stages"] += 1
                stage_start = stage_end + datetime.timedelta(days=1)

            for task_index in range(tasks_per_project):
                task = Task(
                    titulo=f"Tarefa {task_index + 1} do Projeto {project_index + 1:03d}",
                    project_id=project.id,
                    created_by_id=owner.id,
                )
                db.session.add(task)
                db.session.flush()
                counters["project_tasks"] += 1

                for item_index in range(items_per_task):
                    item_status = TASK_ITEM_STATUSES[
                        (task_index + item_index) % len(TASK_ITEM_STATUSES)
                    ]
                    responsavel = owner.name if item_status != "finalizada" else None
                    item = TaskItem(
                        descricao=f"Item {item_index + 1} da tarefa {task_index + 1} do projeto {project_index + 1:03d}",
                        status=item_status,
                        responsavel=responsavel,
                        ordem=item_index + 1,
                        task_id=task.id,
                    )
                    db.session.add(item)
                    db.session.flush()
                    counters["task_items"] += 1

                    for comment_index in range(comments_per_item):
                        author_id = admin.id if comment_index % 2 == 0 else owner.id
                        db.session.add(
                            TaskItemComment(
                                content=(
                                    f"Comentario {comment_index + 1} do item {item_index + 1} "
                                    f"da tarefa {task_index + 1} do projeto {project_index + 1:03d}"
                                ),
                                user_id=author_id,
                                task_item_id=item.id,
                            )
                        )
                        counters["task_item_comments"] += 1

            db.session.add(
                ProjectHistory(
                    project_id=project.id,
                    user_id=owner.id,
                    action_type="seed_create",
                    action_description="Projeto criado automaticamente pelo seed fake.",
                )
            )
            counters["project_history"] += 1

        orgao_users = list(users_by_sigla.values())
        for orphan_index in range(orphan_tasks):
            creator = orgao_users[orphan_index % len(orgao_users)]
            task = Task(
                titulo=f"Tarefa sem projeto {orphan_index + 1:03d}",
                project_id=None,
                created_by_id=creator.id,
            )
            db.session.add(task)
            db.session.flush()
            counters["orphan_tasks"] += 1

            for item_index in range(items_per_task):
                item = TaskItem(
                    descricao=f"Item {item_index + 1} da tarefa sem projeto {orphan_index + 1:03d}",
                    status=TASK_ITEM_STATUSES[item_index % len(TASK_ITEM_STATUSES)],
                    responsavel=creator.name,
                    ordem=item_index + 1,
                    task_id=task.id,
                )
                db.session.add(item)
                db.session.flush()
                counters["task_items"] += 1

                for comment_index in range(comments_per_item):
                    db.session.add(
                        TaskItemComment(
                            content=(
                                f"Comentario {comment_index + 1} do item {item_index + 1} "
                                f"da tarefa sem projeto {orphan_index + 1:03d}"
                            ),
                            user_id=creator.id,
                            task_item_id=item.id,
                        )
                    )
                    counters["task_item_comments"] += 1

        db.session.commit()

        return {
            **counters,
            "users": User.query.count(),
            "projects_total_in_db": Project.query.count(),
            "tasks_total_in_db": Task.query.count(),
            "task_items_total_in_db": TaskItem.query.count(),
            "task_item_comments_total_in_db": TaskItemComment.query.count(),
        }


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Popula o banco com dados fake para testes."
    )
    parser.add_argument("--projects", type=int, default=100)
    parser.add_argument("--stages-per-project", type=int, default=5)
    parser.add_argument("--tasks-per-project", type=int, default=2)
    parser.add_argument("--items-per-task", type=int, default=4)
    parser.add_argument("--comments-per-item", type=int, default=1)
    parser.add_argument("--orphan-tasks", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--no-reset", action="store_true", help="Nao reseta tabelas antes de popular."
    )
    parser.add_argument(
        "--yes", action="store_true", help="Confirma execucao sem prompt."
    )
    return parser.parse_args(argv)


def _validate_args(args):
    numeric_fields = [
        "projects",
        "stages_per_project",
        "tasks_per_project",
        "items_per_task",
        "comments_per_item",
        "orphan_tasks",
    ]
    for field in numeric_fields:
        value = getattr(args, field)
        if value < 0:
            raise ValueError(f'O parametro --{field.replace("_", "-")} deve ser >= 0.')


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    _validate_args(args)

    reset = not args.no_reset
    if reset and not args.yes:
        confirmation = input(
            'Este comando vai resetar e recriar o banco configurado. Digite "YES" para continuar: '
        ).strip()
        if confirmation != "YES":
            print("Operacao cancelada pelo usuario.")
            return 1

    app = create_app({"SKIP_STARTUP_DB_INIT": True})
    summary = seed_fake_data(
        app,
        reset=reset,
        projects=args.projects,
        stages_per_project=args.stages_per_project,
        tasks_per_project=args.tasks_per_project,
        items_per_task=args.items_per_task,
        comments_per_item=args.comments_per_item,
        orphan_tasks=args.orphan_tasks,
        rng_seed=args.seed,
    )

    print("Seed finalizado com sucesso.")
    print(f"Usuarios: {summary['users']}")
    print(f"Projetos: {summary['projects_total_in_db']} (novos: {summary['projects']})")
    print(
        "Tarefas vinculadas a projeto: "
        f"{summary['project_tasks']} | tarefas sem projeto: {summary['orphan_tasks']} | "
        f"total tarefas: {summary['tasks_total_in_db']}"
    )
    print(f"Itens de tarefa (total): {summary['task_items_total_in_db']}")
    print(f"Comentarios de item (total): {summary['task_item_comments_total_in_db']}")
    print(f'Historico de projetos criado: {summary["project_history"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
