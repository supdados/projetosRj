"""Backfill: converte ``Task.responsavel`` (texto livre legado) em ``TaskAssignee``.

Contexto (2026-06-10): a SPA exibe responsáveis pela relação ``task_assignee``
(avatares no kanban/lista e picker do drawer), mas tarefas antigas só têm o
texto livre — o kanban mostrava o nome legado enquanto o drawer aparecia vazio.
Este passo converte cada nome do texto em uma linha de ``task_assignee`` quando
há exatamente UM usuário ativo com aquele nome, e REMOVE do texto os nomes
convertidos. Remover é o que torna o passo idempotente: rodar de novo não
ressuscita atribuições que o usuário removeu depois pela UI. Nomes sem correspondência (ou ambíguos) permanecem no
texto legado, sem perda de informação.
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import Task, TaskAssignee, User, db


def _normalized_name_key(name: str) -> str:
    """Chave de comparação de nome: espaços colapsados + casefold.

    Exemplo: "  Jose   Hudson " -> "jose hudson".
    """
    return " ".join((name or "").strip().split()).casefold()


def _active_users_by_name_key() -> dict[str, int | None]:
    """Mapa nome normalizado -> user_id (ou ``None`` quando o nome é ambíguo).

    Considera apenas usuários ativos (sem soft-delete). Indexa pelo nome de
    exibição (``User.name``, fallback ``username`` — mesmo critério de
    ``routes.tasks.queries.serialize_assignee``) E pelo ``username``: o texto
    legado guardou tanto nomes completos ("Jose Hudson") quanto apelidos de
    login ("Lucas" para o username ``lucas``). Colisão de chave entre usuários
    diferentes marca a chave como ambígua (``None``) e o nome fica no texto.
    """
    users_by_key: dict[str, int | None] = {}
    active_users = User.query.filter(User.deleted_at.is_(None)).all()
    for user in active_users:
        keys = {
            _normalized_name_key(user.name or user.username or ""),
            _normalized_name_key(user.username or ""),
        }
        for key in keys:
            if not key:
                continue
            if users_by_key.get(key, user.id) != user.id:
                users_by_key[key] = None
            else:
                users_by_key[key] = user.id
    return users_by_key


def _convert_legacy_names(
    task: Task, users_by_key: dict[str, int | None]
) -> tuple[list[int], list[str]]:
    """Separa os nomes do texto legado em (user_ids casados, nomes restantes).

    Ignora ids já presentes em ``task.assignees`` (PK composta) e nomes
    ambíguos/sem correspondência — esses últimos voltam para o texto.
    """
    from routes.tasks.constants import _split_responsavel_names

    existing_ids = {assignee.user_id for assignee in task.assignees}
    matched_ids: list[int] = []
    unmatched_names: list[str] = []
    for name in _split_responsavel_names(task.responsavel):
        user_id = users_by_key.get(_normalized_name_key(name))
        if user_id is None:
            unmatched_names.append(name)
        elif user_id not in existing_ids:
            existing_ids.add(user_id)
            matched_ids.append(user_id)
    return matched_ids, unmatched_names


def _emit(message: str, emit_output: bool = True) -> None:
    if emit_output:
        print(message)


def backfill_task_assignees(emit_output: bool = True, *, apply: bool = True) -> dict:
    """Passo de migração: texto legado -> ``task_assignee`` (idempotente).

    Returns:
        ``{"success": bool, "converted_tasks": int, "assignees_created": int}``.
    """
    _emit(
        "\n-- Backfill de responsáveis (texto legado -> task_assignee)...", emit_output
    )
    try:
        users_by_key = _active_users_by_name_key()
        legacy_tasks = Task.query.filter(
            Task.responsavel.isnot(None), db.func.trim(Task.responsavel) != ""
        ).all()

        converted_tasks = 0
        assignees_created = 0
        for task in legacy_tasks:
            matched_ids, unmatched_names = _convert_legacy_names(task, users_by_key)
            if not matched_ids:
                continue
            for user_id in matched_ids:
                task.assignees.append(TaskAssignee(user_id=user_id))
            task.responsavel = ", ".join(unmatched_names) or None
            converted_tasks += 1
            assignees_created += len(matched_ids)

        if apply:
            db.session.commit()
        else:
            db.session.rollback()
        if converted_tasks:
            _emit(
                f"   ✓ {assignees_created} responsáveis criados em {converted_tasks} tarefas.",
                emit_output,
            )
        else:
            _emit("   ✓ Nenhum texto legado pendente de conversão.", emit_output)
        return {
            "success": True,
            "converted_tasks": converted_tasks,
            "assignees_created": assignees_created,
        }
    except Exception as exc:
        db.session.rollback()
        _emit(f"   ✗ ERRO no backfill de responsáveis: {exc}", emit_output)
        return {
            "success": False,
            "error": str(exc),
            "converted_tasks": 0,
            "assignees_created": 0,
        }


def main() -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="Converte Task.responsavel legado em linhas task_assignee."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Grava as alterações (default é dry-run, que só relata contagens).",
    )
    args = parser.parse_args()
    # Backfill de dados puro: importar o app não deve rodar verificação de schema.
    os.environ.setdefault("SKIP_STARTUP_DB_INIT", "true")
    from app import app

    with app.app_context():
        print(f"Banco: {app.config['SQLALCHEMY_DATABASE_URI']}")
        result = backfill_task_assignees(apply=args.apply)
        if not args.apply:
            print("\nDry-run: nada gravado. Use --apply para gravar.")
        return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
