import os
import re

VALID_PRIORIDADES = {"baixa", "media", "alta", "urgente"}
VALID_TIPOS = {"bug", "melhoria", "duvida", "outros"}
LEGACY_TIPOS = {"implementacao"}
VALID_STATUSES = {
    "nao_iniciada",
    "em_andamento",
    "para_validacao",
    "para_ajustes",
    "finalizada",
}
ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "txt",
}

# Assinaturas (magic bytes) nos primeiros bytes do arquivo. Office moderno (docx/xlsx)
# é container ZIP (PK\x03\x04); Office legado (doc/xls) usa OLE2 (D0 CF 11 E0).
# TXT não tem assinatura determinística — validado por ausência de bytes NUL.
_MAGIC_SIGNATURES = {
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "gif": [b"GIF87a", b"GIF89a"],
    "webp": [b"RIFF"],  # complementar: verifica 'WEBP' no offset 8
    "pdf": [b"%PDF-"],
    "docx": [b"PK\x03\x04"],
    "xlsx": [b"PK\x03\x04"],
    "doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "xls": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
}
TASK_PRIORIDADE_ORDER = ("baixa", "media", "alta", "urgente")
TASK_TIPO_ORDER = ("bug", "melhoria", "duvida", "outros", "implementacao")
TASK_STATUS_ORDER = (
    "nao_iniciada",
    "em_andamento",
    "para_validacao",
    "para_ajustes",
    "finalizada",
)

# Pesos de ordenação reusados pelo hub (lista) e pelo board (kanban). Prioridade
# é invertida (urgente primeiro); valor ausente/desconhecido recebe o maior peso
# (vai por último). Fonte única para evitar duplicar o mapeamento entre
# routes/tasks/hub.py, routes/api/board.py e routes/api/projects_write.py.
_PRIORITY_SORT_RANK = {
    prioridade: rank for rank, prioridade in enumerate(reversed(TASK_PRIORIDADE_ORDER))
}


def task_priority_sort_rank(prioridade) -> int:
    """Peso de ordenação por prioridade: 0=urgente, 1=alta, 2=media, 3=baixa.

    Prioridade ausente/desconhecida recebe o maior peso (vai por último).
    Exemplo: ``task_priority_sort_rank("urgente")`` → 0; ``task_priority_sort_rank(None)`` → 4.
    """
    return _PRIORITY_SORT_RANK.get(prioridade, len(TASK_PRIORIDADE_ORDER))


def _get_upload_folder():
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    folder = os.path.join(basedir, "instance", "uploads", "tasks")
    os.makedirs(folder, exist_ok=True)
    return folder


def _allowed_attachment(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _extension_of(filename):
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def _file_content_matches_extension(file_storage, extension):
    """Lê os primeiros 16 bytes e valida contra a assinatura esperada da extensão.

    Retorna True para `txt` se o conteúdo não tiver NUL bytes (heurística simples
    para evitar que binários sejam enviados com extensão .txt).
    """
    extension = (extension or "").lower()
    try:
        head = file_storage.stream.read(16)
    except Exception:
        return False
    finally:
        try:
            file_storage.stream.seek(0)
        except Exception:
            pass

    if not head:
        return False

    if extension == "txt":
        return b"\x00" not in head

    signatures = _MAGIC_SIGNATURES.get(extension)
    if not signatures:
        return False

    if extension == "webp":
        return head.startswith(b"RIFF") and len(head) >= 12 and head[8:12] == b"WEBP"

    return any(head.startswith(sig) for sig in signatures)


def _task_status_label(status):
    labels = {
        "nao_iniciada": "Não iniciada",
        "em_andamento": "Em andamento",
        "para_validacao": "Para validação",
        "para_ajustes": "Para ajustes",
        "finalizada": "Finalizada",
    }
    return labels.get(status, status or "")


def _task_prioridade_label(prioridade):
    labels = {
        "baixa": "Baixa",
        "media": "Média",
        "alta": "Alta",
        "urgente": "Urgente",
    }
    return labels.get(prioridade, prioridade or "")


def _task_tipo_label(tipo):
    labels = {
        "bug": "Bug",
        "melhoria": "Melhoria",
        "duvida": "Dúvida",
        "outros": "Outros",
        "implementacao": "Implementação (legado)",
    }
    return labels.get(tipo, tipo or "")


def _preview_text(value, max_length=90):
    text_value = " ".join((value or "").split())
    if len(text_value) <= max_length:
        return text_value
    return text_value[: max_length - 3].rstrip() + "..."


def _normalize_person_name(name):
    return " ".join((name or "").strip().split())


def _split_responsavel_names(raw_value):
    raw_value = (raw_value or "").replace("\r", "\n").strip()
    if not raw_value:
        return []

    names = []
    seen = set()
    for part in re.split(r"[,\n;]+", raw_value):
        normalized = _normalize_person_name(part.lstrip("@"))
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(normalized)
    return names


def _normalize_responsavel_value(raw_value):
    return ", ".join(_split_responsavel_names(raw_value))
