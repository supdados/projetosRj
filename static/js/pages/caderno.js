/**
 * caderno.js — editor do Meu Caderno com layout em widgets persistidos.
 */
(function () {
  'use strict';

  const CFG = window.__CADERNO_CONFIG__ || {};

  const blocksContainer = document.getElementById('cadernoBlocks');
  const emptyHint = document.getElementById('cadernoEmptyHint');
  const composer = document.getElementById('cadernoComposer');
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
  const DEFAULT_SHEET = { expand_steps: 0, max_expand_steps: 3 };
  const DEFAULT_TEXT_BLOCK_LAYOUT = { grid_w: 6, grid_h: 5 };
  const DEFAULT_CARD_BLOCK_LAYOUT = { grid_w: 6, grid_h: 3 };
  const TEXT_MIN_GRID_H = 2;
  const CARD_MIN_GRID_W = 3;
  const CARD_MIN_GRID_H = 2;

  let blocks = [];
  let sheet = { ...DEFAULT_SHEET };
  let activeBlockId = null;
  let slashTargetBlockId = null;
  let slashMenuActiveIdx = -1;
  let searchDebounceTimer = null;
  let searchPendingType = null;
  let searchPendingLayout = null;
  let dragState = null;
  let resizeState = null;
  let persistLayoutTimer = null;
  let measureAllTimer = null;
  let unionIndicatorEl = null;
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

  function resolveBlockType(blockOrType) {
    if (typeof blockOrType === 'string') return blockOrType;
    return String(blockOrType && blockOrType.block_type ? blockOrType.block_type : 'text');
  }

  function getDefaultLayoutForBlockType(_blockOrType) {
    return isResizableBlockType(_blockOrType)
      ? { ...DEFAULT_CARD_BLOCK_LAYOUT }
      : { ...DEFAULT_TEXT_BLOCK_LAYOUT };
  }

  function isResizableBlockType(blockOrType) {
    return resolveBlockType(blockOrType) !== 'text';
  }

  function isOverlayBlockType(blockOrType) {
    return resolveBlockType(blockOrType) === 'nota';
  }

  function canAttachNoteToBlock(block) {
    return !!block && !isOverlayBlockType(block);
  }

  function isAttachedOverlayBlock(block) {
    return isOverlayBlockType(block) && Number.isInteger(block.attached_to_block_id) && block.attached_to_block_id > 0;
  }

  function clearBlockAttachment(block) {
    return {
      ...block,
      attached_to_block_id: null,
      attached_offset_x: 0,
      attached_offset_y: 0,
    };
  }

  function getMinimumGridWidth(blockOrType) {
    return isResizableBlockType(blockOrType) ? CARD_MIN_GRID_W : 1;
  }

  function getMinimumGridHeight(blockOrType) {
    return isResizableBlockType(blockOrType) ? CARD_MIN_GRID_H : TEXT_MIN_GRID_H;
  }

  function normalizeBlock(rawBlock) {
    const block = { ...(rawBlock || {}) };
    const blockType = resolveBlockType(block);
    const defaults = getDefaultLayoutForBlockType(blockType);
    const gridW = coerceInt(block.grid_w, defaults.grid_w, getMinimumGridWidth(blockType), GRID_COLUMNS);
    let gridH = coerceInt(block.grid_h, defaults.grid_h, getMinimumGridHeight(blockType));
    if (isResizableBlockType(blockType) && gridW === 6 && gridH === 5) {
      gridH = defaults.grid_h;
    }
    return {
      ...block,
      block_type: blockType,
      content: block.content || '',
      grid_x: coerceInt(block.grid_x, 0, 0, Math.max(0, GRID_COLUMNS - gridW)),
      grid_y: coerceInt(block.grid_y, 0, 0),
      grid_w: gridW,
      grid_h: gridH,
      attached_to_block_id: isOverlayBlockType(blockType)
        ? coerceInt(block.attached_to_block_id, null, 1)
        : null,
      attached_offset_x: isOverlayBlockType(blockType)
        ? coerceInt(block.attached_offset_x, 0)
        : 0,
      attached_offset_y: isOverlayBlockType(blockType)
        ? coerceInt(block.attached_offset_y, 0)
        : 0,
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

  function sortBlocksForRender(sourceBlocks) {
    const ordered = sortBlocksForLayout(sourceBlocks);
    const regularBlocks = ordered.filter(block => !isOverlayBlockType(block));
    const overlayBlocks = ordered.filter(block => isOverlayBlockType(block));
    return [...regularBlocks, ...overlayBlocks];
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

  function resolveOverlayBlocksLayout(overlayBlocks, regularBlocks) {
    const parentBlocks = new Map(regularBlocks.map(block => [block.id, block]));

    return overlayBlocks.map(block => {
      if (!isAttachedOverlayBlock(block)) {
        return {
          ...block,
          grid_x: coerceInt(block.grid_x, 0, 0, Math.max(0, GRID_COLUMNS - block.grid_w)),
          grid_y: coerceInt(block.grid_y, 0, 0, getCurrentSheetMaxGridY(block.grid_h)),
        };
      }

      const parentBlock = parentBlocks.get(block.attached_to_block_id);
      if (!canAttachNoteToBlock(parentBlock)) {
        return {
          ...clearBlockAttachment(block),
          grid_x: coerceInt(block.grid_x, 0, 0, Math.max(0, GRID_COLUMNS - block.grid_w)),
          grid_y: coerceInt(block.grid_y, 0, 0, getCurrentSheetMaxGridY(block.grid_h)),
        };
      }

      return {
        ...block,
        grid_x: coerceInt(
          parentBlock.grid_x + block.attached_offset_x,
          block.grid_x,
          0,
          Math.max(0, GRID_COLUMNS - block.grid_w),
        ),
        grid_y: coerceInt(
          parentBlock.grid_y + block.attached_offset_y,
          block.grid_y,
          0,
          getCurrentSheetMaxGridY(block.grid_h),
        ),
      };
    });
  }

  function normalizeLayout(sourceBlocks, preferredBlockId) {
    const normalizedBlocks = sourceBlocks.map(normalizeBlock);
    const overlayBlocks = [];
    const ordered = sortBlocksForLayout(normalizedBlocks).filter(block => {
      if (isOverlayBlockType(block)) {
        overlayBlocks.push(block);
        return false;
      }
      return true;
    });
    if (preferredBlockId != null && !overlayBlocks.some(block => block.id === preferredBlockId)) {
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

    const overlayLaidOut = resolveOverlayBlocksLayout(overlayBlocks, laidOut);

    return assignSequentialPositions([...laidOut, ...overlayLaidOut]);
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

  function getUnionIndicator() {
    if (unionIndicatorEl) return unionIndicatorEl;
    unionIndicatorEl = document.createElement('div');
    unionIndicatorEl.className = 'caderno-union-indicator';
    unionIndicatorEl.setAttribute('aria-hidden', 'true');
    unionIndicatorEl.hidden = true;
    unionIndicatorEl.innerHTML = '<i class="fas fa-link"></i>';
    document.body.appendChild(unionIndicatorEl);
    return unionIndicatorEl;
  }

  function syncUnionTargetState() {
    const unionTargetId = dragState && dragState.unionTargetId != null ? dragState.unionTargetId : null;
    blocksContainer.querySelectorAll('.caderno-block').forEach(blockEl => {
      const blockId = coerceInt(blockEl.dataset.blockId, null);
      blockEl.classList.toggle('is-union-target', blockId === unionTargetId);
    });

    const indicatorEl = getUnionIndicator();
    if (unionTargetId == null) {
      indicatorEl.hidden = true;
      indicatorEl.style.left = '';
      indicatorEl.style.top = '';
      return;
    }

    const targetEl = findBlockElement(unionTargetId);
    if (!targetEl) {
      indicatorEl.hidden = true;
      return;
    }

    const rect = targetEl.getBoundingClientRect();
    indicatorEl.hidden = false;
    indicatorEl.style.left = `${Math.round(rect.left + (rect.width / 2))}px`;
    indicatorEl.style.top = `${Math.round(rect.top + (rect.height / 2))}px`;
  }

  function setDragUnionTarget(unionTargetId) {
    if (!dragState) return;
    dragState.unionTargetId = unionTargetId == null ? null : unionTargetId;
    syncUnionTargetState();
  }

  function findAttachTargetBlockId(clientX, clientY, draggingBlockId) {
    const hoveredEl = document.elementFromPoint(clientX, clientY);
    const targetBlockEl = hoveredEl ? hoveredEl.closest('.caderno-block') : null;
    if (!targetBlockEl || targetBlockEl.classList.contains('caderno-block-placeholder')) return null;
    const targetBlockId = coerceInt(targetBlockEl.dataset.blockId, null);
    if (targetBlockId == null || targetBlockId === draggingBlockId) return null;
    const targetBlock = getBlockById(targetBlockId);
    return canAttachNoteToBlock(targetBlock) ? targetBlockId : null;
  }

  function getAttachedChildBlocks(parentBlockId, sourceBlocks = blocks) {
    return sourceBlocks
      .filter(block => block.attached_to_block_id === parentBlockId)
      .sort((a, b) => a.grid_y - b.grid_y || a.grid_x - b.grid_x || a.id - b.id);
  }

  function createDragCompanion(sourceEl, rect, zIndex) {
    if (!sourceEl || !rect) return null;
    const companionEl = sourceEl.cloneNode(true);
    companionEl.classList.add('caderno-block-drag-companion');
    companionEl.classList.remove('is-active', 'is-union-target', 'is-dragging');
    companionEl.hidden = true;
    companionEl.style.position = 'fixed';
    companionEl.style.left = `${rect.left}px`;
    companionEl.style.top = `${rect.top}px`;
    companionEl.style.width = `${rect.width}px`;
    companionEl.style.height = `${rect.height}px`;
    companionEl.style.zIndex = String(zIndex);
    document.body.appendChild(companionEl);
    return companionEl;
  }

  function buildDragChildCompanions(parentBlockId, parentRect) {
    const childBlocks = getAttachedChildBlocks(parentBlockId);
    return childBlocks.map((childBlock, index) => {
      const sourceEl = findBlockElement(childBlock.id);
      if (!sourceEl) return null;
      const rect = sourceEl.getBoundingClientRect();
      const companionEl = createDragCompanion(sourceEl, rect, 1201 + index);
      if (!companionEl) return null;
      return {
        blockId: childBlock.id,
        sourceEl,
        companionEl,
        offsetLeft: rect.left - parentRect.left,
        offsetTop: rect.top - parentRect.top,
      };
    }).filter(Boolean);
  }

  function activateDragChildCompanions() {
    if (!dragState || !dragState.childCompanions || dragState.childCompanionsActive) return;
    dragState.childCompanions.forEach(companion => {
      companion.sourceEl.classList.add('is-drag-child-hidden');
      companion.companionEl.hidden = false;
    });
    dragState.childCompanionsActive = true;
  }

  function updateDragChildCompanions(left, top) {
    if (!dragState || !dragState.childCompanions || !dragState.childCompanions.length) return;
    dragState.childCompanions.forEach(companion => {
      companion.companionEl.style.left = `${left + companion.offsetLeft}px`;
      companion.companionEl.style.top = `${top + companion.offsetTop}px`;
    });
  }

  function cleanupDragChildCompanions(childCompanions) {
    (childCompanions || []).forEach(companion => {
      if (companion.sourceEl) companion.sourceEl.classList.remove('is-drag-child-hidden');
      if (companion.companionEl && companion.companionEl.parentNode) {
        companion.companionEl.parentNode.removeChild(companion.companionEl);
      }
    });
  }

  function activateDragState() {
    if (!dragState || dragState.isActive) return;
    const { blockEl, blockId, startRect, startClientX, startClientY } = dragState;
    if (!blockEl || !startRect) return;
    const block = getBlockById(blockId);
    if (!block) return;

    const placeholderEl = document.createElement('div');
    placeholderEl.className = 'caderno-block caderno-block-placeholder';
    placeholderEl.dataset.blockId = String(blockId);
    placeholderEl.setAttribute('style', buildBlockStyleAttr(block));
    blockEl.insertAdjacentElement('afterend', placeholderEl);

    const childCompanions = isOverlayBlockType(block) ? [] : buildDragChildCompanions(blockId, startRect);

    blockEl.classList.add('is-dragging');
    blockEl.style.position = 'fixed';
    blockEl.style.left = `${startRect.left}px`;
    blockEl.style.top = `${startRect.top}px`;
    blockEl.style.width = `${startRect.width}px`;
    blockEl.style.height = `${startRect.height}px`;
    blockEl.style.zIndex = '1200';
    blockEl.style.pointerEvents = 'none';

    dragState.placeholderEl = placeholderEl;
    dragState.childCompanions = childCompanions;
    dragState.childCompanionsActive = false;
    dragState.offsetX = startClientX - startRect.left;
    dragState.offsetY = startClientY - startRect.top;
    dragState.isActive = true;
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
        block.grid_x !== current.grid_x ||
        block.grid_y !== current.grid_y ||
        block.grid_w !== current.grid_w ||
        block.grid_h !== current.grid_h ||
        block.attached_to_block_id !== current.attached_to_block_id ||
        block.attached_offset_x !== current.attached_offset_x ||
        block.attached_offset_y !== current.attached_offset_y
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

  function getCurrentSheetPixelHeight() {
    if (!canvasWrap) return getBaseCanvasMinHeight();
    const inlineMinHeight = parseFloat(canvasWrap.style.minHeight);
    if (Number.isFinite(inlineMinHeight) && inlineMinHeight > 0) return inlineMinHeight;

    const computedMinHeight = parseFloat(window.getComputedStyle(canvasWrap).minHeight);
    if (Number.isFinite(computedMinHeight) && computedMinHeight > 0) return computedMinHeight;

    return getBaseCanvasMinHeight();
  }

  function getCurrentSheetUsableHeight() {
    const reserve = 16;
    return Math.max(GRID_TRACK_HEIGHT, getCurrentSheetPixelHeight() - reserve);
  }

  function getCurrentSheetTotalRows() {
    return Math.max(1, Math.floor((getCurrentSheetUsableHeight() + GRID_GAP_PX) / GRID_TRACK_HEIGHT));
  }

  function getCurrentSheetMaxGridY(gridH = DEFAULT_TEXT_BLOCK_LAYOUT.grid_h) {
    const maxRows = getCurrentSheetTotalRows();
    return Math.max(0, maxRows - Math.max(1, gridH));
  }

  function getCurrentSheetMaxGridHeight(gridY = 0) {
    return Math.max(1, getCurrentSheetTotalRows() - coerceInt(gridY, 0, 0));
  }

  function compactLayout(sourceBlocks) {
    const normalizedBlocks = sourceBlocks.map(normalizeBlock);
    const overlayBlocks = [];
    const ordered = sortBlocksForLayout(normalizedBlocks).filter(block => {
      if (isOverlayBlockType(block)) {
        overlayBlocks.push(block);
        return false;
      }
      return true;
    });
    const occupied = new Set();

    const laidOut = ordered.map(block => {
      const slot = findSlotFrom(
        occupied,
        block.grid_w,
        block.grid_h,
        block.grid_x,
        0,
      );
      const nextBlock = {
        ...block,
        grid_x: slot.grid_x,
        grid_y: slot.grid_y,
      };
      occupyCells(occupied, nextBlock.grid_x, nextBlock.grid_y, nextBlock.grid_w, nextBlock.grid_h);
      return nextBlock;
    });

    const overlayLaidOut = resolveOverlayBlocksLayout(overlayBlocks, laidOut);

    return assignSequentialPositions([...laidOut, ...overlayLaidOut]);
  }

  function hasLayoutOverflowForCurrentSheet(sourceBlocks) {
    return sourceBlocks.some(block => block.grid_y > getCurrentSheetMaxGridY(block.grid_h));
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

  function canMoveBlock(block) {
    return block.block_type !== 'text';
  }

  function canResizeBlock(block) {
    return block.block_type !== 'text';
  }

  function canDeleteBlock(block) {
    return block.block_type !== 'text';
  }

  function shouldRenderToolbar(block) {
    return canMoveBlock(block) || canResizeBlock(block) || canDeleteBlock(block);
  }

  function renderResizeHandles(block) {
    if (!canResizeBlock(block)) return '';
    return `
      <button class="caderno-block-resize-handle caderno-block-resize-handle--east" type="button" data-action="resize" data-resize-direction="east" aria-label="Ajustar largura"></button>
      <button class="caderno-block-resize-handle caderno-block-resize-handle--south" type="button" data-action="resize" data-resize-direction="south" aria-label="Ajustar altura"></button>
      <button class="caderno-block-resize-handle caderno-block-resize-handle--corner" type="button" data-action="resize" data-resize-direction="southeast" aria-label="Ajustar largura e altura"></button>
    `;
  }

  function renderToolbar(block) {
    if (!shouldRenderToolbar(block)) return '';

    return `
      <div class="caderno-block-toolbar">
        ${canDeleteBlock(block) ? `
          <div class="caderno-block-toolbar-delete">
            <button class="caderno-block-btn caderno-block-btn--delete" type="button" data-action="delete" aria-label="Remover bloco">
              <i class="fas fa-trash-alt"></i>
            </button>
          </div>
        ` : ''}
        ${renderResizeHandles(block)}
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
          <div class="caderno-nota-card-header" data-drag-surface="note">
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
        <div class="caderno-ref-null" data-drag-surface="reference">
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
        <div class="caderno-ref-card" data-drag-surface="reference">
          <span class="caderno-ref-card-icon"><i class="fas fa-folder"></i></span>
          <div class="caderno-ref-card-body">
            <span class="caderno-ref-card-type">Projeto</span>
            <a href="${safeHref(ref.url)}" class="caderno-ref-card-title-link" title="${escapeHtml(ref.titulo)}">${escapeHtml(ref.titulo)}</a>
            <div class="caderno-ref-card-meta">
              ${ref.orgao_sigla ? `<span>${escapeHtml(ref.orgao_sigla)}</span>` : ''}
              ${ref.status ? `<span class="caderno-ref-badge">${escapeHtml(ref.status)}</span>` : ''}
              ${ref.prioridade ? prioLabel(ref.prioridade) : ''}
            </div>
            ${ref.total_etapas > 0 ? `
              <div class="caderno-project-progress">
                <div class="caderno-progress-bar-wrap">
                  <div class="caderno-progress-bar" style="width:${Math.min(100, Math.max(0, pct))}%"></div>
                </div>
                <span class="caderno-progress-label">${escapeHtml(String(ref.etapas_concluidas))}/${escapeHtml(String(ref.total_etapas))}</span>
              </div>
            ` : ''}
          </div>
        </div>
      </div>
    `;
  }

  function renderEtapaBlock(block) {
    const ref = block.ref_data;
    if (!ref) return renderNullRef(block, 'Etapa removida');
    const dateRange = [formatDate(ref.data_inicio), formatDate(ref.data_fim)].filter(Boolean).join(' → ');
    return `
      <div class="caderno-widget-body">
        <div class="caderno-ref-card" data-drag-surface="reference">
          <span class="caderno-ref-card-icon"><i class="fas fa-tasks"></i></span>
          <div class="caderno-ref-card-body">
            <span class="caderno-ref-card-type">Etapa</span>
            <a href="${safeHref(ref.url)}" class="caderno-ref-card-title-link" title="${escapeHtml(ref.descricao)}">${escapeHtml(ref.descricao)}</a>
            <div class="caderno-ref-card-meta">
              ${ref.project_titulo ? `<span>${escapeHtml(ref.project_titulo)}</span>` : ''}
              ${etapaStatusBadge(ref)}
              ${dateRange ? `<span><i class="fas fa-calendar-alt"></i> ${escapeHtml(dateRange)}</span>` : ''}
              ${ref.responsavel ? `<span>${escapeHtml(ref.responsavel)}</span>` : ''}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderTaskBlock(block) {
    const ref = block.ref_data;
    if (!ref) return renderNullRef(block, 'Tarefa removida');
    return `
      <div class="caderno-widget-body">
        <div class="caderno-ref-card" data-drag-surface="reference">
          <span class="caderno-ref-card-icon"><i class="fas fa-check-square"></i></span>
          <div class="caderno-ref-card-body">
            <span class="caderno-ref-card-type">Tarefa</span>
            <a href="${safeHref(ref.url)}" class="caderno-ref-card-title-link" title="${escapeHtml(ref.descricao)}">${escapeHtml(ref.descricao)}</a>
            <div class="caderno-ref-card-meta">
              ${ref.project_titulo ? `<span>${escapeHtml(ref.project_titulo)}</span>` : ''}
              ${statusBadge(ref.status)}
              ${ref.prioridade ? prioLabel(ref.prioridade) : ''}
              ${ref.responsavel ? `<span>${escapeHtml(ref.responsavel)}</span>` : ''}
            </div>
          </div>
        </div>
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
      <div class="${classes}" data-block-id="${block.id}" data-block-type="${block.block_type}" role="listitem" tabindex="-1" style="${buildBlockStyleAttr(block)}">
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
    blocksContainer.innerHTML = sortBlocksForRender(blocks).map(renderBlockHTML).join('');
    bindBlockEvents();
    updateEmptyHint();
    syncActiveBlockState();
    syncUnionTargetState();
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

  function shouldAutoMeasureBlock(block) {
    return !!block && block.block_type === 'text';
  }

  function syncEditorHeight(editorEl) {
    if (!editorEl) return;
    const blockId = coerceInt(editorEl.dataset.blockId, null);
    const block = getBlockById(blockId);
    if (!block) return;
    if (block.block_type === 'text') {
      editorEl.style.height = 'auto';
      editorEl.style.height = `${editorEl.scrollHeight}px`;
      return;
    }
    editorEl.style.height = '';
  }

  function measureRequiredGridHeight(blockId) {
    const block = getBlockById(blockId);
    const blockEl = findBlockElement(blockId);
    if (!shouldAutoMeasureBlock(block) || !blockEl || !isDesktopLayout()) return null;
    const measureRoot = blockEl.querySelector('.caderno-text-editor');
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
          grid_x: block.grid_x,
          grid_y: block.grid_y,
          grid_w: block.grid_w,
          grid_h: block.grid_h,
          attached_to_block_id: block.attached_to_block_id,
          attached_offset_x: block.attached_offset_x,
          attached_offset_y: block.attached_offset_y,
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
    const block = getBlockById(blockId);
    if (!shouldAutoMeasureBlock(block)) {
      const existingTimer = measureTimers.get(blockId);
      if (existingTimer) clearTimeout(existingTimer);
      measureTimers.delete(blockId);
      return;
    }

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

  async function createTextBlockFromComposer() {
    const reusableDraft = findReusableDraftTextBlock();
    if (reusableDraft) {
      setActiveBlock(reusableDraft.id);
      focusBlock(reusableDraft.id);
      return reusableDraft;
    }

    return createBlock({ block_type: 'text', content: '' });
  }

  async function onComposerActionClick(event) {
    event.preventDefault();
    const btn = event.currentTarget;
    const type = btn ? String(btn.dataset.createType || '').trim() : '';
    if (!type) return;

    closeSlashMenu();

    if (type === 'text') {
      await createTextBlockFromComposer();
      return;
    }

    if (type === 'nota') {
      await createBlock({ block_type: 'nota', content: '' });
      return;
    }

    openSearchModal(type, null);
  }

  async function createTextBlockAfter(blockId) {
    const sourceBlock = getBlockById(blockId);
    if (!sourceBlock) return;
    const defaults = getDefaultLayoutForBlockType('text');
    const desiredGridY = Math.min(
      sourceBlock.grid_y + sourceBlock.grid_h,
      getCurrentSheetMaxGridY(defaults.grid_h),
    );
    await createBlock({
      block_type: 'text',
      content: '',
      grid_x: sourceBlock.grid_x,
      grid_y: desiredGridY,
      grid_w: defaults.grid_w,
      grid_h: defaults.grid_h,
    });
  }

  async function deleteBlock(blockId) {
    blocks = normalizeLayout(blocks
      .filter(block => block.id !== blockId)
      .map(block => (block.attached_to_block_id === blockId ? clearBlockAttachment(block) : block)));
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
    const defaults = getDefaultLayoutForBlockType(type);
    searchPendingLayout = sourceBlock ? {
      position: sourceBlock.position,
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
      const persistedSheet = { ...DEFAULT_SHEET, ...(payload.sheet || {}) };
      const shouldResetSheetSize = persistedSheet.expand_steps > 0;
      sheet = {
        ...persistedSheet,
        expand_steps: 0,
      };
      applyCanvasSizing();
      updateExpandControl();
      const incomingBlocks = (payload.blocks || []).map(normalizeBlock);
      const nextBlocks = (
        shouldResetSheetSize || hasLayoutOverflowForCurrentSheet(incomingBlocks)
      )
        ? compactLayout(incomingBlocks)
        : normalizeLayout(incomingBlocks);
      blocks = nextBlocks;
      renderAllBlocks();

      if (shouldResetSheetSize) {
        await saveSheetExpandSteps(0);
      }
      if (layoutsDiffer(nextBlocks, incomingBlocks)) {
        schedulePersistLayout();
      }
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

  async function expandPaper() {
    const maxExpandSteps = sheet.max_expand_steps || DEFAULT_SHEET.max_expand_steps;
    if (sheet.expand_steps >= maxExpandSteps) return;
    sheet = { ...sheet, expand_steps: sheet.expand_steps + 1 };
    applyCanvasSizing();
    updateExpandControl();
    await saveSheetExpandSteps(sheet.expand_steps);
  }

  function getGridMetrics() {
    const containerRect = blocksContainer.getBoundingClientRect();
    const columnWidth = (containerRect.width - (GRID_GAP_PX * (GRID_COLUMNS - 1))) / GRID_COLUMNS;
    return {
      containerRect,
      columnTrack: columnWidth + GRID_GAP_PX,
      rowTrack: GRID_TRACK_HEIGHT,
    };
  }

  function updatePreviewLayout(previewBlocks, floatingBlockId) {
    const previewMap = new Map(previewBlocks.map(block => [block.id, block]));
    blocksContainer.querySelectorAll('.caderno-block').forEach(blockEl => {
      const blockId = coerceInt(blockEl.dataset.blockId, null);
      const layout = previewMap.get(blockId);
      if (!layout) return;
      if (blockId === floatingBlockId && dragState && dragState.placeholderEl) {
        dragState.placeholderEl.setAttribute('style', buildBlockStyleAttr(layout));
      } else {
        blockEl.setAttribute('style', buildBlockStyleAttr(layout));
      }
    });
    syncUnionTargetState();
  }

  function onDragMove(event) {
    if (!dragState) return;
    event.preventDefault();

    const { blockEl, blockId } = dragState;
    const deltaFromOriginX = event.clientX - dragState.startClientX;
    const deltaFromOriginY = event.clientY - dragState.startClientY;
    if (!dragState.hasMoved && Math.max(Math.abs(deltaFromOriginX), Math.abs(deltaFromOriginY)) < 6) {
      return;
    }
    if (!dragState.isActive) activateDragState();
    if (!dragState.isActive) return;
    if (!dragState.hasMoved) activateDragChildCompanions();
    dragState.hasMoved = true;
    const { offsetX, offsetY } = dragState;

    const left = event.clientX - offsetX;
    const top = event.clientY - offsetY;
    blockEl.style.left = `${left}px`;
    blockEl.style.top = `${top}px`;
    updateDragChildCompanions(left, top);

    const { containerRect, columnTrack, rowTrack } = getGridMetrics();
    const desiredX = Math.round((left - containerRect.left) / columnTrack);
    const desiredY = Math.round((top - containerRect.top) / rowTrack);

    const nextBlocks = cloneBlocks(blocks);
    const draggedBlock = nextBlocks.find(block => block.id === blockId);
    if (!draggedBlock) return;
    const isDraggingNote = isOverlayBlockType(draggedBlock);
    if (isDraggingNote) {
      draggedBlock.attached_to_block_id = null;
      draggedBlock.attached_offset_x = 0;
      draggedBlock.attached_offset_y = 0;
      setDragUnionTarget(findAttachTargetBlockId(event.clientX, event.clientY, blockId));
    } else if (dragState.unionTargetId != null) {
      setDragUnionTarget(null);
    }
    draggedBlock.grid_x = coerceInt(desiredX, draggedBlock.grid_x, 0, Math.max(0, GRID_COLUMNS - draggedBlock.grid_w));
    draggedBlock.grid_y = coerceInt(desiredY, draggedBlock.grid_y, 0, getCurrentSheetMaxGridY(draggedBlock.grid_h));

    const normalized = normalizeLayout(nextBlocks, blockId);
    if (!layoutsDiffer(normalized, dragState.previewBlocks)) return;
    dragState.previewBlocks = normalized;
    updatePreviewLayout(normalized, blockId);
  }

  function cleanupDragState() {
    if (!dragState) return;
    if (dragState.blockEl) dragState.blockEl.style.pointerEvents = '';
    cleanupDragChildCompanions(dragState.childCompanions);
    document.removeEventListener('pointermove', onDragMove);
    document.removeEventListener('pointerup', onDragEnd);
    document.removeEventListener('pointercancel', onDragEnd);
    dragState.unionTargetId = null;
    dragState = null;
    document.body.classList.remove('caderno-is-dragging');
    syncUnionTargetState();
  }

  function onDragEnd() {
    if (!dragState) return;
    const {
      blockEl,
      placeholderEl,
      blockId,
      previewBlocks,
      unionTargetId,
    } = dragState;
    if (!dragState.isActive || !dragState.hasMoved) {
      cleanupDragState();
      setActiveBlock(blockId);
      return;
    }
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
    const finalBlocks = cloneBlocks(previewBlocks);
    const draggedBlock = finalBlocks.find(block => block.id === blockId);
    if (draggedBlock && isOverlayBlockType(draggedBlock)) {
      if (unionTargetId != null) {
        const parentBlock = finalBlocks.find(block => block.id === unionTargetId);
        if (canAttachNoteToBlock(parentBlock)) {
          draggedBlock.attached_to_block_id = parentBlock.id;
          draggedBlock.attached_offset_x = draggedBlock.grid_x - parentBlock.grid_x;
          draggedBlock.attached_offset_y = draggedBlock.grid_y - parentBlock.grid_y;
        } else {
          Object.assign(draggedBlock, clearBlockAttachment(draggedBlock));
        }
      } else {
        Object.assign(draggedBlock, clearBlockAttachment(draggedBlock));
      }
      blocks = normalizeLayout(finalBlocks, blockId);
    } else {
      blocks = previewBlocks;
    }
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

    dragState = {
      blockId,
      blockEl,
      startRect: rect,
      startClientX: event.clientX,
      startClientY: event.clientY,
      hasMoved: false,
      isActive: false,
      previewBlocks: cloneBlocks(blocks),
      placeholderEl: null,
      childCompanions: [],
      childCompanionsActive: false,
      unionTargetId: null,
    };

    document.body.classList.add('caderno-is-dragging');
    document.addEventListener('pointermove', onDragMove);
    document.addEventListener('pointerup', onDragEnd);
    document.addEventListener('pointercancel', onDragEnd);
  }

  function cleanupResizeState() {
    if (!resizeState) return;
    document.removeEventListener('pointermove', onResizeMove);
    document.removeEventListener('pointerup', onResizeEnd);
    document.removeEventListener('pointercancel', onResizeEnd);
    resizeState = null;
    document.body.classList.remove('caderno-is-resizing');
  }

  function onResizeMove(event) {
    if (!resizeState) return;
    event.preventDefault();

    const { blockId, direction, originalBlock } = resizeState;
    const nextBlocks = cloneBlocks(blocks);
    const target = nextBlocks.find(block => block.id === blockId);
    if (!target) return;

    const { columnTrack, rowTrack } = getGridMetrics();
    const affectsWidth = direction === 'east' || direction === 'southeast';
    const affectsHeight = direction === 'south' || direction === 'southeast';
    const deltaCols = Math.round((event.clientX - resizeState.startClientX) / columnTrack);
    const deltaRows = Math.round((event.clientY - resizeState.startClientY) / rowTrack);
    const maxGridW = Math.max(getMinimumGridWidth(target), GRID_COLUMNS - originalBlock.grid_x);
    const maxGridH = Math.max(getMinimumGridHeight(target), getCurrentSheetMaxGridHeight(originalBlock.grid_y));

    target.grid_x = originalBlock.grid_x;
    target.grid_y = originalBlock.grid_y;
    if (affectsWidth) {
      target.grid_w = coerceInt(
        originalBlock.grid_w + deltaCols,
        originalBlock.grid_w,
        getMinimumGridWidth(target),
        maxGridW,
      );
    }
    if (affectsHeight) {
      target.grid_h = coerceInt(
        originalBlock.grid_h + deltaRows,
        originalBlock.grid_h,
        getMinimumGridHeight(target),
        maxGridH,
      );
    }

    const normalized = normalizeLayout(nextBlocks, blockId);
    if (!layoutsDiffer(normalized, resizeState.previewBlocks)) return;
    resizeState.previewBlocks = normalized;
    updatePreviewLayout(normalized, null);
  }

  function onResizeEnd() {
    if (!resizeState) return;
    const { blockId, previewBlocks } = resizeState;
    blocks = previewBlocks;
    cleanupResizeState();
    renderAllBlocks();
    setActiveBlock(blockId);
    persistLayoutNow();
  }

  function onResizeHandlePointerDown(event) {
    if (!isDesktopLayout()) return;
    const handle = event.currentTarget;
    const blockEl = handle.closest('.caderno-block');
    if (!blockEl) return;
    const blockId = coerceInt(blockEl.dataset.blockId, null);
    const block = getBlockById(blockId);
    if (!block || !canResizeBlock(block)) return;

    event.preventDefault();
    event.stopPropagation();
    setActiveBlock(blockId);
    resizeState = {
      blockId,
      direction: String(handle.dataset.resizeDirection || ''),
      startClientX: event.clientX,
      startClientY: event.clientY,
      originalBlock: { ...block },
      previewBlocks: cloneBlocks(blocks),
    };

    document.body.classList.add('caderno-is-resizing');
    document.addEventListener('pointermove', onResizeMove);
    document.addEventListener('pointerup', onResizeEnd);
    document.addEventListener('pointercancel', onResizeEnd);
  }

  function onEditorInput(event) {
    const editorEl = event.target;
    const blockId = coerceInt(editorEl.dataset.blockId, null);
    syncEditorHeight(editorEl);
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

    syncEditorHeight(editorEl);
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

  function onDragSurfacePointerDown(event) {
    if (event.target.closest('a, button, [contenteditable], input, textarea, select')) return;
    const blockEl = event.currentTarget.closest('.caderno-block');
    if (!blockEl) return;
    onBlockHandlePointerDown(event);
  }

  function bindBlockEvents() {
    blocksContainer.querySelectorAll('.caderno-block').forEach(blockEl => {
      const blockId = coerceInt(blockEl.dataset.blockId, null);
      blockEl.addEventListener('click', () => setActiveBlock(blockId));
      blockEl.addEventListener('focusin', () => setActiveBlock(blockId));
    });

    blocksContainer.querySelectorAll('[contenteditable]').forEach(editorEl => {
      syncEditorHeight(editorEl);
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

    blocksContainer.querySelectorAll('[data-drag-surface]').forEach(surface => {
      surface.addEventListener('pointerdown', onDragSurfacePointerDown);
    });

    blocksContainer.querySelectorAll('.caderno-block-resize-handle').forEach(handle => {
      handle.addEventListener('pointerdown', onResizeHandlePointerDown);
    });
  }

  function onWindowResize() {
    applyCanvasSizing();
    renderAllBlocks();
    syncUnionTargetState();
    repositionOpenSlashMenu();
  }

  function init() {
    renderDate();
    applyCanvasSizing();
    updateExpandControl();
    loadBlocks();

    if (composer) {
      composer.querySelectorAll('[data-create-type]').forEach(btn => {
        btn.addEventListener('click', onComposerActionClick);
      });
    }
    if (expandZone) expandZone.addEventListener('click', expandPaper);

    slashMenuList.querySelectorAll('.slash-menu-item').forEach(item => {
      item.addEventListener('click', onSlashMenuItemClick);
    });
    document.addEventListener('keydown', handleSlashMenuNavigation);
    document.addEventListener('click', event => {
      if (!event.target.closest('.caderno-block')) {
        setActiveBlock(null);
      }
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
