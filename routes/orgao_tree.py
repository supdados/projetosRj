"""Operações sobre a árvore hierárquica de OrgaoUnidade.

Funções puras (compute_orgao_depth, compute_subtree_height) operam em instâncias
já carregadas. Funções que fazem query (get_orgao_descendants, validate_orgao_move)
exigem contexto de aplicação Flask.
"""

from models import OrgaoUnidade, db
from models.orgao import ALLOWED_TIPOS, MAX_DEPTH, TIPO_RANK


def is_valid_parent_tipo(parent_tipo: str, child_tipo: str) -> bool:
    """Pai precisa ter rank ESTRITAMENTE menor que o filho."""
    parent_rank = TIPO_RANK.get(parent_tipo)
    child_rank = TIPO_RANK.get(child_tipo)
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
    tipo = (form.get("tipo") or "").strip()
    pai_id_raw = form.get("pai_id")
    ordem_raw = form.get("ordem")
    ativo_raw = form.get("ativo")

    if not nome:
        return None, "O nome do órgão é obrigatório."
    if len(nome) > 255:
        return None, "O nome do órgão deve ter no máximo 255 caracteres."
    if not sigla:
        return None, "A sigla do órgão é obrigatória."
    if len(sigla) > 50:
        return None, "A sigla deve ter no máximo 50 caracteres."
    if tipo not in ALLOWED_TIPOS:
        return None, "Tipo de órgão inválido."
    if not is_root and tipo == "Estado":
        return None, 'O tipo "Estado" é reservado para o órgão raiz.'
    if is_root and tipo != "Estado":
        return None, 'O órgão raiz deve ter o tipo "Estado".'

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
        if not is_valid_parent_tipo(pai.tipo, tipo):
            return None, f'Um órgão do tipo "{pai.tipo}" não pode ser pai de "{tipo}".'

    try:
        ordem = int(ordem_raw) if ordem_raw not in (None, "") else 0
    except (TypeError, ValueError):
        ordem = 0

    ativo = True
    if ativo_raw is not None:
        ativo_str = str(ativo_raw).strip().lower()
        ativo = ativo_str in ("1", "true", "on", "yes", "sim")

    return {
        "nome": nome,
        "sigla": sigla,
        "tipo": tipo,
        "pai_id": pai_id,
        "ordem": ordem,
        "ativo": ativo,
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

    effective_child_tipo = child_tipo or getattr(orgao, "tipo", None)

    if new_pai_id is None:
        if effective_child_tipo != "Estado":
            return "Apenas o órgão raiz (Estado) pode ficar sem pai."
        return None

    if would_create_cycle(orgao.id, new_pai_id):
        return "Não é possível mover um órgão para dentro de si mesmo."

    new_pai = db.session.get(OrgaoUnidade, new_pai_id)
    if new_pai is None:
        return "Órgão pai não encontrado."

    if not is_valid_parent_tipo(new_pai.tipo, effective_child_tipo):
        return f'Um órgão do tipo "{new_pai.tipo}" não pode ser pai de "{effective_child_tipo}".'

    if compute_orgao_depth(new_pai) + compute_subtree_height(orgao) > MAX_DEPTH:
        return f"Profundidade máxima de {MAX_DEPTH} níveis excedida."

    return None
