from pathlib import Path


def test_admin_templates_list_has_clickable_rows_and_only_duplicate_delete(
    client_admin,
):
    response = client_admin.get("/admin/templates")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Ações: apenas duplicar + excluir (lápis e "+" removidos)
    assert "tpl-action-duplicate" in html
    assert "tpl-action-delete" in html
    assert "btn-edit-clean" not in html

    # Linhas clicáveis com papel link e controle de propagação
    assert "tpl-row" in html
    assert 'data-template-url="/admin/templates/' in html
    assert 'role="link"' in html
    assert 'data-stop-row-click="1"' in html


def test_admin_template_form_new_has_counter_clear_and_drag(client_admin):
    response = client_admin.get("/admin/templates/new")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Contador dinâmico "N etapas · M dias no total"
    assert "data-stage-counter" in html
    assert "data-stage-count" in html
    assert "data-stage-duration" in html

    # Botão "Limpar tudo"
    assert "data-clear-all" in html
    assert "Limpar tudo" in html
    assert "fa-broom" not in html

    # Drag handle funcional (não apenas decorativo)
    assert "data-drag-handle" in html
    assert 'draggable="true"' in html
    assert "tpl-stage-card" in html

    # Botão de adicionar com dica do Enter
    assert "data-add-stage" in html
    assert "Adicionar nova etapa" in html

    # Cancelar + Salvar ficam abaixo do item de adicao; sem card inferior.
    assert "tpl-form-stage-actions" in html
    assert html.count("tpl-btn-primary") == 1
    assert html.count("tpl-btn-secondary") == 1
    assert html.index("</section>") < html.index('class="tpl-form-actions"')
    assert "tpl-form-footer" not in html
    assert "Arraste pelo" not in html

    # Remoção de etapa é um X textual, sem ícone de lixeira.
    assert "fa-trash" not in html
    assert 'data-remove-stage aria-label="Remover etapa">X</button>' in html
    assert "</div>\n        <button type=\"button\" class=\"tpl-stage-remove\"" in html

    # JS externo carregado
    assert "js/admin/template_form.js" in html
    assert "template-form.css?v=20260424b" in html
    assert "template_form.js?v=20260424b" in html


def test_admin_template_form_edit_renders_existing_stages(client_admin, seed_data):
    response = client_admin.get(f"/admin/templates/{seed_data['template_id']}/edit")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Cada etapa existente aparece com estrutura esperada
    assert "data-stage-item" in html
    assert "data-stage-number" in html
    assert 'name="stage_name"' in html
    assert 'name="stage_duration"' in html
    assert "tpl-stage-duration-suffix" not in html


def test_admin_templates_list_has_search_and_sort(client_admin):
    response = client_admin.get("/admin/templates")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'name="q"' in html
    assert 'name="order"' in html
    # Todas as opções de ordenação esperadas
    for opt in (
        "mais_usados",
        "nome",
        "mais_etapas",
        "maior_duracao",
        "edicao_recente",
    ):
        assert f'value="{opt}"' in html


def test_admin_template_form_enter_focuses_created_stage_contract():
    js_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "js"
        / "admin"
        / "template_form.js"
    )
    js = js_path.read_text(encoding="utf-8")

    assert "(!options || options.focus !== false)" in js
    assert "window.requestAnimationFrame" in js
    assert "nameInput.focus()" in js


def test_admin_template_form_draft_stage_removed_on_blur_contract():
    js_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "js"
        / "admin"
        / "template_form.js"
    )
    js = js_path.read_text(encoding="utf-8")

    assert "item.dataset.draftStage = '1'" in js
    assert "addStage({ draft: true })" in js
    assert "list.addEventListener('focusout'" in js
    assert "removeStage(item)" in js


def test_admin_template_form_add_stage_matches_inline_entry_visual_contract():
    css_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "admin"
        / "template-form.css"
    )
    css = css_path.read_text(encoding="utf-8")

    assert ".tpl-form-stage-actions" in css
    assert ".tpl-form-add-stage" in css
    assert "display: grid;" in css
    assert "grid-template-columns: minmax(0, 1fr) 24px;" in css
    assert "grid-column: 1;" in css
    assert "border: 1px dashed var(--tf-border-strong);" in css
    assert "background: #f6faff;" in css
    assert "min-height: 44px;" in css
    assert ".tpl-form-icon-btn" not in css


