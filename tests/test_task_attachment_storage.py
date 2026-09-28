import logging
from pathlib import Path

from services.task_attachment_storage import remove_task_attachment_files


class UnremovableAttachmentPath(Path):
    def unlink(self, *, missing_ok: bool = False) -> None:
        raise PermissionError("Falha de remoção simulada")


def test_missing_file_and_duplicate_names_are_idempotent(tmp_path) -> None:
    attachment = tmp_path / "anexo.txt"
    attachment.write_text("conteúdo")
    assert (
        remove_task_attachment_files(
            ["anexo.txt", "ausente.txt", "anexo.txt"],
            upload_folder=tmp_path,
            logger=logging.getLogger(__name__),
        )
        == []
    )
    assert not attachment.exists()


def test_failed_removal_is_recorded_for_retry(tmp_path, monkeypatch, caplog) -> None:
    attachment = tmp_path / "anexo.txt"
    attachment.write_text("conteúdo")
    with monkeypatch.context() as patch:
        patch.setattr(
            "services.task_attachment_storage.Path", UnremovableAttachmentPath
        )
        assert remove_task_attachment_files(
            ["anexo.txt"], upload_folder=tmp_path, logger=logging.getLogger(__name__)
        ) == ["anexo.txt"]
    assert attachment.exists()
    record = caplog.records[-1]
    assert record.event == "task_attachment_cleanup_failed"
    assert record.stored_filename == "anexo.txt"
    assert record.exc_info is not None
    assert (
        remove_task_attachment_files(
            ["anexo.txt"], upload_folder=tmp_path, logger=logging.getLogger(__name__)
        )
        == []
    )


def test_cleanup_rejects_paths_outside_upload_folder(tmp_path, caplog) -> None:
    folder = tmp_path / "uploads"
    folder.mkdir()
    outside = tmp_path / "preservar.txt"
    outside.write_text("preservar")
    assert remove_task_attachment_files(
        ["../preservar.txt"], upload_folder=folder, logger=logging.getLogger(__name__)
    ) == ["../preservar.txt"]
    assert outside.exists()
