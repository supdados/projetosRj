from flask import flash, jsonify, redirect, render_template, request, url_for

from models import OrgaoTipo, OrgaoUnidade, db
from models.orgao import MAX_DEPTH, slugify_orgao_tipo

from .blueprint import main_bp
from .decorators import admin_required, login_required
from .orgao_tree import (
    backfill_orgao_tipo_ids,
    compute_orgao_depth,
    get_orgao_descendants,
    get_orgao_tipo_options,
    get_tipo_rank_map,
    ensure_default_orgao_tipos,
    is_valid_parent_tipo,
    normalize_orgao_form,
    rebuild_orgao_closure,
    validate_orgao_move,
)
from .shared import get_or_404


def _serialize_orgao(orgao):
    return {
        "id": orgao.id,
        "nome": orgao.nome,
        "sigla": orgao.sigla,
        "tipo": orgao.tipo,
        "tipo_id": orgao.tipo_id,
        "pai_id": orgao.pai_id,
        "ordem": orgao.ordem,
        "ativo": orgao.ativo,
        "codigo_externo": orgao.codigo_externo,
    }


def _wants_json():
    if request.is_json:
        return True
    accept = request.headers.get("Accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    return False


def _ancestrais(orgao):
    chain = []
    current = orgao
    seen = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        chain.insert(0, current)
        current = current.pai
    return chain


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


def _render_orgao_form(**context):
    context.setdefault("tipos", get_orgao_tipo_options())
    context.setdefault("tipo_rank", get_tipo_rank_map())
    return render_template("admin/orgao_form.html", **context)


@main_bp.route("/admin/orgaos")
@login_required
@admin_required
def list_orgaos():
    _prepare_orgao_catalogs()
    raizes = (
        OrgaoUnidade.query.filter(OrgaoUnidade.pai_id.is_(None))
        .order_by(OrgaoUnidade.ordem, OrgaoUnidade.sigla)
        .all()
    )
    todos = OrgaoUnidade.query.order_by(OrgaoUnidade.sigla).all()
    return render_template(
        "admin/orgao_tree.html",
        raizes=raizes,
        todos=todos,
        total_unidades=len(todos),
        tipos=get_orgao_tipo_options(include_inactive=True),
        max_depth=MAX_DEPTH,
        tipo_rank=get_tipo_rank_map(),
    )


@main_bp.route("/admin/orgaos/tipos")
@login_required
@admin_required
def list_orgao_tipos():
    _prepare_orgao_catalogs()
    tipos = get_orgao_tipo_options(include_inactive=True)
    usage_counts = {
        tipo_id: count
        for tipo_id, count in db.session.query(
            OrgaoUnidade.tipo_id, db.func.count(OrgaoUnidade.id)
        )
        .group_by(OrgaoUnidade.tipo_id)
        .all()
    }
    return render_template(
        "admin/orgao_tipos.html",
        tipos=tipos,
        usage_counts=usage_counts,
    )


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


@main_bp.route("/admin/orgaos/tipos/new", methods=["GET", "POST"])
@login_required
@admin_required
def add_orgao_tipo():
    _prepare_orgao_catalogs()
    if request.method == "POST":
        data, error = _normalize_tipo_form(request.form)
        if error:
            flash(error, "danger")
            return render_template(
                "admin/orgao_tipo_form.html",
                action_verb="Adicionar",
                tipo=request.form,
            )
        tipo = OrgaoTipo(**data, is_system=False)
        db.session.add(tipo)
        db.session.commit()
        flash(f'Tipo "{tipo.nome}" criado com sucesso.', "success")
        return redirect(url_for("main.list_orgao_tipos"))

    return render_template(
        "admin/orgao_tipo_form.html",
        action_verb="Adicionar",
        tipo={"ativo": True, "nivel": 1},
    )


@main_bp.route("/admin/orgaos/tipos/<int:tipo_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_orgao_tipo(tipo_id):
    _prepare_orgao_catalogs()
    tipo = get_or_404(OrgaoTipo, tipo_id)
    if request.method == "POST":
        data, error = _normalize_tipo_form(request.form, tipo)
        if error:
            flash(error, "danger")
            return render_template(
                "admin/orgao_tipo_form.html",
                action_verb="Editar",
                tipo=request.form,
                editing_id=tipo.id,
            )

        if (
            tipo.ativo
            and not data["ativo"]
            and OrgaoUnidade.query.filter_by(tipo_id=tipo.id).first() is not None
        ):
            flash("Não é possível desativar tipo em uso por órgãos.", "warning")
            return redirect(url_for("main.edit_orgao_tipo", tipo_id=tipo.id))

        affected = _invalid_orgao_type_level_changes(
            tipo, data["nivel"], data["permite_raiz"]
        )
        if affected:
            labels = ", ".join(o.sigla for o in affected[:8])
            if len(affected) > 8:
                labels += f" e mais {len(affected) - 8}"
            flash(
                "Alteração bloqueada: existem órgãos que ficariam fora da regra "
                f"hierárquica ({labels}).",
                "danger",
            )
            return redirect(url_for("main.edit_orgao_tipo", tipo_id=tipo.id))

        tipo.nome = data["nome"]
        tipo.slug = data["slug"]
        tipo.nivel = data["nivel"]
        tipo.descricao = data["descricao"]
        tipo.ativo = data["ativo"]
        tipo.permite_raiz = data["permite_raiz"]
        for orgao in OrgaoUnidade.query.filter_by(tipo_id=tipo.id).all():
            orgao.tipo = tipo.nome
        db.session.commit()
        flash(f'Tipo "{tipo.nome}" atualizado com sucesso.', "success")
        return redirect(url_for("main.list_orgao_tipos"))

    return render_template(
        "admin/orgao_tipo_form.html",
        action_verb="Editar",
        tipo=tipo,
        editing_id=tipo.id,
    )


@main_bp.route("/admin/orgaos/tipos/<int:tipo_id>/toggle-ativo", methods=["POST"])
@login_required
@admin_required
def toggle_orgao_tipo(tipo_id):
    _prepare_orgao_catalogs()
    tipo = get_or_404(OrgaoTipo, tipo_id)
    if tipo.permite_raiz and tipo.ativo:
        flash("Não é possível desativar o tipo raiz ativo.", "warning")
        return redirect(url_for("main.list_orgao_tipos"))
    if tipo.ativo and OrgaoUnidade.query.filter_by(tipo_id=tipo.id).first() is not None:
        flash("Não é possível desativar tipo em uso por órgãos.", "warning")
        return redirect(url_for("main.list_orgao_tipos"))
    tipo.ativo = not tipo.ativo
    db.session.commit()
    estado = "ativado" if tipo.ativo else "desativado"
    flash(f'Tipo "{tipo.nome}" {estado}.', "success")
    return redirect(url_for("main.list_orgao_tipos"))


@main_bp.route("/admin/orgaos/tipos/<int:tipo_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_orgao_tipo(tipo_id):
    _prepare_orgao_catalogs()
    tipo = get_or_404(OrgaoTipo, tipo_id)
    if OrgaoUnidade.query.filter_by(tipo_id=tipo.id).first() is not None:
        flash("Não é possível excluir tipo em uso por órgãos.", "warning")
        return redirect(url_for("main.list_orgao_tipos"))
    if tipo.permite_raiz:
        flash("Não é possível excluir tipo permitido para raiz.", "warning")
        return redirect(url_for("main.list_orgao_tipos"))
    nome = tipo.nome
    db.session.delete(tipo)
    db.session.commit()
    flash(f'Tipo "{nome}" excluído com sucesso.', "success")
    return redirect(url_for("main.list_orgao_tipos"))


@main_bp.route("/admin/orgaos/new", methods=["GET", "POST"])
@login_required
@admin_required
def add_orgao():
    _prepare_orgao_catalogs()
    has_root = (
        OrgaoUnidade.query.filter(OrgaoUnidade.pai_id.is_(None)).first() is not None
    )
    is_root = not has_root

    if request.method == "POST":
        data, error = normalize_orgao_form(request.form, is_root=is_root)
        if error:
            flash(error, "danger")
            return _render_orgao_form(
                action_verb="Adicionar",
                orgao=request.form,
                is_root=is_root,
                candidate_pais=_candidate_pais(),
                preselected_pai_id=request.form.get("pai_id"),
            )

        # Valida profundidade ao inserir
        if not is_root and data["pai_id"] is not None:
            pai = db.session.get(OrgaoUnidade, data["pai_id"])
            if pai is None:
                flash("Órgão pai não encontrado.", "danger")
                return redirect(url_for("main.add_orgao"))
            if compute_orgao_depth(pai) + 1 > MAX_DEPTH:
                flash(f"Profundidade máxima de {MAX_DEPTH} níveis excedida.", "danger")
                return redirect(url_for("main.add_orgao", pai_id=pai.id))

        try:
            novo = OrgaoUnidade(**data)
            db.session.add(novo)
            db.session.flush()
            rebuild_orgao_closure()
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            flash(f"Erro ao criar órgão: {exc}", "danger")
            return redirect(url_for("main.add_orgao"))

        flash(f'Órgão "{novo.sigla}" criado com sucesso.', "success")
        return redirect(url_for("main.list_orgaos") + f"#orgao-{novo.id}")

    pai_pre = request.args.get("pai_id")
    pai_pre_id = None
    if pai_pre:
        try:
            pai_pre_id = int(pai_pre)
        except (TypeError, ValueError):
            pai_pre_id = None

    root_tipo = OrgaoTipo.query.filter_by(permite_raiz=True, ativo=True).first()
    return _render_orgao_form(
        action_verb="Adicionar",
        orgao={
            "ativo": True,
            "ordem": 0,
            "pai_id": pai_pre_id,
            "tipo": root_tipo.nome if is_root and root_tipo else "",
            "tipo_id": root_tipo.id if is_root and root_tipo else "",
        },
        is_root=is_root,
        candidate_pais=_candidate_pais(),
        preselected_pai_id=pai_pre_id,
    )


@main_bp.route("/admin/orgaos/<int:orgao_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_orgao(orgao_id):
    _prepare_orgao_catalogs()
    orgao = get_or_404(OrgaoUnidade, orgao_id)
    is_root = orgao.pai_id is None

    if request.method == "POST":
        data, error = normalize_orgao_form(request.form, is_root=is_root)
        if error:
            flash(error, "danger")
            return _render_orgao_form(
                action_verb="Editar",
                orgao=request.form,
                is_root=is_root,
                candidate_pais=_candidate_pais(orgao),
                preselected_pai_id=request.form.get("pai_id"),
                editing_id=orgao.id,
            )

        if not is_root and data["pai_id"] != orgao.pai_id:
            move_error = validate_orgao_move(
                orgao, data["pai_id"], child_tipo=data["tipo"]
            )
            if move_error:
                flash(move_error, "danger")
                return redirect(url_for("main.edit_orgao", orgao_id=orgao.id))

        if data["tipo"] != orgao.tipo:
            for filho in orgao.filhos:
                if not is_valid_parent_tipo(data["tipo"], filho.tipo):
                    flash(
                        f'Tipo "{data["tipo"]}" inválido: o filho "{filho.sigla}" '
                        f'é do tipo "{filho.tipo}".',
                        "danger",
                    )
                    return redirect(url_for("main.edit_orgao", orgao_id=orgao.id))

        try:
            orgao.nome = data["nome"]
            orgao.sigla = data["sigla"]
            orgao.tipo = data["tipo"]
            orgao.tipo_id = data["tipo_id"]
            if not is_root:
                orgao.pai_id = data["pai_id"]
            orgao.ordem = data["ordem"]
            orgao.ativo = data["ativo"]
            orgao.codigo_externo = data["codigo_externo"]
            orgao.data_inicio_vigencia = data["data_inicio_vigencia"]
            orgao.data_fim_vigencia = data["data_fim_vigencia"]
            rebuild_orgao_closure()
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            flash(f"Erro ao atualizar órgão: {exc}", "danger")
            return redirect(url_for("main.edit_orgao", orgao_id=orgao.id))

        flash(f'Órgão "{orgao.sigla}" atualizado com sucesso.', "success")
        return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")

    return _render_orgao_form(
        action_verb="Editar",
        orgao=orgao,
        is_root=is_root,
        candidate_pais=_candidate_pais(orgao),
        preselected_pai_id=orgao.pai_id,
        editing_id=orgao.id,
    )


@main_bp.route("/admin/orgaos/<int:orgao_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_orgao(orgao_id):
    orgao = get_or_404(OrgaoUnidade, orgao_id)

    if orgao.filhos:
        flash("Mova as subunidades antes de excluir.", "warning")
        return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")

    if orgao.pai_id is None:
        flash("Não é possível excluir o órgão raiz.", "warning")
        return redirect(url_for("main.list_orgaos"))

    sigla = orgao.sigla
    parent_id = orgao.pai_id
    try:
        db.session.delete(orgao)
        db.session.flush()
        rebuild_orgao_closure()
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao excluir órgão: {exc}", "danger")
        return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")

    flash(f'Órgão "{sigla}" excluído com sucesso.', "success")
    return redirect(url_for("main.list_orgaos") + f"#orgao-{parent_id}")


@main_bp.route("/admin/orgaos/<int:orgao_id>/move", methods=["POST"])
@login_required
@admin_required
def move_orgao(orgao_id):
    orgao = get_or_404(OrgaoUnidade, orgao_id)

    payload = request.get_json(silent=True) or {}
    raw_pai = (
        payload.get("pai_id") if "pai_id" in payload else request.form.get("pai_id")
    )

    if raw_pai in (None, "", "None", "null"):
        new_pai_id = None
    else:
        try:
            new_pai_id = int(raw_pai)
        except (TypeError, ValueError):
            msg = "Órgão pai inválido."
            if _wants_json():
                return jsonify({"ok": False, "error": msg}), 400
            flash(msg, "danger")
            return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")

    error = validate_orgao_move(orgao, new_pai_id)
    if error:
        if _wants_json():
            return jsonify({"ok": False, "error": error}), 400
        flash(error, "danger")
        return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")

    try:
        orgao.pai_id = new_pai_id
        if new_pai_id is not None:
            siblings_count = (
                OrgaoUnidade.query.filter(OrgaoUnidade.pai_id == new_pai_id)
                .filter(OrgaoUnidade.id != orgao.id)
                .count()
            )
            orgao.ordem = siblings_count
        rebuild_orgao_closure()
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if _wants_json():
            return jsonify({"ok": False, "error": str(exc)}), 500
        flash(f"Erro ao mover órgão: {exc}", "danger")
        return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")

    if _wants_json():
        return jsonify({"ok": True, "orgao": _serialize_orgao(orgao)})

    flash(f'Órgão "{orgao.sigla}" movido com sucesso.', "success")
    return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")


@main_bp.route("/admin/orgaos/<int:orgao_id>/reorder", methods=["POST"])
@login_required
@admin_required
def reorder_orgao(orgao_id):
    orgao = get_or_404(OrgaoUnidade, orgao_id)
    direction = (request.form.get("direction") or "").lower()

    if direction not in ("up", "down"):
        flash("Direção inválida.", "danger")
        return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")

    siblings = (
        OrgaoUnidade.query.filter(OrgaoUnidade.pai_id == orgao.pai_id)
        .order_by(OrgaoUnidade.ordem, OrgaoUnidade.sigla)
        .all()
    )
    indices = {s.id: i for i, s in enumerate(siblings)}
    idx = indices.get(orgao.id)
    if idx is None:
        return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")

    target_idx = idx - 1 if direction == "up" else idx + 1
    if target_idx < 0 or target_idx >= len(siblings):
        return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")

    other = siblings[target_idx]
    try:
        orgao.ordem, other.ordem = other.ordem, orgao.ordem
        if orgao.ordem == other.ordem:
            orgao.ordem = target_idx
            other.ordem = idx
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao reordenar: {exc}", "danger")

    return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")


@main_bp.route("/admin/orgaos/<int:orgao_id>/toggle-ativo", methods=["POST"])
@login_required
@admin_required
def toggle_orgao_ativo(orgao_id):
    orgao = get_or_404(OrgaoUnidade, orgao_id)
    try:
        orgao.ativo = not orgao.ativo
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f"Erro ao alterar status: {exc}", "danger")
        return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")

    estado = "ativado" if orgao.ativo else "desativado"
    flash(f'Órgão "{orgao.sigla}" {estado}.', "success")
    return redirect(url_for("main.list_orgaos") + f"#orgao-{orgao.id}")
