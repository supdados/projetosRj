"""Operações sobre a árvore hierárquica de OrgaoUnidade.

Funções puras (compute_orgao_depth, compute_subtree_height) operam em instâncias
já carregadas. Funções que fazem query (get_orgao_descendants, validate_orgao_move)
exigem contexto de aplicação Flask.
"""

from datetime import datetime

from sqlalchemy.exc import OperationalError, ProgrammingError

from models import OrgaoClosure, OrgaoTipo, OrgaoUnidade, db
from models.orgao import DEFAULT_ORGAO_TIPOS, MAX_DEPTH, TIPO_RANK, slugify_orgao_tipo


def ensure_default_orgao_tipos():
    """Garante os tipos-padrão usados por bancos legados e testes."""
    existing = {
        row.nome: row
        for row in OrgaoTipo.query.filter(
            OrgaoTipo.nome.in_([item["nome"] for item in DEFAULT_ORGAO_TIPOS])
        ).all()
    }
    changed = False
    for item in DEFAULT_ORGAO_TIPOS:
        tipo = existing.get(item["nome"])
        if tipo is None:
            tipo = OrgaoTipo(
                nome=item["nome"],
                slug=slugify_orgao_tipo(item["nome"]),
                nivel=item["nivel"],
                ativo=True,
                is_system=True,
                permite_raiz=item["permite_raiz"],
            )
            db.session.add(tipo)
            changed = True
            continue
        if not tipo.slug:
            tipo.slug = slugify_orgao_tipo(tipo.nome)
            changed = True
        if not tipo.is_system:
            tipo.is_system = True
            changed = True
    if changed:
        db.session.flush()


def get_orgao_tipo_options(*, include_inactive=False):
    query = OrgaoTipo.query
    if not include_inactive:
        query = query.filter(OrgaoTipo.ativo.is_(True))
    return query.order_by(OrgaoTipo.nivel, OrgaoTipo.nome).all()


def get_tipo_rank_map():
    rows = get_orgao_tipo_options(include_inactive=True)
    if not rows:
        return dict(TIPO_RANK)
    return {row.nome: row.nivel for row in rows}


def find_orgao_tipo(value):
    if value in (None, ""):
        return None
    try:
        tipo_id = int(value)
    except (TypeError, ValueError):
        tipo_id = None
    try:
        if tipo_id is not None:
            tipo = db.session.get(OrgaoTipo, tipo_id)
            if tipo is not None:
                return tipo
        name = str(value).strip()
        slug = slugify_orgao_tipo(name)
        return OrgaoTipo.query.filter(
            (OrgaoTipo.nome == name) | (OrgaoTipo.slug == slug)
        ).first()
    except RuntimeError:
        return None


def resolve_orgao_tipo(orgao):
    if orgao is None:
        return None
    if getattr(orgao, "tipo_ref", None) is not None:
        return orgao.tipo_ref
    return find_orgao_tipo(getattr(orgao, "tipo_id", None) or getattr(orgao, "tipo", None))


def is_valid_parent_tipo(parent_tipo: str, child_tipo: str) -> bool:
    """Pai precisa ter rank ESTRITAMENTE menor que o filho."""
    parent = find_orgao_tipo(parent_tipo)
    child = find_orgao_tipo(child_tipo)
    parent_rank = parent.nivel if parent else TIPO_RANK.get(parent_tipo)
    child_rank = child.nivel if child else TIPO_RANK.get(child_tipo)
    if parent_rank is None or child_rank is None:
        return True
    return parent_rank < child_rank


