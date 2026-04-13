/**
 * caderno.js — editor do Meu Caderno com layout em widgets persistidos.
 */
(function () {
  'use strict';

  const CFG = window.__CADERNO_CONFIG__ || {};

  const blocksContainer = document.getElementById('cadernoBlocks');
  const emptyHint = document.getElementById('cadernoEmptyHint');
  const addZone = document.getElementById('cadernoAddZone');
  const dateEl = document.getElementById('cadernoDate');
  const paper = document.getElementById('cadernoPaper');
  const canvasWrap = document.getElementById('cadernoCanvasWrap');
  const expandZone = document.getElementById('cadernoExpandZone');
  const expandZoneLabel = document.getElementById('cadernoExpandZoneLabel');

  const slashMenu = document.getElementById('slashMenu');
  const slashMenuList = document.getElementById('slashMenuList');

  const searchBackdrop = document.getElementById('cadernoSearchBackdrop');
  const searchModal = document.getElementById('cadernoSearchModal');
  const searchModalTitle = document.getElementById('cadernoSearchModalTitle');
  const searchModalIcon = document.getElementById('cadernoSearchModalIcon');
  const searchModalClose = document.getElementById('cadernoSearchModalClose');
  const searchInput = document.getElementById('cadernoSearchInput');
  const searchResults = document.getElementById('cadernoSearchResults');

  const GRID_COLUMNS = 12;
  const GRID_GAP_PX = 16;
  const GRID_ROW_HEIGHT = 36;
  const GRID_TRACK_HEIGHT = GRID_ROW_HEIGHT + GRID_GAP_PX;
  const MOBILE_BREAKPOINT = 960;
  const DESKTOP_BASE_CANVAS_MIN_HEIGHT = { min: 420, max: 560, ratio: 0.54 };
  const MOBILE_BASE_CANVAS_MIN_HEIGHT = { min: 280, max: 420, ratio: 0.42 };
  const EXPAND_STEP_PX = 320;
  const SLASH_MENU_OFFSET_PX = 10;
  const SLASH_MENU_VIEWPORT_GAP = 12;
  const DEFAULT_SIZE_PRESET = 'M';
  const DEFAULT_SHEET = { expand_steps: 0, max_expand_steps: 3 };
  const SIZE_PRESET_LAYOUTS = {
    P: { grid_w: 3, grid_h: 4 },
    M: { grid_w: 6, grid_h: 5 },
    G: { grid_w: 12, grid_h: 6 },
  };

  let blocks = [];
  let sheet = { ...DEFAULT_SHEET };
  let activeBlockId = null;
  let slashTargetBlockId = null;
  let slashMenuActiveIdx = -1;
  let searchDebounceTimer = null;
  let searchPendingType = null;
  let searchPendingLayout = null;
  let dragState = null;
  let persistLayoutTimer = null;
  let measureAllTimer = null;
  const measureTimers = new Map();

  function escapeHtml(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#x27;');
  }

  function isSafeUrl(url) {
    if (!url || typeof url !== 'string') return false;
    const trimmed = url.trim();
    return /^\/[^/]/.test(trimmed) || trimmed === '/';
  }

  function safeHref(url) {
    return isSafeUrl(url) ? escapeHtml(url) : '#';
  }

  function renderDate() {
    if (!dateEl) return;
    const formatted = new Date().toLocaleDateString('pt-BR', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
    dateEl.textContent = formatted.charAt(0).toUpperCase() + formatted.slice(1);
  }

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

  function coerceInt(value, fallback, minimum, maximum) {
    const coerced = parseInt(value, 10);
    if (!Number.isFinite(coerced)) return fallback;
    let next = coerced;
    if (Number.isFinite(minimum)) next = Math.max(minimum, next);
    if (Number.isFinite(maximum)) next = Math.min(maximum, next);
    return next;
  }

  function normalizeSizePreset(value) {
    const preset = String(value || '').trim().toUpperCase();
    return SIZE_PRESET_LAYOUTS[preset] ? preset : DEFAULT_SIZE_PRESET;
  }

  function getPresetLayout(sizePreset) {
    const preset = normalizeSizePreset(sizePreset);
    return { ...SIZE_PRESET_LAYOUTS[preset] };
  }

  function normalizeBlock(rawBlock) {
    const block = { ...(rawBlock || {}) };
    const sizePreset = normalizeSizePreset(block.size_preset);
    const defaults = getPresetLayout(sizePreset);
    const gridW = coerceInt(block.grid_w, defaults.grid_w, 1, GRID_COLUMNS);
    const gridH = coerceInt(block.grid_h, defaults.grid_h, 1);
    return {
      ...block,
      content: block.content || '',
      size_preset: sizePreset,
      grid_x: coerceInt(block.grid_x, 0, 0, Math.max(0, GRID_COLUMNS - gridW)),
      grid_y: coerceInt(block.grid_y, 0, 0),
      grid_w: gridW,
      grid_h: gridH,
      position: Number.isFinite(Number(block.position)) ? Number(block.position) : 0,
    };
  }

  function cloneBlocks(sourceBlocks) {
    return sourceBlocks.map(block => ({ ...block }));
  }

  function sortBlocksForLayout(sourceBlocks) {
    return [...sourceBlocks].sort((a, b) => (
      a.grid_y - b.grid_y ||
      a.grid_x - b.grid_x ||
      a.id - b.id
    ));
  }

  function assignSequentialPositions(sourceBlocks) {
    return sortBlocksForLayout(sourceBlocks).map((block, index) => ({
      ...block,
      position: (index + 1) * 1000,
    }));
  }

  function occupyCells(occupied, gridX, gridY, gridW, gridH) {
    for (let y = 0; y < gridH; y += 1) {
      for (let x = 0; x < gridW; x += 1) {
        occupied.add(`${gridX + x}:${gridY + y}`);
      }
    }
  }

  function slotFits(occupied, gridX, gridY, gridW, gridH) {
    for (let y = 0; y < gridH; y += 1) {
      for (let x = 0; x < gridW; x += 1) {
        if (occupied.has(`${gridX + x}:${gridY + y}`)) return false;
      }
    }
    return true;
  }

  function buildPreferredXs(startX, maxX) {
    const values = [];
    for (let delta = 0; delta <= maxX; delta += 1) {
      const left = startX - delta;
      const right = startX + delta;
      if (left >= 0 && !values.includes(left)) values.push(left);
      if (right <= maxX && !values.includes(right)) values.push(right);
    }
    return values;
  }

  function findSlotFrom(occupied, gridW, gridH, preferredX, preferredY) {
    const maxX = Math.max(0, GRID_COLUMNS - gridW);
    const startX = coerceInt(preferredX, 0, 0, maxX);
    const startY = coerceInt(preferredY, 0, 0);

    for (let y = startY; y < startY + 2000; y += 1) {
      const xCandidates = y === startY
        ? buildPreferredXs(startX, maxX)
        : Array.from({ length: maxX + 1 }, (_, idx) => idx);
      for (const x of xCandidates) {
        if (slotFits(occupied, x, y, gridW, gridH)) {
          return { grid_x: x, grid_y: y };
        }
      }
    }
    return { grid_x: 0, grid_y: startY };
  }

  function normalizeLayout(sourceBlocks, preferredBlockId) {
    const normalizedBlocks = sourceBlocks.map(normalizeBlock);
    const ordered = sortBlocksForLayout(normalizedBlocks);
    if (preferredBlockId != null) {
      ordered.sort((a, b) => {
        if (a.id === preferredBlockId) return -1;
        if (b.id === preferredBlockId) return 1;
        return a.grid_y - b.grid_y || a.grid_x - b.grid_x || a.id - b.id;
      });
    }

    const occupied = new Set();
    const laidOut = ordered.map(block => {
      const slot = findSlotFrom(
        occupied,
        block.grid_w,
        block.grid_h,
        block.grid_x,
        block.grid_y,
      );
      const nextBlock = {
        ...block,
        grid_x: slot.grid_x,
        grid_y: slot.grid_y,
      };
      occupyCells(occupied, nextBlock.grid_x, nextBlock.grid_y, nextBlock.grid_w, nextBlock.grid_h);
      return nextBlock;
    });

    return assignSequentialPositions(laidOut);
  }

  function setBlocks(nextBlocks, preferredBlockId) {
    blocks = normalizeLayout(nextBlocks, preferredBlockId);
  }

  function getBlockById(blockId) {
    return blocks.find(block => block.id === blockId) || null;
  }

  function findBlockElement(blockId) {
    return blocksContainer.querySelector(`.caderno-block[data-block-id="${blockId}"]`);
  }

  function findBlockEditor(blockId) {
    return blocksContainer.querySelector(`[contenteditable][data-block-id="${blockId}"]`);
  }

  function getEditorText(editorEl) {
    return String(editorEl ? (editorEl.textContent || '') : '')
      .replace(/\u200b/g, '')
      .replace(/\u00a0/g, ' ');
  }

  function isSlashTriggerText(text) {
    return String(text || '').replace(/\s/g, '') === '/';
  }

  function syncSlashMenuState() {
    const isMenuOpen = !!slashMenu && !slashMenu.hidden && slashTargetBlockId != null;
    blocksContainer.querySelectorAll('.caderno-block').forEach(blockEl => {
      const blockId = coerceInt(blockEl.dataset.blockId, null);
      blockEl.classList.toggle('is-slash-menu-open', isMenuOpen && blockId === slashTargetBlockId);
    });
  }

  function syncEditorInteractionState(editorEl) {
    const blockEl = editorEl ? editorEl.closest('.caderno-block') : null;
    if (!blockEl) return;
    const text = getEditorText(editorEl);
    blockEl.classList.toggle('is-editor-empty', text.trim() === '');
    blockEl.classList.toggle('is-slash-trigger', isSlashTriggerText(text));
  }

  function syncAllEditorInteractionStates() {
    blocksContainer.querySelectorAll('[contenteditable]').forEach(syncEditorInteractionState);
    syncSlashMenuState();
  }

  function getBlockCurrentText(blockId) {
    const editorEl = findBlockEditor(blockId);
    if (editorEl) return getEditorText(editorEl);
    const block = getBlockById(blockId);
    return block ? String(block.content || '') : '';
  }

  function findReusableDraftTextBlock() {
    for (let index = blocks.length - 1; index >= 0; index -= 1) {
      const block = blocks[index];
      if (block.block_type !== 'text') continue;
      if (!getBlockCurrentText(block.id).trim()) return block;
    }
    return null;
  }

  function layoutsDiffer(nextBlocks, currentBlocks) {
    if (nextBlocks.length !== currentBlocks.length) return true;
    const currentMap = new Map(currentBlocks.map(block => [block.id, block]));
    return nextBlocks.some(block => {
      const current = currentMap.get(block.id);
      if (!current) return true;
      return (
        block.position !== current.position ||
        block.size_preset !== current.size_preset ||
        block.grid_x !== current.grid_x ||
        block.grid_y !== current.grid_y ||
        block.grid_w !== current.grid_w ||
        block.grid_h !== current.grid_h
      );
    });
  }

  function isDesktopLayout() {
    return window.innerWidth >= MOBILE_BREAKPOINT;
  }

  function getFallbackCaretRect(editorEl) {
    const rect = editorEl.getBoundingClientRect();
    const lineHeight = parseFloat(window.getComputedStyle(editorEl).lineHeight) || 24;
    return {
      top: rect.top,
      bottom: rect.top + lineHeight,
      left: rect.left,
      right: rect.left,
      width: 0,
      height: lineHeight,
    };
  }

  function getEditorCaretRect(editorEl) {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) return getFallbackCaretRect(editorEl);

    const activeRange = selection.getRangeAt(0);
    if (!editorEl.contains(activeRange.startContainer)) return getFallbackCaretRect(editorEl);

    const caretRange = activeRange.cloneRange();
    caretRange.collapse(false);

    const directRect = caretRange.getBoundingClientRect();
    if (directRect && (directRect.height || directRect.width)) return directRect;

    const marker = document.createElement('span');
    marker.textContent = '\u200b';
    marker.setAttribute('aria-hidden', 'true');
    caretRange.insertNode(marker);

    const markerRect = marker.getBoundingClientRect();
    const restoreRange = document.createRange();
    restoreRange.setStartAfter(marker);
    restoreRange.collapse(true);
    selection.removeAllRanges();
    selection.addRange(restoreRange);
    marker.remove();

    if (markerRect && (markerRect.height || markerRect.width)) return markerRect;
    return getFallbackCaretRect(editorEl);
  }

  function positionSlashMenu(editorEl) {
    if (!slashMenu || !editorEl) return;

    const anchorRect = getEditorCaretRect(editorEl);
    const menuRect = slashMenu.getBoundingClientRect();
    const shouldPlaceAbove = (
      (window.innerHeight - anchorRect.bottom) < (menuRect.height + SLASH_MENU_VIEWPORT_GAP) &&
      anchorRect.top > (menuRect.height + SLASH_MENU_VIEWPORT_GAP)
    );
    const desiredTop = shouldPlaceAbove
      ? anchorRect.top - menuRect.height - SLASH_MENU_OFFSET_PX
      : anchorRect.bottom + SLASH_MENU_OFFSET_PX;
    const desiredLeft = anchorRect.left;
    const maxTop = Math.max(SLASH_MENU_VIEWPORT_GAP, window.innerHeight - menuRect.height - SLASH_MENU_VIEWPORT_GAP);
    const maxLeft = Math.max(SLASH_MENU_VIEWPORT_GAP, window.innerWidth - menuRect.width - SLASH_MENU_VIEWPORT_GAP);
    const top = Math.min(Math.max(desiredTop, SLASH_MENU_VIEWPORT_GAP), maxTop);
    const left = Math.min(Math.max(desiredLeft, SLASH_MENU_VIEWPORT_GAP), maxLeft);

    slashMenu.style.top = `${Math.round(top)}px`;
    slashMenu.style.left = `${Math.round(left)}px`;
    slashMenu.dataset.side = shouldPlaceAbove ? 'top' : 'bottom';
  }

  function repositionOpenSlashMenu() {
    if (!slashMenu || slashMenu.hidden || slashTargetBlockId == null) return;
    const editorEl = findBlockEditor(slashTargetBlockId);
    if (!editorEl) {
      closeSlashMenu();
      return;
    }
    positionSlashMenu(editorEl);
  }

  function getCanvasLayoutFromPoint(clientX, clientY, sizePreset = DEFAULT_SIZE_PRESET) {
    if (!canvasWrap || !blocksContainer || !isDesktopLayout()) return null;

    const defaults = getPresetLayout(sizePreset);
    const canvasRect = canvasWrap.getBoundingClientRect();
    const containerRect = blocksContainer.getBoundingClientRect();
    const usableWidth = Math.max(containerRect.width, 1);
    const columnWidth = (usableWidth - (GRID_GAP_PX * (GRID_COLUMNS - 1))) / GRID_COLUMNS;
    if (!Number.isFinite(columnWidth) || columnWidth <= 0) return null;

    const relativeX = Math.max(0, Math.min(clientX - containerRect.left, usableWidth - 1));
    const relativeY = Math.max(0, clientY - canvasRect.top);
    const desiredGridX = coerceInt(
      Math.floor(relativeX / (columnWidth + GRID_GAP_PX)),
      0,
      0,
      Math.max(0, GRID_COLUMNS - defaults.grid_w),
    );
    const desiredGridY = coerceInt(
      Math.floor(relativeY / GRID_TRACK_HEIGHT),
      0,
      0,
    );

    return {
      size_preset: sizePreset,
      grid_x: desiredGridX,
      grid_y: desiredGridY,
      grid_w: defaults.grid_w,
      grid_h: defaults.grid_h,
    };
  }

  function getBaseCanvasMinHeight() {
    const baseConfig = isDesktopLayout()
      ? DESKTOP_BASE_CANVAS_MIN_HEIGHT
      : MOBILE_BASE_CANVAS_MIN_HEIGHT;
    const viewportHeight = Math.round(window.innerHeight * baseConfig.ratio);
    return coerceInt(viewportHeight, baseConfig.max, baseConfig.min, baseConfig.max);
  }

  function applyCanvasSizing() {
    if (!canvasWrap) return;
    const expandSteps = coerceInt(sheet.expand_steps, 0, 0, sheet.max_expand_steps || DEFAULT_SHEET.max_expand_steps);
    const baseCanvasMinHeight = getBaseCanvasMinHeight();
    canvasWrap.style.minHeight = `${baseCanvasMinHeight + (expandSteps * EXPAND_STEP_PX)}px`;
  }

  function updateExpandControl() {
    if (!expandZone || !expandZoneLabel) return;
    const maxExpandSteps = sheet.max_expand_steps || DEFAULT_SHEET.max_expand_steps;
    const isMaxed = sheet.expand_steps >= maxExpandSteps;
    expandZone.disabled = isMaxed;
    expandZone.setAttribute('aria-disabled', isMaxed ? 'true' : 'false');
    expandZoneLabel.textContent = isMaxed ? 'Limite da folha atingido' : 'Expandir página';
  }

  async function saveSheetExpandSteps(expandSteps) {
    try {
      const response = await apiFetch(CFG.apiStateUrl, {
        method: 'PATCH',
        body: JSON.stringify({ expand_steps: expandSteps }),
      });
      if (!response.ok) throw new Error('API error');
      const payload = await response.json();
      sheet = { ...sheet, ...(payload.sheet || {}) };
      applyCanvasSizing();
      updateExpandControl();
    } catch (err) {
      console.warn('[caderno] Falha ao salvar expansão da folha', err);
      await loadBlocks();
    }
  }

  function buildBlockStyleAttr(block) {
    return [
      `--caderno-grid-column:${block.grid_x + 1}`,
      `--caderno-grid-span:${block.grid_w}`,
      `--caderno-grid-row:${block.grid_y + 1}`,
      `--caderno-grid-height:${block.grid_h}`,
    ].join(';');
  }

  const STATUS_LABELS = {
    nao_iniciada: 'Não iniciada',
    em_andamento: 'Em andamento',
    para_validacao: 'Para validação',
    para_ajustes: 'Para ajustes',
    finalizada: 'Finalizada',
  };

  const PRIORIDADE_LABELS = {
    urgente: 'Urgente',
    alta: 'Alta',
    media: 'Média',
    baixa: 'Baixa',
  };

  const VALID_STATUSES = new Set(Object.keys(STATUS_LABELS));
  const VALID_PRIOS = new Set(Object.keys(PRIORIDADE_LABELS));

  function statusBadge(status) {
    const safeStatus = VALID_STATUSES.has(status) ? status : 'nao_iniciada';
    return `<span class="caderno-task-status caderno-task-status--${safeStatus}">${escapeHtml(STATUS_LABELS[safeStatus] || safeStatus)}</span>`;
  }

  function prioLabel(prio) {
    const safePrio = VALID_PRIOS.has(prio) ? prio : '';
    if (!safePrio) return '';
    return `<span class="caderno-prio caderno-prio--${safePrio}">${escapeHtml(PRIORIDADE_LABELS[safePrio])}</span>`;
  }

  function etapaStatusBadge(ref) {
    if (ref.done) return '<span class="caderno-etapa-status caderno-etapa-status--done"><i class="fas fa-check"></i> Concluída</span>';
    if (ref.iniciada) return '<span class="caderno-etapa-status caderno-etapa-status--iniciada"><i class="fas fa-spinner"></i> Em andamento</span>';
    return '<span class="caderno-etapa-status caderno-etapa-status--pendente"><i class="fas fa-clock"></i> Não iniciada</span>';
  }

  function formatDate(iso) {
    if (!iso || typeof iso !== 'string') return '';
    const parts = iso.split('T')[0].split('-');
    if (parts.length !== 3) return '';
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }

  function renderSizeToggle(block) {
    return ['P', 'M', 'G'].map(size => (
      `<button class="caderno-size-btn${block.size_preset === size ? ' is-active' : ''}" data-action="size" data-size="${size}" type="button" aria-label="Tamanho ${size}">
        <span>${size}</span>
      </button>`
    )).join('');
  }

  function renderToolbar(block) {
    return `
      <div class="caderno-block-toolbar">
        <button class="caderno-block-handle" type="button" data-action="drag" aria-label="Mover bloco">
          <i class="fas fa-grip-lines"></i>
        </button>
        <div class="caderno-size-toggle" role="group" aria-label="Tamanho do bloco">
          ${renderSizeToggle(block)}
        </div>
        <button class="caderno-block-btn caderno-block-btn--delete" type="button" data-action="delete" aria-label="Remover bloco">
          <i class="fas fa-trash-alt"></i>
        </button>
      </div>
    `;
  }

  function renderTextBlock(block) {
    return `
      <div class="caderno-widget-body caderno-widget-body--text">
        <div
          class="caderno-text-editor"
          contenteditable="true"
          data-placeholder="Escreva algo... (/ para inserir bloco)"
          data-block-id="${block.id}"
          spellcheck="false"
        >${escapeHtml(block.content)}</div>
      </div>
    `;
  }

  function renderNoteBlock(block) {
    return `
      <div class="caderno-widget-body caderno-widget-body--note">
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
      </div>
    `;
  }

  function renderNullRef(block, label) {
    return `
      <div class="caderno-widget-body">
        <div class="caderno-ref-null">
          <i class="fas fa-unlink"></i>
          <span>${escapeHtml(label)}</span>
        </div>
      </div>
    `;
  }

  function renderProjectBlock(block) {
    const ref = block.ref_data;
    if (!ref) return renderNullRef(block, 'Projeto removido');
    const pct = ref.total_etapas > 0 ? Math.round((ref.etapas_concluidas / ref.total_etapas) * 100) : 0;
    return `
      <div class="caderno-widget-body">
        <a href="${safeHref(ref.url)}" class="caderno-ref-card" target="_blank" rel="noopener noreferrer" draggable="false">
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
              </div>
            ` : ''}
          </span>
          <span class="caderno-ref-card-link-hint"><i class="fas fa-external-link-alt"></i></span>
        </a>
      </div>
    `;
  }

  function renderEtapaBlock(block) {
    const ref = block.ref_data;
    if (!ref) return renderNullRef(block, 'Etapa removida');
    const dateRange = [formatDate(ref.data_inicio), formatDate(ref.data_fim)].filter(Boolean).join(' → ');
    return `
      <div class="caderno-widget-body">
        <a href="${safeHref(ref.url)}" class="caderno-ref-card" target="_blank" rel="noopener noreferrer" draggable="false">
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
      </div>
    `;
  }

  function renderTaskBlock(block) {
    const ref = block.ref_data;
    if (!ref) return renderNullRef(block, 'Tarefa removida');
    return `
      <div class="caderno-widget-body">
        <a href="${safeHref(ref.url)}" class="caderno-ref-card" target="_blank" rel="noopener noreferrer" draggable="false">
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
      </div>
    `;
  }

  function renderBlockBody(block) {
    if (block.block_type === 'text') return renderTextBlock(block);
    if (block.block_type === 'nota') return renderNoteBlock(block);
    if (block.block_type === 'project') return renderProjectBlock(block);
    if (block.block_type === 'etapa') return renderEtapaBlock(block);
    if (block.block_type === 'tarefa') return renderTaskBlock(block);
    return '';
  }

  function renderBlockHTML(block) {
    const classes = [
      'caderno-block',
      `caderno-block--${block.block_type}`,
      activeBlockId === block.id ? 'is-active' : '',
    ].filter(Boolean).join(' ');

    return `
      <div class="${classes}" data-block-id="${block.id}" data-size-preset="${block.size_preset}" role="listitem" tabindex="-1" style="${buildBlockStyleAttr(block)}">
        <div class="caderno-widget">
          ${renderToolbar(block)}
          ${renderBlockBody(block)}
        </div>
      </div>
    `;
  }

  function updateEmptyHint() {
    if (!emptyHint) return;
    emptyHint.classList.toggle('is-hidden', blocks.length > 0);
  }

  function syncActiveBlockState() {
    blocksContainer.querySelectorAll('.caderno-block').forEach(blockEl => {
      const blockId = coerceInt(blockEl.dataset.blockId, null);
      blockEl.classList.toggle('is-active', blockId === activeBlockId);
    });
  }

  function renderAllBlocks() {
    blocksContainer.innerHTML = sortBlocksForLayout(blocks).map(renderBlockHTML).join('');
    bindBlockEvents();
    updateEmptyHint();
    syncActiveBlockState();
    syncAllEditorInteractionStates();
    scheduleMeasureAllBlocks();
  }

  function setActiveBlock(blockId) {
    activeBlockId = blockId;
    syncActiveBlockState();
  }

  function focusBlock(blockId) {
    const editorEl = findBlockEditor(blockId);
    if (editorEl) {
      editorEl.focus();
      try {
        const range = document.createRange();
        const selection = window.getSelection();
        range.selectNodeContents(editorEl);
        range.collapse(false);
        selection.removeAllRanges();
        selection.addRange(range);
      } catch (_) {
        /* noop */
      }
      return;
    }
    const blockEl = findBlockElement(blockId);
    if (blockEl) blockEl.focus();
  }

  function getMinimumGridHeight(block) {
    return block.block_type === 'text' || block.block_type === 'nota' ? 2 : 1;
  }

  function measureRequiredGridHeight(blockId) {
    const block = getBlockById(blockId);
    const blockEl = findBlockElement(blockId);
    if (!block || !blockEl || !isDesktopLayout()) return null;
    const measureRoot = blockEl.querySelector(
      '.caderno-text-editor, .caderno-nota-card, .caderno-ref-card, .caderno-ref-null'
    );
    const measuredHeight = Math.max(
      measureRoot ? measureRoot.scrollHeight : 0,
      Math.ceil(measureRoot ? measureRoot.getBoundingClientRect().height : blockEl.getBoundingClientRect().height),
    );
    const requiredRows = Math.ceil((measuredHeight + GRID_GAP_PX) / GRID_TRACK_HEIGHT);
    return Math.max(getMinimumGridHeight(block), requiredRows);
  }

  function persistLayoutNow() {
    clearTimeout(persistLayoutTimer);
    persistLayoutTimer = null;
    if (!blocks.length) return;

    apiFetch(CFG.apiBlocksReorder, {
      method: 'POST',
      body: JSON.stringify({
        items: sortBlocksForLayout(blocks).map(block => ({
          id: block.id,
          position: block.position,
          size_preset: block.size_preset,
          grid_x: block.grid_x,
          grid_y: block.grid_y,
          grid_w: block.grid_w,
          grid_h: block.grid_h,
        })),
      }),
    }).catch(async err => {
      console.warn('[caderno] Falha ao persistir layout', err);
      await loadBlocks();
    });
  }

  function schedulePersistLayout() {
    clearTimeout(persistLayoutTimer);
    persistLayoutTimer = setTimeout(persistLayoutNow, 160);
  }

  function scheduleMeasureBlock(blockId, delay = 90) {
    const existingTimer = measureTimers.get(blockId);
    if (existingTimer) clearTimeout(existingTimer);
    const timer = setTimeout(() => {
      measureTimers.delete(blockId);
      const nextGridH = measureRequiredGridHeight(blockId);
      if (nextGridH == null) return;
      const block = getBlockById(blockId);
      if (!block || block.grid_h === nextGridH) return;
      const nextBlocks = cloneBlocks(blocks);
      const target = nextBlocks.find(item => item.id === blockId);
      if (!target) return;
      target.grid_h = nextGridH;
      const normalized = normalizeLayout(nextBlocks, blockId);
      if (!layoutsDiffer(normalized, blocks)) return;
      blocks = normalized;
      renderAllBlocks();
      schedulePersistLayout();
    }, delay);
    measureTimers.set(blockId, timer);
  }

  function scheduleMeasureAllBlocks() {
    clearTimeout(measureAllTimer);
    measureAllTimer = setTimeout(() => {
      if (!isDesktopLayout()) return;
      sortBlocksForLayout(blocks).forEach(block => scheduleMeasureBlock(block.id, 0));
    }, 30);
  }

  function autoResizeEditor(editorEl) {
    if (!editorEl) return;
    editorEl.style.height = 'auto';
    editorEl.style.height = `${editorEl.scrollHeight}px`;
  }

  async function saveBlockContent(blockId, content) {
    const block = getBlockById(blockId);
    if (!block || block.content === content) return;
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

  async function createBlock(data, options = {}) {
    try {
      const response = await apiFetch(CFG.apiBlocksCreate, {
        method: 'POST',
        body: JSON.stringify(data),
      });
      if (!response.ok) return null;
      const payload = await response.json();
      const block = normalizeBlock(payload.block);
      setBlocks([...blocks, block], block.id);
      renderAllBlocks();
      setActiveBlock(block.id);
      if (options.focus !== false) focusBlock(block.id);
      return block;
    } catch (err) {
      console.warn('[caderno] Falha ao criar bloco', err);
      return null;
    }
  }

  function moveDraftTextBlock(blockId, layout) {
    const nextBlocks = cloneBlocks(blocks);
    const target = nextBlocks.find(block => block.id === blockId);
    if (!target) return false;

    target.size_preset = layout.size_preset;
    target.grid_x = layout.grid_x;
    target.grid_y = layout.grid_y;
    target.grid_w = layout.grid_w;
    target.grid_h = layout.grid_h;

    const normalized = normalizeLayout(nextBlocks, blockId);
    if (!layoutsDiffer(normalized, blocks)) {
      renderAllBlocks();
      setActiveBlock(blockId);
      focusBlock(blockId);
      return true;
    }

    blocks = normalized;
    renderAllBlocks();
    setActiveBlock(blockId);
    focusBlock(blockId);
    schedulePersistLayout();
    return true;
  }

  async function createTextBlockAtPoint(clientX, clientY) {
    const layout = getCanvasLayoutFromPoint(clientX, clientY);
    if (!layout) {
      await createBlock({ block_type: 'text', content: '' });
      return;
    }

    const reusableDraft = findReusableDraftTextBlock();
    if (reusableDraft && moveDraftTextBlock(reusableDraft.id, layout)) {
      return;
    }

    await createBlock({
      block_type: 'text',
      content: '',
      ...layout,
    });
  }

  async function createTextBlockAfter(blockId) {
    const sourceBlock = getBlockById(blockId);
    if (!sourceBlock) return;
    const defaults = getPresetLayout(DEFAULT_SIZE_PRESET);
    await createBlock({
      block_type: 'text',
      content: '',
      size_preset: DEFAULT_SIZE_PRESET,
      grid_x: sourceBlock.grid_x,
      grid_y: sourceBlock.grid_y + sourceBlock.grid_h,
      grid_w: defaults.grid_w,
      grid_h: defaults.grid_h,
    });
  }

  async function deleteBlock(blockId) {
    blocks = blocks.filter(block => block.id !== blockId);
    if (activeBlockId === blockId) activeBlockId = null;
    renderAllBlocks();

    try {
      await apiFetch(`${CFG.apiBlocksUrl}/${blockId}`, { method: 'DELETE' });
      schedulePersistLayout();
    } catch (err) {
      console.warn('[caderno] Falha ao deletar bloco', blockId, err);
      await loadBlocks();
    }
  }

  function setSearchState(message) {
    searchResults.textContent = '';
    const wrapper = document.createElement('div');
    wrapper.className = 'caderno-search-empty';
    const icon = document.createElement('i');
    icon.className = 'fas fa-search';
    const label = document.createElement('span');
    label.textContent = message;
    wrapper.appendChild(icon);
    wrapper.appendChild(label);
    searchResults.appendChild(wrapper);
  }

  function setSearchLoading() {
    searchResults.textContent = '';
    const wrapper = document.createElement('div');
    wrapper.className = 'caderno-loading';
    const spinner = document.createElement('div');
    spinner.className = 'caderno-spinner';
    const label = document.createElement('span');
    label.textContent = 'Buscando...';
    wrapper.appendChild(spinner);
    wrapper.appendChild(label);
    searchResults.appendChild(wrapper);
  }

  function closeSearchModal() {
    searchModal.hidden = true;
    searchBackdrop.hidden = true;
    searchPendingType = null;
    searchPendingLayout = null;
    searchInput.value = '';
    searchResults.textContent = '';
  }

  const SEARCH_TYPE_META = {
    project: { title: 'Buscar Projeto', apiKey: 'projects', iconClass: 'fas fa-folder', iconColor: 'var(--ds-color-primary-600)' },
    etapa: { title: 'Buscar Etapa', apiKey: 'stages', iconClass: 'fas fa-tasks', iconColor: '#16a34a' },
    tarefa: { title: 'Buscar Tarefa', apiKey: 'tasks', iconClass: 'fas fa-check-square', iconColor: '#7c3aed' },
  };

  const RESULT_ICON_META = {
    project: { cssKey: 'project', iconClass: 'fas fa-folder' },
    stage: { cssKey: 'stage', iconClass: 'fas fa-tasks' },
    task: { cssKey: 'task', iconClass: 'fas fa-check-square' },
  };

  function openSearchModal(type, sourceBlockId) {
    const meta = SEARCH_TYPE_META[type];
    if (!meta) return;

    searchPendingType = type;
    const sourceBlock = getBlockById(sourceBlockId);
    const defaults = getPresetLayout(DEFAULT_SIZE_PRESET);
    searchPendingLayout = sourceBlock ? {
      position: sourceBlock.position,
      size_preset: DEFAULT_SIZE_PRESET,
      grid_x: sourceBlock.grid_x,
      grid_y: sourceBlock.grid_y,
      grid_w: defaults.grid_w,
      grid_h: defaults.grid_h,
    } : null;

    searchModalTitle.textContent = meta.title;
    searchModalIcon.textContent = '';
    const iconEl = document.createElement('i');
    iconEl.className = meta.iconClass;
    iconEl.style.color = meta.iconColor;
    searchModalIcon.appendChild(iconEl);

    setSearchState('Digite ao menos 2 caracteres.');
    searchInput.value = '';
    searchBackdrop.hidden = false;
    searchModal.hidden = false;
    searchInput.focus();
  }

  function openSlashMenu(editorEl, blockId) {
    if (!slashMenu || !editorEl || blockId == null) return;
    slashTargetBlockId = blockId;
    slashMenuActiveIdx = -1;
    slashMenu.hidden = false;
    syncSlashMenuState();
    positionSlashMenu(editorEl);
    requestAnimationFrame(() => {
      const activeEditor = findBlockEditor(blockId);
      if (activeEditor && !slashMenu.hidden && slashTargetBlockId === blockId) {
        positionSlashMenu(activeEditor);
      }
    });
    updateSlashMenuActive();
  }

  function closeSlashMenu() {
    if (!slashMenu) return;
    slashMenu.hidden = true;
    slashMenu.style.top = '';
    slashMenu.style.left = '';
    slashMenu.removeAttribute('data-side');
    slashTargetBlockId = null;
    slashMenuActiveIdx = -1;
    syncSlashMenuState();
  }

  function updateSlashMenuActive() {
    const items = slashMenuList.querySelectorAll('.slash-menu-item');
    items.forEach((item, index) => item.classList.toggle('is-active', index === slashMenuActiveIdx));
  }

  function handleSlashMenuNavigation(event) {
    if (slashMenu.hidden) return;
    const items = slashMenuList.querySelectorAll('.slash-menu-item');
    if (!items.length) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      slashMenuActiveIdx = (slashMenuActiveIdx + 1) % items.length;
      updateSlashMenuActive();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      slashMenuActiveIdx = (slashMenuActiveIdx - 1 + items.length) % items.length;
      updateSlashMenuActive();
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (slashMenuActiveIdx >= 0) items[slashMenuActiveIdx].click();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      closeSlashMenu();
    }
  }

  async function convertBlockToNota(blockId) {
    const block = getBlockById(blockId);
    if (!block) return;
    const layout = {
      position: block.position,
      size_preset: block.size_preset,
      grid_x: block.grid_x,
      grid_y: block.grid_y,
      grid_w: block.grid_w,
      grid_h: block.grid_h,
    };
    await deleteBlock(blockId);
    const newBlock = await createBlock({
      block_type: 'nota',
      content: '',
      ...layout,
    });
    if (newBlock) focusBlock(newBlock.id);
  }

  function extractIdFromUrl(url) {
    if (!url || typeof url !== 'string') return null;
    const matches = url.match(/\/(\d+)/g);
    if (!matches || !matches.length) return null;
    const id = parseInt(matches[matches.length - 1].replace('/', ''), 10);
    return Number.isFinite(id) && id > 0 ? id : null;
  }

  function renderSearchResults(items) {
    searchResults.textContent = '';
    if (!items.length) {
      setSearchState('Nenhum resultado encontrado.');
      return;
    }

    items.forEach(item => {
      const iconMeta = RESULT_ICON_META[item.type] || { cssKey: item.type, iconClass: 'fas fa-circle' };
      const refId = extractIdFromUrl(item.url);
      if (!refId) return;

      const row = document.createElement('div');
      row.className = 'caderno-search-result-item';
      row.setAttribute('role', 'option');
      row.setAttribute('tabindex', '-1');
      row.dataset.refId = String(refId);

      const iconWrap = document.createElement('span');
      iconWrap.className = `caderno-search-result-icon caderno-search-result-icon--${iconMeta.cssKey}`;
      const iconEl = document.createElement('i');
      iconEl.className = iconMeta.iconClass;
      iconWrap.appendChild(iconEl);

      const body = document.createElement('span');
      body.className = 'caderno-search-result-body';
      const title = document.createElement('span');
      title.className = 'caderno-search-result-title';
      title.textContent = item.title || item.display_title || '—';
      body.appendChild(title);
      if (item.subtitle) {
        const sub = document.createElement('span');
        sub.className = 'caderno-search-result-sub';
        sub.textContent = item.subtitle;
        body.appendChild(sub);
      }

      row.appendChild(iconWrap);
      row.appendChild(body);
      row.addEventListener('click', onSearchResultClick);
      searchResults.appendChild(row);
    });
  }

  async function performSearch(query) {
    const meta = SEARCH_TYPE_META[searchPendingType];
    if (!meta) return;

    try {
      const response = await apiFetch(`${CFG.apiBuscarUrl}?q=${encodeURIComponent(query)}&limit=8`);
      if (!response.ok) throw new Error('API error');
      const payload = await response.json();
      const items = (payload.results || {})[meta.apiKey] || [];
      renderSearchResults(items);
    } catch (err) {
      console.warn('[caderno] Falha na busca', err);
      setSearchState('Erro ao buscar. Tente novamente.');
    }
  }

  function onSearchInput() {
    clearTimeout(searchDebounceTimer);
    const query = searchInput.value.trim();
    if (query.length < 2) {
      setSearchState('Digite ao menos 2 caracteres.');
      return;
    }
    setSearchLoading();
    searchDebounceTimer = setTimeout(() => performSearch(query), 280);
  }

  async function onSearchResultClick(event) {
    const refId = parseInt(event.currentTarget.dataset.refId, 10);
    if (!Number.isFinite(refId) || refId <= 0) return;
    const type = searchPendingType;
    const layout = searchPendingLayout;
    const triggerBlockId = slashTargetBlockId;
    closeSearchModal();

    if (!type) return;
    if (triggerBlockId) {
      const triggerBlock = getBlockById(triggerBlockId);
      if (triggerBlock && triggerBlock.block_type === 'text' && !(triggerBlock.content || '').trim()) {
        await deleteBlock(triggerBlockId);
      }
    }

    await createBlock({
      block_type: type,
      reference_id: refId,
      content: '',
      ...(layout || {}),
    }, { focus: false });
  }

  async function loadBlocks() {
    setBlocksLoading();
    try {
      const response = await apiFetch(CFG.apiBlocksUrl);
      if (!response.ok) throw new Error('API error');
      const payload = await response.json();
      sheet = { ...DEFAULT_SHEET, ...(payload.sheet || {}) };
      applyCanvasSizing();
      updateExpandControl();
      setBlocks((payload.blocks || []).map(normalizeBlock));
      renderAllBlocks();
    } catch (err) {
      console.warn('[caderno] Falha ao carregar blocos', err);
      blocksContainer.textContent = '';
      const wrapper = document.createElement('div');
      wrapper.className = 'caderno-loading';
      wrapper.style.color = '#dc2626';
      const icon = document.createElement('i');
      icon.className = 'fas fa-exclamation-circle';
      const label = document.createElement('span');
      label.textContent = ' Erro ao carregar o caderno.';
      wrapper.appendChild(icon);
      wrapper.appendChild(label);
      blocksContainer.appendChild(wrapper);
    }
  }

  function setBlocksLoading() {
    blocksContainer.textContent = '';
    const wrapper = document.createElement('div');
    wrapper.className = 'caderno-loading';
    const spinner = document.createElement('div');
    spinner.className = 'caderno-spinner';
    const label = document.createElement('span');
    label.textContent = 'Carregando...';
    wrapper.appendChild(spinner);
    wrapper.appendChild(label);
    blocksContainer.appendChild(wrapper);
  }

  async function onAddZoneInteract(event) {
    if (event && Number.isFinite(event.clientX) && Number.isFinite(event.clientY)) {
      await createTextBlockAtPoint(event.clientX, event.clientY);
      return;
    }

    const reusableDraft = findReusableDraftTextBlock();
    if (reusableDraft) {
      focusBlock(reusableDraft.id);
      return;
    }

    await createBlock({ block_type: 'text', content: '' });
  }

  async function onCanvasInteract(event) {
    if (!canvasWrap) return;
    if (
      event.defaultPrevented ||
      !event.target ||
      event.target.closest('.caderno-block, .slash-menu, .caderno-search-modal, .caderno-search-backdrop, .caderno-expand-zone, a, button, input, textarea, select, label, [contenteditable]')
    ) {
      return;
    }

    closeSlashMenu();
    await onAddZoneInteract(event);
  }

  async function expandPaper() {
    const maxExpandSteps = sheet.max_expand_steps || DEFAULT_SHEET.max_expand_steps;
    if (sheet.expand_steps >= maxExpandSteps) return;
    sheet = { ...sheet, expand_steps: sheet.expand_steps + 1 };
    applyCanvasSizing();
    updateExpandControl();
    await saveSheetExpandSteps(sheet.expand_steps);
  }

  function updatePreviewLayout(previewBlocks, draggedBlockId) {
    const previewMap = new Map(previewBlocks.map(block => [block.id, block]));
    blocksContainer.querySelectorAll('.caderno-block').forEach(blockEl => {
      const blockId = coerceInt(blockEl.dataset.blockId, null);
      const layout = previewMap.get(blockId);
      if (!layout) return;
      if (blockId === draggedBlockId && dragState && dragState.placeholderEl) {
        dragState.placeholderEl.setAttribute('style', buildBlockStyleAttr(layout));
      } else {
        blockEl.setAttribute('style', buildBlockStyleAttr(layout));
      }
    });
  }

  function onDragMove(event) {
    if (!dragState) return;
    event.preventDefault();

    const { blockEl, offsetX, offsetY, blockId } = dragState;
    const left = event.clientX - offsetX;
    const top = event.clientY - offsetY;
    blockEl.style.left = `${left}px`;
    blockEl.style.top = `${top}px`;

    const containerRect = blocksContainer.getBoundingClientRect();
    const columnWidth = (containerRect.width - (GRID_GAP_PX * (GRID_COLUMNS - 1))) / GRID_COLUMNS;
    const desiredX = Math.round((left - containerRect.left) / (columnWidth + GRID_GAP_PX));
    const desiredY = Math.round((top - containerRect.top) / (GRID_ROW_HEIGHT + GRID_GAP_PX));

    const nextBlocks = cloneBlocks(blocks);
    const draggedBlock = nextBlocks.find(block => block.id === blockId);
    if (!draggedBlock) return;
    draggedBlock.grid_x = coerceInt(desiredX, draggedBlock.grid_x, 0, Math.max(0, GRID_COLUMNS - draggedBlock.grid_w));
    draggedBlock.grid_y = coerceInt(desiredY, draggedBlock.grid_y, 0);

    const normalized = normalizeLayout(nextBlocks, blockId);
    if (!layoutsDiffer(normalized, dragState.previewBlocks)) return;
    dragState.previewBlocks = normalized;
    updatePreviewLayout(normalized, blockId);
  }

  function cleanupDragState() {
    if (!dragState) return;
    document.removeEventListener('pointermove', onDragMove);
    document.removeEventListener('pointerup', onDragEnd);
    document.removeEventListener('pointercancel', onDragEnd);
    dragState = null;
    document.body.classList.remove('caderno-is-dragging');
  }

  function onDragEnd() {
    if (!dragState) return;
    const { blockEl, placeholderEl, blockId, previewBlocks } = dragState;
    blockEl.classList.remove('is-dragging');
    blockEl.style.position = '';
    blockEl.style.left = '';
    blockEl.style.top = '';
    blockEl.style.width = '';
    blockEl.style.height = '';
    blockEl.style.zIndex = '';
    if (placeholderEl && placeholderEl.parentNode) {
      placeholderEl.parentNode.removeChild(placeholderEl);
    }
    blocks = previewBlocks;
    cleanupDragState();
    renderAllBlocks();
    setActiveBlock(blockId);
    focusBlock(blockId);
    persistLayoutNow();
  }

  function onBlockHandlePointerDown(event) {
    if (!isDesktopLayout()) return;
    const blockEl = event.currentTarget.closest('.caderno-block');
    if (!blockEl) return;
    const blockId = coerceInt(blockEl.dataset.blockId, null);
    const block = getBlockById(blockId);
    if (!block) return;

    event.preventDefault();
    setActiveBlock(blockId);

    const rect = blockEl.getBoundingClientRect();
    const placeholderEl = document.createElement('div');
    placeholderEl.className = 'caderno-block caderno-block-placeholder';
    placeholderEl.dataset.blockId = String(blockId);
    placeholderEl.setAttribute('style', buildBlockStyleAttr(block));
    blockEl.insertAdjacentElement('afterend', placeholderEl);

    blockEl.classList.add('is-dragging');
    blockEl.style.position = 'fixed';
    blockEl.style.left = `${rect.left}px`;
    blockEl.style.top = `${rect.top}px`;
    blockEl.style.width = `${rect.width}px`;
    blockEl.style.height = `${rect.height}px`;
    blockEl.style.zIndex = '1200';

    dragState = {
      blockId,
      blockEl,
      placeholderEl,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
      previewBlocks: cloneBlocks(blocks),
    };

    document.body.classList.add('caderno-is-dragging');
    document.addEventListener('pointermove', onDragMove);
    document.addEventListener('pointerup', onDragEnd);
    document.addEventListener('pointercancel', onDragEnd);
  }

  function onEditorInput(event) {
    const editorEl = event.target;
    const blockId = coerceInt(editorEl.dataset.blockId, null);
    autoResizeEditor(editorEl);
    syncEditorInteractionState(editorEl);
    if (blockId != null) scheduleMeasureBlock(blockId, 80);

    const text = getEditorText(editorEl);
    if (isSlashTriggerText(text)) {
      openSlashMenu(editorEl, blockId);
    } else {
      closeSlashMenu();
    }
  }

  function onEditorBlur(event) {
    const editorEl = event.target;
    const blockId = coerceInt(editorEl.dataset.blockId, null);
    const content = getEditorText(editorEl);
    const block = getBlockById(blockId);
    if (!block) return;

    syncEditorInteractionState(editorEl);

    if (!content.trim() && (block.block_type === 'text' || block.block_type === 'nota')) {
      setTimeout(() => {
        const stillFocused = blocksContainer.querySelector(`.caderno-block[data-block-id="${blockId}"] :focus`);
        if (!stillFocused) deleteBlock(blockId);
      }, 150);
      return;
    }

    scheduleMeasureBlock(blockId, 20);
    saveBlockContent(blockId, content);
  }

  function onEditorKeydown(event) {
    if (!slashMenu.hidden && (event.key === 'Enter' || event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Escape')) {
      return;
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      const blockId = coerceInt(event.target.dataset.blockId, null);
      const content = getEditorText(event.target);
      saveBlockContent(blockId, content);
      createTextBlockAfter(blockId);
    }
  }

  function onSlashMenuItemClick(event) {
    const type = event.currentTarget.dataset.type;
    const savedTargetId = slashTargetBlockId;
    closeSlashMenu();
    if (savedTargetId == null) return;

    const editorEl = findBlockEditor(savedTargetId);
    if (editorEl) {
      editorEl.textContent = '';
      syncEditorInteractionState(editorEl);
      saveBlockContent(savedTargetId, '');
    }

    if (type === 'text') return;
    if (type === 'nota') {
      convertBlockToNota(savedTargetId);
      return;
    }
    openSearchModal(type, savedTargetId);
  }

  async function onDeleteActionClick(event) {
    event.preventDefault();
    const blockEl = event.currentTarget.closest('.caderno-block');
    if (!blockEl) return;
    const blockId = coerceInt(blockEl.dataset.blockId, null);
    if (blockId != null) await deleteBlock(blockId);
  }

  function onSizeButtonClick(event) {
    event.preventDefault();
    const btn = event.currentTarget;
    const blockEl = btn.closest('.caderno-block');
    if (!blockEl) return;
    const blockId = coerceInt(blockEl.dataset.blockId, null);
    const sizePreset = normalizeSizePreset(btn.dataset.size);
    const nextBlocks = cloneBlocks(blocks);
    const target = nextBlocks.find(block => block.id === blockId);
    if (!target) return;
    const presetLayout = getPresetLayout(sizePreset);
    target.size_preset = sizePreset;
    target.grid_w = presetLayout.grid_w;
    blocks = normalizeLayout(nextBlocks, blockId);
    renderAllBlocks();
    setActiveBlock(blockId);
    scheduleMeasureBlock(blockId, 20);
    schedulePersistLayout();
  }

  function bindBlockEvents() {
    blocksContainer.querySelectorAll('.caderno-block').forEach(blockEl => {
      const blockId = coerceInt(blockEl.dataset.blockId, null);
      blockEl.addEventListener('click', () => setActiveBlock(blockId));
      blockEl.addEventListener('focusin', () => setActiveBlock(blockId));
    });

    blocksContainer.querySelectorAll('[contenteditable]').forEach(editorEl => {
      autoResizeEditor(editorEl);
      syncEditorInteractionState(editorEl);
      editorEl.addEventListener('input', onEditorInput);
      editorEl.addEventListener('blur', onEditorBlur);
      editorEl.addEventListener('keydown', onEditorKeydown);
      editorEl.addEventListener('focus', event => {
        setActiveBlock(coerceInt(event.target.dataset.blockId, null));
        syncEditorInteractionState(event.target);
      });
    });

    blocksContainer.querySelectorAll('.caderno-block-btn[data-action="delete"]').forEach(btn => {
      btn.addEventListener('click', onDeleteActionClick);
    });

    blocksContainer.querySelectorAll('.caderno-size-btn').forEach(btn => {
      btn.addEventListener('click', onSizeButtonClick);
    });

    blocksContainer.querySelectorAll('.caderno-block-handle').forEach(handle => {
      handle.addEventListener('pointerdown', onBlockHandlePointerDown);
    });
  }

  function onWindowResize() {
    applyCanvasSizing();
    renderAllBlocks();
    repositionOpenSlashMenu();
  }

  function init() {
    renderDate();
    applyCanvasSizing();
    updateExpandControl();
    loadBlocks();

    if (canvasWrap) canvasWrap.addEventListener('click', onCanvasInteract);
    addZone.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        onAddZoneInteract();
      }
    });

    if (expandZone) expandZone.addEventListener('click', expandPaper);

    slashMenuList.querySelectorAll('.slash-menu-item').forEach(item => {
      item.addEventListener('click', onSlashMenuItemClick);
    });
    document.addEventListener('keydown', handleSlashMenuNavigation);
    document.addEventListener('click', event => {
      if (!slashMenu.contains(event.target) && !event.target.closest('[contenteditable]')) {
        closeSlashMenu();
      }
    });

    searchInput.addEventListener('input', onSearchInput);
    searchModalClose.addEventListener('click', closeSearchModal);
    searchBackdrop.addEventListener('click', closeSearchModal);
    searchModal.addEventListener('keydown', event => {
      if (event.key === 'Escape') closeSearchModal();
    });

    window.addEventListener('resize', onWindowResize);
    window.addEventListener('scroll', repositionOpenSlashMenu, { passive: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
