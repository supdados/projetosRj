"""Limpeza de arquivos de anexos após persistir a remoção dos seus registros."""

from collections.abc import Iterable
from logging import Logger
from pathlib import Path


def remove_task_attachment_files(
    stored_filenames: Iterable[str], *, upload_folder: str | Path, logger: Logger
) -> list[str]:
    """Remove arquivos após commit; devolve e registra os nomes que exigem retry.

    Ex.: ``remove_task_attachment_files(names, upload_folder=folder, logger=log)``.
    Arquivo já ausente é sucesso. O caller nunca chama antes de um commit válido.
    """
    failed: list[str] = []
    for filename in dict.fromkeys(stored_filenames):
        try:
            if (
                not filename
                or Path(filename).name != filename
                or filename in {".", ".."}
            ):
                raise ValueError(
                    f"Nome de anexo inválido: {filename!r}; esperado nome simples sem diretório."
                )
            (Path(upload_folder) / filename).unlink(missing_ok=True)
        except (OSError, ValueError):
            failed.append(filename)
            logger.exception(
                "Falha ao remover arquivo de anexo",
                extra={
                    "event": "task_attachment_cleanup_failed",
                    "stored_filename": filename,
                    "upload_folder": str(upload_folder),
                },
            )
    return failed
