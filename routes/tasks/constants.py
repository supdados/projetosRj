import os
import re


VALID_PRIORIDADES = {'baixa', 'media', 'alta', 'urgente'}
VALID_TIPOS = {'bug', 'melhoria', 'duvida', 'outros'}
LEGACY_TIPOS = {'implementacao'}
VALID_STATUSES = {'nao_iniciada', 'em_andamento', 'para_validacao', 'para_ajustes', 'finalizada'}
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip'}
TASK_PRIORIDADE_ORDER = ('baixa', 'media', 'alta', 'urgente')
TASK_TIPO_ORDER = ('bug', 'melhoria', 'duvida', 'outros', 'implementacao')
TASK_STATUS_ORDER = ('nao_iniciada', 'em_andamento', 'para_validacao', 'para_ajustes', 'finalizada')


def _get_upload_folder():
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    folder = os.path.join(basedir, 'instance', 'uploads', 'tasks')
    os.makedirs(folder, exist_ok=True)
    return folder


def _allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _task_status_label(status):
    labels = {
        'nao_iniciada': 'Não iniciada',
        'em_andamento': 'Em andamento',
        'para_validacao': 'Para validação',
        'para_ajustes': 'Para ajustes',
        'finalizada': 'Finalizada',
    }
    return labels.get(status, status or '')


def _task_prioridade_label(prioridade):
    labels = {
        'baixa': 'Baixa',
        'media': 'Média',
        'alta': 'Alta',
        'urgente': 'Urgente',
    }
    return labels.get(prioridade, prioridade or '')


def _task_tipo_label(tipo):
    labels = {
        'bug': 'Bug',
        'melhoria': 'Melhoria',
        'duvida': 'Dúvida',
        'outros': 'Outros',
        'implementacao': 'Implementação (legado)',
    }
    return labels.get(tipo, tipo or '')


def _preview_text(value, max_length=90):
    text_value = ' '.join((value or '').split())
    if len(text_value) <= max_length:
        return text_value
    return text_value[: max_length - 3].rstrip() + '...'


def _normalize_person_name(name):
    return ' '.join((name or '').strip().split())


def _split_responsavel_names(raw_value):
    raw_value = (raw_value or '').replace('\r', '\n').strip()
    if not raw_value:
        return []

    names = []
    seen = set()
    for part in re.split(r'[,\n;]+', raw_value):
        normalized = _normalize_person_name(part.lstrip('@'))
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(normalized)
    return names


def _normalize_responsavel_value(raw_value):
    return ', '.join(_split_responsavel_names(raw_value))