def test_admin_template_form_minimal_stage_fields_contract():
    css_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "admin"
        / "template-form.css"
    )
    css = css_path.read_text(encoding="utf-8")

    assert "border: 1px solid var(--tf-border);" in css
    assert "background: #fbfdff;" in css
    assert ".tpl-stage-card" in css
    assert "grid-template-columns: minmax(0, 1fr) 24px;" in css
    assert "grid-template-columns: 22px 30px minmax(0, 1fr);" in css
    assert "grid-template-columns: minmax(0, 1fr) 68px;" in css
    assert ".tpl-stage-number" in css
    assert "background: transparent;" in css
    assert "-webkit-appearance: none;" in css
    assert "appearance: textfield;" in css
    assert ".tpl-stage-remove" in css
    assert "border: none;" in css
    # Reveal do botão de remover via :hover/:focus-within nativos (um item por vez).
    assert "opacity: 0;" in css
    assert "pointer-events: none;" in css
    assert ".tpl-stage-item:hover .tpl-stage-remove," in css
    assert ".tpl-stage-item:focus-within .tpl-stage-remove" in css
    assert "opacity: 1;" in css
    assert "pointer-events: auto;" in css


def test_admin_template_form_stage_remove_reveals_on_native_hover_contract():
    root = Path(__file__).resolve().parents[2]
    css = (
        root / "static" / "css" / "admin" / "template-form.css"
    ).read_text(encoding="utf-8")
    js = (
        root / "static" / "js" / "admin" / "template_form.js"
    ).read_text(encoding="utf-8")

    # O reveal do botão de remover etapa é puramente CSS (:hover/:focus-within),
    # naturalmente um item por vez — a antiga lógica JS de "active item"
    # (classes is-hover-active) foi removida.
    assert ".tpl-stage-item:hover .tpl-stage-remove," in css
    assert ".tpl-stage-item:focus-within .tpl-stage-remove" in css
    assert "is-hover-active" not in css
    assert "is-hover-active" not in js
    # O template_form.js cuida só do ciclo de vida das etapas (form wiring).
    assert "getElementById('templateForm')" in js
    assert "addStage(" in js


def test_admin_template_form_drag_uses_single_drop_indicator_contract():
    root = Path(__file__).resolve().parents[2]
    css = (
        root / "static" / "css" / "admin" / "template-form.css"
    ).read_text(encoding="utf-8")
    js = (
        root / "static" / "js" / "admin" / "template_form.js"
    ).read_text(encoding="utf-8")

    assert ".tpl-stage-drop-indicator" in css
    assert ".tpl-stage-drop-indicator.show" in css
    assert "tpl-stage-drop-indicator" in js
    assert "function getInsertionSlot(clientY)" in js
    assert "function showDropIndicator(slot)" in js
    assert "function hideDropIndicator()" in js
    assert "showDropIndicator(slot)" in js
    assert "list.insertBefore(draggedItem, slot.referenceItem)" in js
    assert "is-drop-target-top" not in js
    assert "is-drop-target-bottom" not in js
    assert "is-drop-target-top" not in css
    assert "is-drop-target-bottom" not in css


def test_admin_template_form_drag_canonicalizes_adjacent_drop_slots_contract():
    js_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "js"
        / "admin"
        / "template_form.js"
    )
    js = js_path.read_text(encoding="utf-8")

    assert "function getDropItems()" in js
    assert "return item !== draggedItem;" in js
    assert "previousItem: previousItem" in js
    assert "referenceItem: item" in js
    assert "referenceItem: null" in js
    assert "const anchorRect = (slot.referenceItem || slot.previousItem).getBoundingClientRect();" in js


def test_admin_template_form_dark_drag_handle_contract():
    css_path = (
        Path(__file__).resolve().parents[2]
        / "static"
        / "css"
        / "admin"
        / "template-form.css"
    )
    css = css_path.read_text(encoding="utf-8")

    assert 'html[data-theme="dark"] body.is-authenticated .tpl-stage-drag {' in css
    assert "color: #9fb2c7;" in css
    assert (
        'html[data-theme="dark"] body.is-authenticated .tpl-stage-drag:hover,'
        in css
    )
    assert "background: rgba(148, 163, 184, 0.1);" in css
