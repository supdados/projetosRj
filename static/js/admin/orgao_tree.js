(function () {
  'use strict';

  var tree = document.getElementById('orgaoTree');
  if (!tree) return;

  var searchInput = document.getElementById('orgaoTreeSearch');
  var expandAllBtn = document.querySelector('[data-orgao-expand-all]');
  var collapseAllBtn = document.querySelector('[data-orgao-collapse-all]');

  var TIPO_RANK = {};
  var ranksEl = document.getElementById('orgaoTipoRanks');
  if (ranksEl) {
    try { TIPO_RANK = JSON.parse(ranksEl.textContent || '{}'); } catch (_) {}
  }

  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function isValidParentTipo(parentTipo, childTipo) {
    var pr = TIPO_RANK[parentTipo];
    var cr = TIPO_RANK[childTipo];
    if (pr === undefined || cr === undefined) return true;
    return pr < cr;
  }

  function setOpen(node, open) {
    if (open) {
      node.classList.add('is-open');
    } else {
      node.classList.remove('is-open');
    }
  }

  function expandToRoot(node) {
    var parent = node.parentElement;
    while (parent && parent !== tree) {
      if (parent.classList && parent.classList.contains('orgao-node')) {
        setOpen(parent, true);
      }
      parent = parent.parentElement;
    }
  }

  // === Expand / collapse via chevron ===
  tree.addEventListener('click', function (e) {
    var toggle = e.target.closest('[data-orgao-toggle]');
    if (!toggle) return;
    var node = toggle.closest('.orgao-node');
    if (!node) return;
    if (node.classList.contains('is-leaf')) return;
    setOpen(node, !node.classList.contains('is-open'));
  });

  // Initially expand level 0 + 1
  Array.prototype.forEach.call(tree.querySelectorAll('.orgao-node'), function (node) {
    var depth = parseInt(node.getAttribute('data-depth') || '0', 10);
    if (depth <= 1) setOpen(node, true);
  });

  if (expandAllBtn) {
    expandAllBtn.addEventListener('click', function () {
      Array.prototype.forEach.call(tree.querySelectorAll('.orgao-node'), function (n) {
        setOpen(n, true);
      });
    });
  }
  if (collapseAllBtn) {
    collapseAllBtn.addEventListener('click', function () {
      Array.prototype.forEach.call(tree.querySelectorAll('.orgao-node'), function (n) {
        var depth = parseInt(n.getAttribute('data-depth') || '0', 10);
        setOpen(n, depth === 0);
      });
    });
  }

  // === Search filter ===
  function applyFilter(query) {
    var q = (query || '').trim().toLowerCase();
    var nodes = tree.querySelectorAll('.orgao-node');
    if (!q) {
      Array.prototype.forEach.call(nodes, function (n) {
        n.classList.remove('is-hidden');
        n.classList.remove('is-match');
      });
      return;
    }
    Array.prototype.forEach.call(nodes, function (n) {
      var sigla = (n.getAttribute('data-sigla') || '').toLowerCase();
      var nome = (n.getAttribute('data-nome') || '').toLowerCase();
      var hit = sigla.indexOf(q) !== -1 || nome.indexOf(q) !== -1;
      if (hit) {
        n.classList.add('is-match');
        n.classList.remove('is-hidden');
        expandToRoot(n);
      } else {
        n.classList.remove('is-match');
      }
    });
    Array.prototype.forEach.call(nodes, function (n) {
      if (n.classList.contains('is-match')) return;
      var hasMatchInSubtree = n.querySelector('.orgao-node.is-match');
      if (!hasMatchInSubtree) {
        n.classList.add('is-hidden');
      } else {
        n.classList.remove('is-hidden');
        setOpen(n, true);
      }
    });
  }

  if (searchInput) {
    var debounceTimer = null;
    searchInput.addEventListener('input', function () {
      clearTimeout(debounceTimer);
      var value = this.value;
      debounceTimer = setTimeout(function () { applyFilter(value); }, 120);
    });
  }

  // === Drag & drop reparent ===
  var dragId = null;
  var dragTipo = null;
  var dragDescendants = new Set();

  function collectDescendantIds(node) {
    var ids = new Set();
    Array.prototype.forEach.call(node.querySelectorAll('.orgao-node'), function (d) {
      ids.add(d.getAttribute('data-id'));
    });
    return ids;
  }

  function clearDropTargets() {
    Array.prototype.forEach.call(tree.querySelectorAll('.is-drop-target'), function (n) {
      n.classList.remove('is-drop-target');
    });
  }

  tree.addEventListener('dragstart', function (e) {
    var row = e.target.closest('.orgao-row');
    if (!row || row.getAttribute('draggable') !== 'true') return;
    var node = row.closest('.orgao-node');
    if (!node) return;
    dragId = node.getAttribute('data-id');
    dragTipo = node.getAttribute('data-tipo');
    dragDescendants = collectDescendantIds(node);
    dragDescendants.add(dragId);
    e.dataTransfer.effectAllowed = 'move';
    try { e.dataTransfer.setData('text/plain', dragId); } catch (_) {}
    node.classList.add('is-dragging');
  });

  tree.addEventListener('dragend', function () {
    if (dragId) {
      var node = tree.querySelector('[data-id="' + dragId + '"]');
      if (node) node.classList.remove('is-dragging');
    }
    clearDropTargets();
    dragId = null;
    dragTipo = null;
    dragDescendants = new Set();
  });

  tree.addEventListener('dragover', function (e) {
    if (!dragId) return;
    var row = e.target.closest('.orgao-row');
    if (!row) return;
    var node = row.closest('.orgao-node');
    if (!node) return;
    var targetId = node.getAttribute('data-id');
    if (dragDescendants.has(targetId)) return;
    var targetTipo = node.getAttribute('data-tipo');
    if (!isValidParentTipo(targetTipo, dragTipo)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    Array.prototype.forEach.call(tree.querySelectorAll('.is-drop-target'), function (n) {
      if (n !== node) n.classList.remove('is-drop-target');
    });
    node.classList.add('is-drop-target');
  });

  tree.addEventListener('dragleave', function (e) {
    var node = e.target.closest('.orgao-node');
    if (node && node.classList.contains('is-drop-target')) {
      node.classList.remove('is-drop-target');
    }
  });

  function updateDepthRecursive(node, newDepth) {
    node.setAttribute('data-depth', newDepth);
    node.style.setProperty('--orgao-depth', newDepth);
    var children = node.querySelector(':scope > .orgao-children');
    if (!children) return;
    Array.prototype.forEach.call(children.children, function (child) {
      if (child.classList && child.classList.contains('orgao-node')) {
        updateDepthRecursive(child, newDepth + 1);
      }
    });
  }

  function refreshLeafState(node) {
    if (!node) return;
    var children = node.querySelector(':scope > .orgao-children');
    var hasChild = false;
    if (children) {
      for (var i = 0; i < children.children.length; i++) {
        if (children.children[i].classList && children.children[i].classList.contains('orgao-node')) {
          hasChild = true;
          break;
        }
      }
    }
    if (hasChild) {
      node.classList.remove('is-leaf');
    } else {
      node.classList.add('is-leaf');
      node.classList.remove('is-open');
    }
  }

  function reparentNode(movingNode, newParentNode) {
    var oldParentNode = null;
    var oldUl = movingNode.parentNode;
    if (oldUl && oldUl.classList && oldUl.classList.contains('orgao-children')) {
      oldParentNode = oldUl.closest('.orgao-node');
    }

    var newChildren = newParentNode.querySelector(':scope > .orgao-children');
    if (!newChildren) {
      newChildren = document.createElement('ul');
      newChildren.className = 'orgao-children';
      newParentNode.appendChild(newChildren);
    }
    newChildren.appendChild(movingNode);

    movingNode.setAttribute('data-pai-id', newParentNode.getAttribute('data-id'));

    var newDepth = parseInt(newParentNode.getAttribute('data-depth') || '0', 10) + 1;
    updateDepthRecursive(movingNode, newDepth);

    refreshLeafState(oldParentNode);
    refreshLeafState(newParentNode);
    setOpen(newParentNode, true);

    Array.prototype.forEach.call(tree.querySelectorAll('.is-selected'), function (n) {
      n.classList.remove('is-selected');
    });
    movingNode.classList.add('is-selected');
    history.replaceState(null, '', '#orgao-' + movingNode.getAttribute('data-id'));
  }

  tree.addEventListener('drop', function (e) {
    if (!dragId) return;
    var row = e.target.closest('.orgao-row');
    if (!row) return;
    var node = row.closest('.orgao-node');
    if (!node) return;
    var targetId = node.getAttribute('data-id');
    if (dragDescendants.has(targetId)) return;
    var targetTipo = node.getAttribute('data-tipo');
    if (!isValidParentTipo(targetTipo, dragTipo)) {
      e.preventDefault();
      showToast('Um órgão do tipo "' + targetTipo + '" não pode ser pai de "' + dragTipo + '".', 'danger');
      clearDropTargets();
      return;
    }
    e.preventDefault();

    var movingId = dragId;
    var movingNode = tree.querySelector('[data-id="' + movingId + '"]');
    var newParentNode = node;
    clearDropTargets();

    fetch('/admin/orgaos/' + movingId + '/move', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-CSRFToken': getCsrfToken(),
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({ pai_id: targetId })
    }).then(function (res) {
      return res.json().then(function (body) { return { ok: res.ok, body: body }; });
    }).then(function (result) {
      if (result.ok && result.body && result.body.ok) {
        if (movingNode && newParentNode) {
          reparentNode(movingNode, newParentNode);
        }
      } else {
        var msg = (result.body && result.body.error) || 'Erro ao mover órgão.';
        showToast(msg, 'danger');
      }
    }).catch(function () {
      showToast('Falha de rede ao mover órgão.', 'danger');
    });
  });

  function showToast(message, level) {
    var stack = document.querySelector('.app-flash-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'app-flash-stack';
      document.body.appendChild(stack);
    }
    var alert = document.createElement('div');
    alert.className = 'app-flash-alert alert-' + (level || 'info');
    alert.textContent = message;
    stack.appendChild(alert);
    setTimeout(function () {
      if (alert.parentNode) alert.parentNode.removeChild(alert);
    }, 4000);
  }

  // === Highlight selected via URL hash ===
  function highlightFromHash() {
    Array.prototype.forEach.call(tree.querySelectorAll('.is-selected'), function (n) {
      n.classList.remove('is-selected');
    });
    var hash = window.location.hash;
    if (!hash || hash.indexOf('#orgao-') !== 0) return;
    var node = tree.querySelector(hash);
    if (node) {
      node.classList.add('is-selected');
      expandToRoot(node);
      node.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }
  highlightFromHash();
  window.addEventListener('hashchange', highlightFromHash);

  tree.addEventListener('click', function (e) {
    var row = e.target.closest('.orgao-row');
    if (!row) return;
    if (e.target.closest('.orgao-actions')) return;
    if (e.target.closest('[data-orgao-toggle]')) return;
    var node = row.closest('.orgao-node');
    if (!node) return;
    var id = node.getAttribute('data-id');
    if (id) {
      history.replaceState(null, '', '#orgao-' + id);
      highlightFromHash();
    }
  });
})();