def normalize_orgao_form(
    form, *, is_root: bool = False
) -> tuple[dict | None, str | None]:
    """Valida e normaliza dados do formulário de órgão.

    Retorna ``(dados_dict, None)`` em sucesso ou ``(None, mensagem_de_erro)``.
    Exemplo: ``data, err = normalize_orgao_form(request.form)``
    """
    nome = (form.get("nome") or "").strip()
    sigla = (form.get("sigla") or "").strip().upper()
    # tipo_id chega como int via JSON da SPA; nao aplicar .strip() prematuro
    # (find_orgao_tipo ja coage int/str). Fix bug AttributeError 500 orgao_tree.py:113.
    tipo_raw = form.get("tipo_id") or form.get("tipo") or ""
    pai_id_raw = form.get("pai_id")
    ordem_raw = form.get("ordem")
    ativo_raw = form.get("ativo")
    codigo_externo = (form.get("codigo_externo") or "").strip()
    data_inicio_raw = (form.get("data_inicio_vigencia") or "").strip()
    data_fim_raw = (form.get("data_fim_vigencia") or "").strip()

    if not nome:
        return None, "O nome do órgão é obrigatório."
    if len(nome) > 255:
        return None, "O nome do órgão deve ter no máximo 255 caracteres."
    if not sigla:
        return None, "A sigla do órgão é obrigatória."
    if len(sigla) > 50:
        return None, "A sigla deve ter no máximo 50 caracteres."
    tipo_obj = find_orgao_tipo(tipo_raw)
    if tipo_obj is None:
        return None, "Tipo de órgão inválido."
    if not tipo_obj.ativo:
        return None, "Tipo de órgão inativo."
    if not is_root and tipo_obj.permite_raiz:
        return None, f'O tipo "{tipo_obj.nome}" é reservado para órgão raiz.'
    if is_root and not tipo_obj.permite_raiz:
        return None, "O órgão raiz exige um tipo permitido para raiz."

    if is_root:
        pai_id = None
    else:
        if pai_id_raw in (None, "", "None"):
            return None, "O órgão pai é obrigatório."
        try:
            pai_id = int(pai_id_raw)
        except (TypeError, ValueError):
            return None, "Órgão pai inválido."
        pai = db.session.get(OrgaoUnidade, pai_id)
        if pai is None:
            return None, "Órgão pai não encontrado."
        pai_tipo = resolve_orgao_tipo(pai)
        pai_tipo_nome = pai_tipo.nome if pai_tipo else pai.tipo
        if not is_valid_parent_tipo(pai_tipo_nome, tipo_obj.nome):
            return None, f'Um órgão do tipo "{pai_tipo_nome}" não pode ser pai de "{tipo_obj.nome}".'

    try:
        ordem = int(ordem_raw) if ordem_raw not in (None, "") else 0
    except (TypeError, ValueError):
        ordem = 0

    ativo = True
    if ativo_raw is not None:
        ativo_str = str(ativo_raw).strip().lower()
        ativo = ativo_str in ("1", "true", "on", "yes", "sim")

    def parse_date(raw, field_label):
        if not raw:
            return None, None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date(), None
        except ValueError:
            return None, f"{field_label} inválida."

    data_inicio, date_error = parse_date(data_inicio_raw, "Data de início de vigência")
    if date_error:
        return None, date_error
    data_fim, date_error = parse_date(data_fim_raw, "Data de fim de vigência")
    if date_error:
        return None, date_error
    if data_inicio and data_fim and data_fim < data_inicio:
        return None, "Data de fim de vigência deve ser posterior ao início."

    return {
        "nome": nome,
        "sigla": sigla,
        "tipo": tipo_obj.nome,
        "tipo_id": tipo_obj.id,
        "pai_id": pai_id,
        "ordem": ordem,
        "ativo": ativo,
        "codigo_externo": codigo_externo or None,
        "data_inicio_vigencia": data_inicio,
        "data_fim_vigencia": data_fim,
    }, None


def compute_orgao_depth(orgao) -> int:
    """Profundidade do nó na árvore (raiz = 1)."""
    if orgao is None:
        return 0
    depth = 1
    seen = set()
    current = orgao.pai
    while current is not None and current.id not in seen:
        seen.add(current.id)
        depth += 1
        current = current.pai
    return depth


def compute_subtree_height(orgao) -> int:
    """Altura da subárvore: 1 para folha, +1 a cada nível abaixo."""
    if orgao is None:
        return 0
    return 1 + max((compute_subtree_height(child) for child in orgao.filhos), default=0)


def get_orgao_descendants(orgao_id: int) -> list[int]:
    """IDs de todos os descendentes (BFS, sem incluir o próprio orgao_id)."""
    try:
        rows = (
            db.session.query(OrgaoClosure.descendant_id)
            .filter(OrgaoClosure.ancestor_id == orgao_id, OrgaoClosure.depth > 0)
            .order_by(OrgaoClosure.depth, OrgaoClosure.descendant_id)
            .all()
        )
        if rows:
            return [row_id for (row_id,) in rows]
    except (OperationalError, ProgrammingError):
        db.session.rollback()

    descendants: list[int] = []
    frontier = [orgao_id]
    seen = {orgao_id}
    while frontier:
        rows = (
            db.session.query(OrgaoUnidade.id)
            .filter(OrgaoUnidade.pai_id.in_(frontier))
            .all()
        )
        frontier = []
        for (row_id,) in rows:
            if row_id in seen:
                continue
            seen.add(row_id)
            descendants.append(row_id)
            frontier.append(row_id)
    return descendants


