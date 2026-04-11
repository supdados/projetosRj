/**
 * caderno.js — Editor de blocos do Caderno pessoal.
 *
 * Responsabilidades:
 * - Carregar e renderizar blocos do usuário via API
 * - Gerenciar editor contenteditable para blocos de texto/nota
 * - Detectar "/" e abrir o menu de tipos de bloco
 * - Abrir modal de busca para blocos de referência
 * - Auto-salvar no blur, deletar e reordenar blocos
 *
 * Segurança: todo conteúdo de usuário passado para innerHTML usa
 * escapeHtml(). URLs vêm exclusivamente de url_for() no servidor
 * (caminhos relativos) e são validadas por isSafeUrl() antes de
 * serem usadas em atributos href.
 */
(function () {
  'use strict';

  const CFG = window.__CADERNO_CONFIG__ || {};

  // ── Elementos DOM ──────────────────────────────────────────
  const blocksContainer = document.getElementById('cadernoBlocks');
  const emptyHint       = document.getElementById('cadernoEmptyHint');
  const addZone         = document.getElementById('cadernoAddZone');
  const dateEl          = document.getElementById('cadernoDate');
  const paper           = document.getElementById('cadernoPaper');
  const expandZone      = document.getElementById('cadernoExpandZone');

  const slashMenu       = document.getElementById('slashMenu');
  const slashMenuList   = document.getElementById('slashMenuList');

  const searchBackdrop  = document.getElementById('cadernoSearchBackdrop');
  const searchModal     = document.getElementById('cadernoSearchModal');
  const searchModalTitle= document.getElementById('cadernoSearchModalTitle');
  const searchModalIcon = document.getElementById('cadernoSearchModalIcon');
  const searchModalClose= document.getElementById('cadernoSearchModalClose');
  const searchInput     = document.getElementById('cadernoSearchInput');
  const searchResults   = document.getElementById('cadernoSearchResults');

  // ── Estado ────────────────────────────────────────────────
  let blocks = [];
  let slashTargetBlockId = null;
  let slashMenuActiveIdx = -1;
  let searchDebounceTimer = null;
  let searchPendingType = null;
  let searchPendingPosition = null;

  // ── Segurança: escape e validação ─────────────────────────
  function escapeHtml(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#x27;');
  }

  /**
   * Valida que uma URL é um caminho relativo seguro gerado pelo servidor
   * (url_for). Rejeita qualquer coisa com protocolo, javascript:, data:, etc.
   */
  function isSafeUrl(url) {
    if (!url || typeof url !== 'string') return false;
    const trimmed = url.trim();
    // Aceita apenas caminhos relativos que começam com /
    return /^\/[^/]/.test(trimmed) || trimmed === '/';
  }

  function safeHref(url) {
    return isSafeUrl(url) ? escapeHtml(url) : '#';
  }

  // ── Data atual ───────────────────────────────────────────
  function renderDate() {
    if (!dateEl) return;
    const now = new Date();
    const formatted = now.toLocaleDateString('pt-BR', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    });
    dateEl.textContent = formatted.charAt(0).toUpperCase() + formatted.slice(1);
  }

  // ── CSRF helper ──────────────────────────────────────────
  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
  }

  function apiFetch(url, opts = {}) {
    const method = (opts.method || 'GET').toUpperCase();
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (method !== 'GET') headers['X-CSRFToken'] = getCsrfToken();
    return fetch(url, { ...opts, method, headers });
  }

  // ── Helpers de status ────────────────────────────────────
  const STATUS_LABELS = {
    nao_iniciada:   'Não iniciada',
    em_andamento:   'Em andamento',
    para_validacao: 'Para validação',
    para_ajustes:   'Para ajustes',
    finalizada:     'Finalizada',
  };

  const PRIORIDADE_LABELS = {
    urgente: 'Urgente',
    alta:    'Alta',
    media:   'Média',
    baixa:   'Baixa',
  };

  // Conjunto de valores de status permitidos (proteção extra)
  const VALID_STATUSES = new Set(Object.keys(STATUS_LABELS));
  const VALID_PRIOS    = new Set(Object.keys(PRIORIDADE_LABELS));

  function statusBadge(status) {
    const safeStatus = VALID_STATUSES.has(status) ? status : 'nao_iniciada';
    const label = escapeHtml(STATUS_LABELS[safeStatus] || safeStatus);
    return `<span class="caderno-task-status caderno-task-status--${safeStatus}">${label}</span>`;
  }

  function prioLabel(prio) {
    if (!prio) return '';
    const safePrio = VALID_PRIOS.has(prio) ? prio : '';
    if (!safePrio) return '';
    const label = escapeHtml(PRIORIDADE_LABELS[safePrio]);
    return `<span class="caderno-prio caderno-prio--${safePrio}">${label}</span>`;
  }

  function etapaStatusBadge(ref) {
    if (ref.done)     return '<span class="caderno-etapa-status caderno-etapa-status--done"><i class="fas fa-check"></i> Conclu\u00edda</span>';
    if (ref.iniciada) return '<span class="caderno-etapa-status caderno-etapa-status--iniciada"><i class="fas fa-spinner"></i> Em andamento</span>';
    return '<span class="caderno-etapa-status caderno-etapa-status--pendente"><i class="fas fa-clock"></i> N\u00e3o iniciada</span>';
  }

  function formatDate(iso) {
    if (!iso || typeof iso !== 'string') return '';
    const parts = iso.split('T')[0].split('-');
    if (parts.length !== 3) return '';
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }

  // ── Renderização de blocos ───────────────────────────────
  function buildBlockActions(idx) {
    const isFirst = idx === 0;
    const isLast  = idx === blocks.length - 1;
    return `
      <div class="caderno-block-actions" aria-hidden="true">
        <button class="caderno-block-btn" data-action="up" title="Mover para cima"${isFirst ? ' disabled' : ''}>
          <i class="fas fa-chevron-up"></i>
        </button>
        <button class="caderno-block-btn" data-action="down" title="Mover para baixo"${isLast ? ' disabled' : ''}>
          <i class="fas fa-chevron-down"></i>
        </button>
        <button class="caderno-block-btn caderno-block-btn--delete" data-action="delete" title="Remover bloco">
          <i class="fas fa-trash-alt"></i>
        </button>
      </div>`;
  }

  function renderBlockHTML(block) {
    const idx = blocks.findIndex(b => b.id === block.id);
    const actions = buildBlockActions(idx);

    if (block.block_type === 'text') {
      return `
        <div class="caderno-block caderno-block--text" data-block-id="${block.id}" role="listitem">
          ${actions}
          <div
            class="caderno-text-editor"
            contenteditable="true"
            data-placeholder="Escreva algo... (/ para inserir bloco)"
            data-block-id="${block.id}"
            spellcheck="false"
          >${escapeHtml(block.content)}</div>
        </div>`;
    }

    if (block.block_type === 'nota') {
      return `
        <div class="caderno-block caderno-block--nota" data-block-id="${block.id}" role="listitem">
          ${actions}
          <div class="caderno-nota-card">
            <div class="caderno-nota-card-header">
              <i class="fas fa-sticky-note"></i> Nota
            </div>
            <div
              class="caderno-text-editor"
              contenteditable="true"
              data-placeholder="Escreva sua nota..."
              data-block-id="${block.id}"
              spellcheck="false"
            >${escapeHtml(block.content)}</div>
          </div>
        </div>`;
    }

    if (block.block_type === 'project') {
      const ref = block.ref_data;
      if (!ref) return renderNullRef(block, actions, 'Projeto removido');

      const pct = ref.total_etapas > 0
        ? Math.round((ref.etapas_concluidas / ref.total_etapas) * 100)
        : 0;
      const href = safeHref(ref.url);

      return `
        <div class="caderno-block caderno-block--project" data-block-id="${block.id}" role="listitem">
          ${actions}
          <a href="${href}" class="caderno-ref-card" target="_blank" rel="noopener noreferrer">
            <span class="caderno-ref-card-icon"><i class="fas fa-folder"></i></span>
            <span class="caderno-ref-card-body">
              <span class="caderno-ref-card-type">Projeto</span>
              <span class="caderno-ref-card-title" title="${escapeHtml(ref.titulo)}">${escapeHtml(ref.titulo)}</span>
              <span class="caderno-ref-card-meta">
                ${ref.area ? `<span>${escapeHtml(ref.area)}</span>` : ''}
                ${ref.status ? `<span class="caderno-ref-badge">${escapeHtml(ref.status)}</span>` : ''}
                ${ref.prioridade ? prioLabel(ref.prioridade) : ''}
              </span>
              ${ref.total_etapas > 0 ? `
              <div class="caderno-project-progress">
                <div class="caderno-progress-bar-wrap">
                  <div class="caderno-progress-bar" style="width:${Math.min(100, Math.max(0, pct))}%"></div>
                </div>
                <span class="caderno-progress-label">${escapeHtml(String(ref.etapas_concluidas))}/${escapeHtml(String(ref.total_etapas))}</span>
              </div>` : ''}
            </span>
            <span class="caderno-ref-card-link-hint"><i class="fas fa-external-link-alt"></i></span>
          </a>
        </div>`;
    }

    if (block.block_type === 'etapa') {
      const ref = block.ref_data;
      if (!ref) return renderNullRef(block, actions, 'Etapa removida');

      const dateRange = [formatDate(ref.data_inicio), formatDate(ref.data_fim)]
        .filter(Boolean).join(' \u2192 ');
      const href = safeHref(ref.url);

      return `
        <div class="caderno-block caderno-block--etapa" data-block-id="${block.id}" role="listitem">
          ${actions}
          <a href="${href}" class="caderno-ref-card" target="_blank" rel="noopener noreferrer">
            <span class="caderno-ref-card-icon"><i class="fas fa-tasks"></i></span>
            <span class="caderno-ref-card-body">
              <span class="caderno-ref-card-type">Etapa</span>
              <span class="caderno-ref-card-title" title="${escapeHtml(ref.descricao)}">${escapeHtml(ref.descricao)}</span>
              <span class="caderno-ref-card-meta">
                ${ref.project_titulo ? `<span>${escapeHtml(ref.project_titulo)}</span>` : ''}
                ${etapaStatusBadge(ref)}
                ${dateRange ? `<span><i class="fas fa-calendar-alt"></i> ${escapeHtml(dateRange)}</span>` : ''}
                ${ref.responsavel ? `<span>${escapeHtml(ref.responsavel)}</span>` : ''}
              </span>
            </span>
            <span class="caderno-ref-card-link-hint"><i class="fas fa-external-link-alt"></i></span>
          </a>
        </div>`;
    }

    if (block.block_type === 'tarefa') {
      const ref = block.ref_data;
      if (!ref) return renderNullRef(block, actions, 'Tarefa removida');
      const href = safeHref(ref.url);

      return `
        <div class="caderno-block caderno-block--tarefa" data-block-id="${block.id}" role="listitem">
          ${actions}
          <a href="${href}" class="caderno-ref-card" target="_blank" rel="noopener noreferrer">
            <span class="caderno-ref-card-icon"><i class="fas fa-check-square"></i></span>
            <span class="caderno-ref-card-body">
              <span class="caderno-ref-card-type">Tarefa</span>
              <span class="caderno-ref-card-title" title="${escapeHtml(ref.descricao)}">${escapeHtml(ref.descricao)}</span>
              <span class="caderno-ref-card-meta">
                ${ref.project_titulo ? `<span>${escapeHtml(ref.project_titulo)}</span>` : ''}
                ${statusBadge(ref.status)}
                ${ref.prioridade ? prioLabel(ref.prioridade) : ''}
                ${ref.responsavel ? `<span>${escapeHtml(ref.responsavel)}</span>` : ''}
              </span>
            </span>
            <span class="caderno-ref-card-link-hint"><i class="fas fa-external-link-alt"></i></span>
          </a>
        </div>`;
    }

    return '';
  }

  function renderNullRef(block, actions, msg) {
    return `
      <div class="caderno-block caderno-block--${block.block_type}" data-block-id="${block.id}" role="listitem">
        ${actions}
        <div class="caderno-ref-null">
          <i class="fas fa-unlink"></i>
          <span>${escapeHtml(msg)}</span>
        </div>
      </div>`;
  }

  // ── Render all ──────────────────────────────────────────
  function renderAllBlocks() {
    blocksContainer.innerHTML = blocks.map(renderBlockHTML).join('');
    bindBlockEvents();
    updateEmptyHint();
  }

  function updateEmptyHint() {
    if (!emptyHint) return;
    emptyHint.classList.toggle('is-hidden', blocks.length > 0);
  }

  // ── Bind events ─────────────────────────────────────────
  function bindBlockEvents() {
    blocksContainer.querySelectorAll('[contenteditable]').forEach(el => {
      el.addEventListener('input', onEditorInput);
      el.addEventListener('blur',  onEditorBlur);
      el.addEventListener('keydown', onEditorKeydown);
    });

    blocksContainer.querySelectorAll('.caderno-block-btn').forEach(btn => {
      btn.addEventListener('click', onBlockActionClick);
    });
  }

  // ── Editor events ────────────────────────────────────────
  function onEditorInput(e) {
    const el = e.target;
    autoResizeEditor(el);
    const text = el.textContent || '';

    if (text === '/') {
      const blockId = parseInt(el.dataset.blockId, 10);
      openSlashMenu(el, blockId);
    } else {
      closeSlashMenu();
    }
  }

  function onEditorBlur(e) {
    const el      = e.target;
    const blockId = parseInt(el.dataset.blockId, 10);
    const content = el.textContent || '';

    // Bloco de texto/nota vazio que nunca foi preenchido → remove
    // Usamos setTimeout para deixar possíveis cliques em outros elementos se processarem primeiro
    if (!content.trim()) {
      const block = blocks.find(b => b.id === blockId);
      if (block && (block.block_type === 'text' || block.block_type === 'nota')) {
        setTimeout(() => {
          // Só remove se nenhum outro elemento do mesmo bloco ganhou foco
          const stillFocused = blocksContainer.querySelector(
            `.caderno-block[data-block-id="${blockId}"] :focus`
          );
          if (!stillFocused) deleteBlock(blockId);
        }, 150);
        return;
      }
    }

    saveBlockContent(blockId, content);
  }

  function onEditorKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const blockId = parseInt(e.target.dataset.blockId, 10);
      const content = e.target.textContent || '';
      saveBlockContent(blockId, content);
      createTextBlockAfter(blockId);
    }
  }

  function autoResizeEditor(el) {
    el.style.height = 'auto';
    el.style.height = el.scrollHeight + 'px';
  }

  // ── Save content ─────────────────────────────────────────
  async function saveBlockContent(blockId, content) {
    const block = blocks.find(b => b.id === blockId);
    if (!block) return;
    if (block.content === content) return;
    block.content = content;

    try {
      await apiFetch(`${CFG.apiBlocksUrl}/${blockId}`, {
        method: 'PATCH',
        body: JSON.stringify({ content }),
      });
    } catch (err) {
      console.warn('[caderno] Falha ao salvar bloco', blockId, err);
    }
  }

  // ── Criar bloco de texto ──────────────────────────────────
  async function createTextBlockAfter(afterBlockId) {
    const idx = blocks.findIndex(b => b.id === afterBlockId);
    const nextBlock  = blocks[idx + 1];
    const afterBlock = blocks[idx];

    let position;
    if (nextBlock) {
      position = (afterBlock.position + nextBlock.position) / 2;
    } else {
      position = (afterBlock ? afterBlock.position : 0) + 1000;
    }

    await createBlock({ block_type: 'text', content: '', position });
  }

  async function createBlock(data) {
    try {
      const res = await apiFetch(CFG.apiBlocksCreate, {
        method: 'POST',
        body: JSON.stringify(data),
      });
      if (!res.ok) return null;
      const json = await res.json();
      const block = json.block;
      insertBlockIntoState(block);
      renderAllBlocks();
      focusBlock(block.id);
      return block;
    } catch (err) {
      console.warn('[caderno] Falha ao criar bloco', err);
      return null;
    }
  }

  function insertBlockIntoState(block) {
    const idx = blocks.findIndex(b => b.position > block.position);
    if (idx === -1) {
      blocks.push(block);
    } else {
      blocks.splice(idx, 0, block);
    }
  }

  function focusBlock(blockId) {
    const el = blocksContainer.querySelector(`[contenteditable][data-block-id="${blockId}"]`);
    if (!el) return;
    el.focus();
    try {
      const range = document.createRange();
      const sel = window.getSelection();
      range.selectNodeContents(el);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    } catch (_) { /* seguro ignorar */ }
  }

  // ── Block actions ────────────────────────────────────────
  async function onBlockActionClick(e) {
    const btn    = e.currentTarget;
    const action = btn.dataset.action;
    const blockEl = btn.closest('.caderno-block');
    if (!blockEl) return;
    const blockId = parseInt(blockEl.dataset.blockId, 10);

    if (action === 'delete')     await deleteBlock(blockId);
    else if (action === 'up')    await moveBlock(blockId, 'up');
    else if (action === 'down')  await moveBlock(blockId, 'down');
  }

  async function deleteBlock(blockId) {
    blocks = blocks.filter(b => b.id !== blockId);
    renderAllBlocks();

    try {
      await apiFetch(`${CFG.apiBlocksUrl}/${blockId}`, { method: 'DELETE' });
    } catch (err) {
      console.warn('[caderno] Falha ao deletar bloco', blockId, err);
      await loadBlocks();
    }
  }

  async function moveBlock(blockId, direction) {
    const idx = blocks.findIndex(b => b.id === blockId);
    if (idx === -1) return;

    const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (swapIdx < 0 || swapIdx >= blocks.length) return;

    const posA = blocks[idx].position;
    const posB = blocks[swapIdx].position;

    const movedBlock   = blocks[idx];
    const swappedBlock = blocks[swapIdx];

    movedBlock.position   = posB;
    swappedBlock.position = posA;
    blocks.sort((a, b) => a.position - b.position || a.id - b.id);
    renderAllBlocks();

    try {
      await Promise.all([
        apiFetch(`${CFG.apiBlocksUrl}/${movedBlock.id}`,   { method: 'PATCH', body: JSON.stringify({ position: posB }) }),
        apiFetch(`${CFG.apiBlocksUrl}/${swappedBlock.id}`, { method: 'PATCH', body: JSON.stringify({ position: posA }) }),
      ]);
    } catch (err) {
      console.warn('[caderno] Falha ao mover bloco', err);
    }
  }

  // ── Slash menu ───────────────────────────────────────────
  function openSlashMenu(editorEl, blockId) {
    slashTargetBlockId = blockId;
    slashMenuActiveIdx = -1;

    const rect = editorEl.getBoundingClientRect();
    slashMenu.style.top  = `${rect.bottom + window.scrollY + 4}px`;
    slashMenu.style.left = `${rect.left  + window.scrollX}px`;
    slashMenu.hidden = false;
    updateSlashMenuActive();
  }

  function closeSlashMenu() {
    slashMenu.hidden = true;
    slashTargetBlockId = null;
    slashMenuActiveIdx = -1;
  }

  function updateSlashMenuActive() {
    const items = slashMenuList.querySelectorAll('.slash-menu-item');
    items.forEach((item, i) => item.classList.toggle('is-active', i === slashMenuActiveIdx));
  }

  function handleSlashMenuNavigation(e) {
    if (slashMenu.hidden) return;
    const items = slashMenuList.querySelectorAll('.slash-menu-item');
    if (!items.length) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      slashMenuActiveIdx = (slashMenuActiveIdx + 1) % items.length;
      updateSlashMenuActive();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      slashMenuActiveIdx = (slashMenuActiveIdx - 1 + items.length) % items.length;
      updateSlashMenuActive();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (slashMenuActiveIdx >= 0) items[slashMenuActiveIdx].click();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeSlashMenu();
    }
  }

  // ── Seleção no menu slash ────────────────────────────────
  function onSlashMenuItemClick(e) {
    const item = e.currentTarget;
    const type = item.dataset.type;
    const savedTargetId = slashTargetBlockId;
    closeSlashMenu();

    if (!savedTargetId && savedTargetId !== 0) return;

    const editorEl = blocksContainer.querySelector(
      `[contenteditable][data-block-id="${savedTargetId}"]`
    );
    if (editorEl) {
      editorEl.textContent = '';
      saveBlockContent(savedTargetId, '');
    }

    if (type === 'text') return;

    if (type === 'nota') {
      convertBlockToNota(savedTargetId);
      return;
    }

    openSearchModal(type, savedTargetId);
  }

  async function convertBlockToNota(blockId) {
    const block = blocks.find(b => b.id === blockId);
    const position = block ? block.position : null;
    await deleteBlock(blockId);
    const newBlock = await createBlock({
      block_type: 'nota',
      content: '',
      position: position || undefined,
    });
    if (newBlock) focusBlock(newBlock.id);
  }

  // ── Modal de busca ───────────────────────────────────────
  const SEARCH_TYPE_META = {
    project: { title: 'Buscar Projeto', apiKey: 'projects', iconClass: 'fas fa-folder',       iconColor: 'var(--ds-color-primary-600)' },
    etapa:   { title: 'Buscar Etapa',   apiKey: 'stages',   iconClass: 'fas fa-tasks',         iconColor: '#16a34a' },
    tarefa:  { title: 'Buscar Tarefa',  apiKey: 'tasks',    iconClass: 'fas fa-check-square',  iconColor: '#7c3aed' },
  };

  // Mapeamento do tipo da API para a classe CSS do ícone no resultado
  const RESULT_ICON_META = {
    project: { cssKey: 'project', iconClass: 'fas fa-folder' },
    stage:   { cssKey: 'stage',   iconClass: 'fas fa-tasks' },
    task:    { cssKey: 'task',    iconClass: 'fas fa-check-square' },
  };

  function openSearchModal(type, sourceBlockId) {
    const meta = SEARCH_TYPE_META[type];
    if (!meta) return;

    searchPendingType     = type;
    searchPendingPosition = null;

    const sourceBlock = blocks.find(b => b.id === sourceBlockId);
    if (sourceBlock) searchPendingPosition = sourceBlock.position;

    // textContent é seguro aqui (sem HTML)
    searchModalTitle.textContent = meta.title;

    // Constrói ícone via DOM para evitar innerHTML com dados externos
    searchModalIcon.textContent = '';
    const iconEl = document.createElement('i');
    iconEl.className = meta.iconClass;
    iconEl.style.color = meta.iconColor;
    searchModalIcon.appendChild(iconEl);

    searchInput.value = '';
    searchResults.textContent = '';

    // Estado inicial via DOM
    const emptyDiv = document.createElement('div');
    emptyDiv.className = 'caderno-search-empty';
    const ico = document.createElement('i');
    ico.className = 'fas fa-search';
    const span = document.createElement('span');
    span.textContent = 'Digite ao menos 2 caracteres.';
    emptyDiv.appendChild(ico);
    emptyDiv.appendChild(span);
    searchResults.appendChild(emptyDiv);

    searchBackdrop.hidden = false;
    searchModal.hidden    = false;
    searchInput.focus();
  }

  function closeSearchModal() {
    searchModal.hidden    = true;
    searchBackdrop.hidden = true;
    searchPendingType     = null;
    searchPendingPosition = null;
    searchInput.value     = '';
    searchResults.textContent = '';
  }

  function onSearchInput() {
    clearTimeout(searchDebounceTimer);
    const q = searchInput.value.trim();
    if (q.length < 2) {
      setSearchState('Digite ao menos 2 caracteres.');
      return;
    }
    setSearchLoading();
    searchDebounceTimer = setTimeout(() => performSearch(q), 280);
  }

  function setSearchState(msg) {
    searchResults.textContent = '';
    const div = document.createElement('div');
    div.className = 'caderno-search-empty';
    const ico = document.createElement('i');
    ico.className = 'fas fa-search';
    const span = document.createElement('span');
    span.textContent = msg;
    div.appendChild(ico);
    div.appendChild(span);
    searchResults.appendChild(div);
  }

  function setSearchLoading() {
    searchResults.textContent = '';
    const div = document.createElement('div');
    div.className = 'caderno-loading';
    const spinner = document.createElement('div');
    spinner.className = 'caderno-spinner';
    const span = document.createElement('span');
    span.textContent = 'Buscando...';
    div.appendChild(spinner);
    div.appendChild(span);
    searchResults.appendChild(div);
  }

  async function performSearch(q) {
    const meta = SEARCH_TYPE_META[searchPendingType];
    if (!meta) return;

    try {
      const url = `${CFG.apiBuscarUrl}?q=${encodeURIComponent(q)}&limit=8`;
      const res = await apiFetch(url);
      if (!res.ok) throw new Error('API error');
      const data = await res.json();
      const items = (data.results || {})[meta.apiKey] || [];
      renderSearchResults(items);
    } catch (err) {
      console.warn('[caderno] Falha na busca', err);
      setSearchState('Erro ao buscar. Tente novamente.');
    }
  }

  function renderSearchResults(items) {
    searchResults.textContent = '';

    if (!items.length) {
      setSearchState('Nenhum resultado encontrado.');
      return;
    }

    items.forEach(item => {
      const iconMeta = RESULT_ICON_META[item.type] || { cssKey: item.type, iconClass: 'fas fa-circle' };
      const refId    = extractIdFromUrl(item.url);
      const safeUrl  = isSafeUrl(item.url) ? item.url : null;

      const div = document.createElement('div');
      div.className = 'caderno-search-result-item';
      div.setAttribute('role', 'option');
      div.setAttribute('tabindex', '-1');
      if (refId !== null) div.dataset.refId  = String(refId);
      if (safeUrl)        div.dataset.refUrl = safeUrl;

      const iconWrap = document.createElement('span');
      iconWrap.className = `caderno-search-result-icon caderno-search-result-icon--${iconMeta.cssKey}`;
      const iconEl = document.createElement('i');
      iconEl.className = iconMeta.iconClass;
      iconWrap.appendChild(iconEl);

      const body = document.createElement('span');
      body.className = 'caderno-search-result-body';

      const titleEl = document.createElement('span');
      titleEl.className = 'caderno-search-result-title';
      titleEl.textContent = item.title || item.display_title || '—';

      body.appendChild(titleEl);

      if (item.subtitle) {
        const subEl = document.createElement('span');
        subEl.className = 'caderno-search-result-sub';
        subEl.textContent = item.subtitle;
        body.appendChild(subEl);
      }

      div.appendChild(iconWrap);
      div.appendChild(body);
      div.addEventListener('click', onSearchResultClick);
      searchResults.appendChild(div);
    });
  }

  function extractIdFromUrl(url) {
    if (!url || typeof url !== 'string') return null;
    const matches = url.match(/\/(\d+)/g);
    if (!matches || !matches.length) return null;
    const id = parseInt(matches[matches.length - 1].replace('/', ''), 10);
    return Number.isFinite(id) && id > 0 ? id : null;
  }

  async function onSearchResultClick(e) {
    const el = e.currentTarget;
    const refId = parseInt(el.dataset.refId, 10);
    if (!refId || !Number.isFinite(refId)) return;

    const type         = searchPendingType;
    const position     = searchPendingPosition;
    const triggerBlockId = slashTargetBlockId;
    closeSearchModal();

    if (!type) return;

    // Remove o bloco de texto gatilho se estava vazio
    if (triggerBlockId) {
      const triggerBlock = blocks.find(b => b.id === triggerBlockId);
      if (triggerBlock && triggerBlock.block_type === 'text' && !(triggerBlock.content || '').trim()) {
        await deleteBlock(triggerBlockId);
      }
    }

    await createBlock({
      block_type:   type,
      reference_id: refId,
      content:      '',
      position:     position || undefined,
    });
  }

  // ── Carregar blocos ──────────────────────────────────────
  async function loadBlocks() {
    setBlocksLoading();
    try {
      const res = await apiFetch(CFG.apiBlocksUrl);
      if (!res.ok) throw new Error('API error');
      const data = await res.json();
      blocks = data.blocks || [];
      renderAllBlocks();
    } catch (err) {
      console.warn('[caderno] Falha ao carregar blocos', err);
      blocksContainer.textContent = '';
      const div = document.createElement('div');
      div.className = 'caderno-loading';
      div.style.color = '#dc2626';
      const ico = document.createElement('i');
      ico.className = 'fas fa-exclamation-circle';
      const span = document.createElement('span');
      span.textContent = ' Erro ao carregar o caderno.';
      div.appendChild(ico);
      div.appendChild(span);
      blocksContainer.appendChild(div);
    }
  }

  function setBlocksLoading() {
    blocksContainer.textContent = '';
    const div = document.createElement('div');
    div.className = 'caderno-loading';
    const spinner = document.createElement('div');
    spinner.className = 'caderno-spinner';
    const span = document.createElement('span');
    span.textContent = 'Carregando...';
    div.appendChild(spinner);
    div.appendChild(span);
    blocksContainer.appendChild(div);
  }

  // ── Zona de adição ───────────────────────────────────────
  async function onAddZoneInteract() {
    // Se já existe um bloco de texto vazio (ao final), apenas foca nele
    for (let i = blocks.length - 1; i >= 0; i--) {
      const b = blocks[i];
      if (b.block_type === 'text' && !(b.content || '').trim()) {
        focusBlock(b.id);
        return;
      }
    }
    await createBlock({ block_type: 'text', content: '' });
  }

  // ── Expandir papel (incremental, sem recolher) ──────────
  const EXPAND_STEP_PX = 500;

  function expandPaper() {
    if (!paper) return;
    const current = parseInt(paper.style.minHeight, 10) || paper.offsetHeight;
    paper.style.minHeight = (current + EXPAND_STEP_PX) + 'px';
  }

  // ── Inicialização ────────────────────────────────────────
  function init() {
    renderDate();
    loadBlocks();

    addZone.addEventListener('click', onAddZoneInteract);
    addZone.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') onAddZoneInteract();
    });

    if (emptyHint) {
      emptyHint.addEventListener('click', onAddZoneInteract);
    }

    if (expandZone) {
      expandZone.addEventListener('click', expandPaper);
    }

    slashMenuList.querySelectorAll('.slash-menu-item').forEach(item => {
      item.addEventListener('click', onSlashMenuItemClick);
    });

    document.addEventListener('keydown', handleSlashMenuNavigation);

    document.addEventListener('click', e => {
      if (!slashMenu.contains(e.target) && !e.target.closest('[contenteditable]')) {
        closeSlashMenu();
      }
    });

    searchInput.addEventListener('input', onSearchInput);
    searchModalClose.addEventListener('click', closeSearchModal);
    searchBackdrop.addEventListener('click', closeSearchModal);
    searchModal.addEventListener('keydown', e => {
      if (e.key === 'Escape') closeSearchModal();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
