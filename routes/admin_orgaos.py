from models import OrgaoTipo, OrgaoUnidade, db
from models.orgao import slugify_orgao_tipo

from .orgao_tree import (
    backfill_orgao_tipo_ids,
    ensure_default_orgao_tipos,
    get_orgao_descendants,
)


def _candidate_pais(orgao=None):
    """Retorna órgãos que podem ser pai do `orgao` (exclui ele e descendentes)."""
    excluded = set()
    if orgao is not None and orgao.id is not None:
        excluded.add(orgao.id)
        excluded.update(get_orgao_descendants(orgao.id))
    todos = OrgaoUnidade.query.order_by(
        OrgaoUnidade.pai_id.is_(None).desc(), OrgaoUnidade.sigla
    ).all()
    return [o for o in todos if o.id not in excluded]


def _prepare_orgao_catalogs():
    ensure_default_orgao_tipos()
    backfill_orgao_tipo_ids()
    db.session.flush()


def _normalize_tipo_form(form, tipo=None):
    nome = (form.get("nome") or "").strip()
    slug = slugify_orgao_tipo(form.get("slug") or nome)
    descricao = (form.get("descricao") or "").strip()
    try:
        nivel = int(form.get("nivel") or 0)
    except (TypeError, ValueError):
        return None, "Nível inválido."
    ativo = form.get("ativo") is not None
    permite_raiz = form.get("permite_raiz") is not None
    if not nome:
        return None, "O nome do tipo é obrigatório."
    if not slug:
        return None, "O identificador do tipo é obrigatório."
    if nivel < 0:
        return None, "O nível deve ser maior ou igual a zero."

    query = OrgaoTipo.query.filter((OrgaoTipo.nome == nome) | (OrgaoTipo.slug == slug))
    if tipo is not None:
        query = query.filter(OrgaoTipo.id != tipo.id)
    if query.first() is not None:
        return None, "Já existe um tipo com esse nome ou identificador."

    return {
        "nome": nome,
        "slug": slug,
        "nivel": nivel,
        "descricao": descricao or None,
        "ativo": ativo,
        "permite_raiz": permite_raiz,
    }, None


def _invalid_orgao_type_level_changes(tipo, new_nivel, new_permite_raiz):
    affected = []
    for orgao in OrgaoUnidade.query.filter_by(tipo_id=tipo.id).all():
        if orgao.pai_id is None:
            if not new_permite_raiz:
                affected.append(orgao)
            continue
        pai_tipo = orgao.pai.tipo_ref if orgao.pai else None
        if pai_tipo is not None and pai_tipo.nivel >= new_nivel:
            affected.append(orgao)
        for filho in orgao.filhos:
            filho_tipo = filho.tipo_ref
            if filho_tipo is not None and new_nivel >= filho_tipo.nivel:
                affected.append(filho)
    return affected