def get_orgao_ancestors(orgao_id: int) -> list[int]:
    """IDs de todos os ancestrais (do pai até a raiz, sem incluir o próprio orgao_id)."""
    try:
        rows = (
            db.session.query(OrgaoClosure.ancestor_id)
            .filter(OrgaoClosure.descendant_id == orgao_id, OrgaoClosure.depth > 0)
            .order_by(OrgaoClosure.depth.desc(), OrgaoClosure.ancestor_id)
            .all()
        )
        if rows:
            return [row_id for (row_id,) in rows]
    except (OperationalError, ProgrammingError):
        db.session.rollback()

    ancestors: list[int] = []
    orgao = db.session.get(OrgaoUnidade, orgao_id)
    if orgao is None:
        return ancestors
    seen = {orgao_id}
    current = orgao.pai
    while current is not None and current.id not in seen:
        seen.add(current.id)
        ancestors.append(current.id)
        current = current.pai
    return ancestors


def would_create_cycle(orgao_id: int, new_pai_id: int | None) -> bool:
    if new_pai_id is None:
        return False
    if new_pai_id == orgao_id:
        return True
    return new_pai_id in get_orgao_descendants(orgao_id)


def validate_orgao_move(
    orgao, new_pai_id: int | None, *, child_tipo: str | None = None
) -> str | None:
    """Valida se mover ``orgao`` para ``new_pai_id`` é permitido.

    Retorna mensagem de erro ou ``None`` se a operação é válida.
    """
    if orgao is None:
        return "Órgão não encontrado."

    child_tipo_obj = find_orgao_tipo(child_tipo) if child_tipo else resolve_orgao_tipo(orgao)
    effective_child_tipo = (
        child_tipo_obj.nome if child_tipo_obj else child_tipo or getattr(orgao, "tipo", None)
    )

    if new_pai_id is None:
        if not child_tipo_obj or not child_tipo_obj.permite_raiz:
            return "Apenas tipos permitidos para raiz podem ficar sem pai."
        return None

    if would_create_cycle(orgao.id, new_pai_id):
        return "Não é possível mover um órgão para dentro de si mesmo."

    new_pai = db.session.get(OrgaoUnidade, new_pai_id)
    if new_pai is None:
        return "Órgão pai não encontrado."

    new_pai_tipo = resolve_orgao_tipo(new_pai)
    new_pai_tipo_nome = new_pai_tipo.nome if new_pai_tipo else new_pai.tipo
    if not is_valid_parent_tipo(new_pai_tipo_nome, effective_child_tipo):
        return f'Um órgão do tipo "{new_pai_tipo_nome}" não pode ser pai de "{effective_child_tipo}".'

    if compute_orgao_depth(new_pai) + compute_subtree_height(orgao) > MAX_DEPTH:
        return f"Profundidade máxima de {MAX_DEPTH} níveis excedida."

    return None


def rebuild_orgao_closure():
    """Reconstrói a closure table a partir de `pai_id`."""
    OrgaoClosure.query.delete()
    nodes = OrgaoUnidade.query.order_by(OrgaoUnidade.id).all()
    by_id = {node.id: node for node in nodes}
    for node in nodes:
        db.session.add(
            OrgaoClosure(ancestor_id=node.id, descendant_id=node.id, depth=0)
        )
        depth = 1
        current = by_id.get(node.pai_id)
        seen = {node.id}
        while current is not None and current.id not in seen:
            seen.add(current.id)
            db.session.add(
                OrgaoClosure(
                    ancestor_id=current.id,
                    descendant_id=node.id,
                    depth=depth,
                )
            )
            depth += 1
            current = by_id.get(current.pai_id)
    db.session.flush()


def backfill_orgao_tipo_ids():
    """Vincula órgãos legados aos tipos cadastrados quando `tipo_id` está vazio."""
    tipos = {tipo.nome: tipo for tipo in OrgaoTipo.query.all()}
    changed = False
    for orgao in OrgaoUnidade.query.filter(OrgaoUnidade.tipo_id.is_(None)).all():
        tipo = tipos.get(orgao.tipo)
        if tipo is None:
            tipo = OrgaoTipo(
                nome=orgao.tipo,
                slug=slugify_orgao_tipo(orgao.tipo),
                nivel=TIPO_RANK.get(orgao.tipo, MAX_DEPTH),
                ativo=True,
                is_system=False,
                permite_raiz=orgao.pai_id is None,
            )
            db.session.add(tipo)
            db.session.flush()
            tipos[tipo.nome] = tipo
        orgao.tipo_id = tipo.id
        orgao.tipo = tipo.nome
        changed = True
    if changed:
        db.session.flush()
