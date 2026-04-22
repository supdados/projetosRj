/**
 * Orquestrador do tutorial guiado (Shepherd.js).
 *
 * Estado no localStorage (sobrevive a page navigations):
 *   tutorial_section  — seção ativa (e.g. 'criar_projeto')
 *   tutorial_step     — próximo step global a mostrar (globalIdx + 1 do último step exibido)
 *
 * "Global index" = posição do step dentro de sectionDef.steps (não do subset filtrado pela página).
 * Armazenamos globalIdx + 1 para que, ao recarregar, steps já concluídos sejam pulados.
 */
(function () {
  'use strict';

  var SK_SECTION = 'projetosrj.tutorial.section';
  var SK_STEP    = 'projetosrj.tutorial.step';

  var SECTION_ORDER = [
    'criar_projeto',
    'criar_etapa',
    'criar_tarefa',
    'navegar',
  ];

  /* ── storage helpers ───────────────────────────────────────────── */

  function get(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; }
  }
  function set(key, val) {
    try { localStorage.setItem(key, String(val)); } catch (e) {}
  }
  function clearAll() {
    try { localStorage.removeItem(SK_SECTION); localStorage.removeItem(SK_STEP); } catch (e) {}
  }

  /* ── URL matching ──────────────────────────────────────────────── */

  function matchesPage(pattern) {
    var p = window.location.pathname;
    return p === pattern || p.startsWith(pattern);
  }

  /* ── server → localStorage sync ────────────────────────────────── */

  function syncSessionFromServer() {
    // Reset explícito (pause ou begin): zera tudo no localStorage
    if (window.__TUTORIAL_RESET__) {
      clearAll();
    }

    var serverSection = window.__TUTORIAL_SECTION__ || '';
    var storedSection = get(SK_SECTION, '');
    if (serverSection && serverSection !== storedSection) {
      set(SK_SECTION, serverSection);
      set(SK_STEP, '0');
    }
  }

  /* ── navegação entre seções ────────────────────────────────────── */

  function goToNextSection(currentSection) {
    var idx = SECTION_ORDER.indexOf(currentSection);
    clearAll();
    if (idx >= 0 && idx < SECTION_ORDER.length - 1) {
      var next = SECTION_ORDER[idx + 1];
      set(SK_SECTION, next);
      set(SK_STEP, '0');
      var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).getAttribute('content') || '';
      var form = document.createElement('form');
      form.method = 'POST';
      form.action  = '/tutorial/start';
      _addInput(form, 'csrf_token', csrf);
      _addInput(form, 'section', next);
      document.body.appendChild(form);
      form.submit();
    } else {
      // última seção concluída
      clearAll();
      window.location.href = '/tutorial/finish-redirect';
    }
  }

  function _addInput(form, name, value) {
    var el = document.createElement('input');
    el.type = 'hidden'; el.name = name; el.value = value;
    form.appendChild(el);
  }

  /* ── construção do tour ────────────────────────────────────────── */

  function buildTour(section, sectionDef, pageSteps) {
    var allSteps   = sectionDef.steps || [];
    var totalSteps = allSteps.length;

    var tour = new Shepherd.Tour({
      useModalOverlay: false,   // sem overlay bloqueante — usuário clica livremente
      defaultStepOptions: {
        cancelIcon: { enabled: true },
        scrollTo:   { behavior: 'smooth', block: 'center' },
        classes:    'tutorial-shepherd-step',
        popperOptions: { modifiers: [{ name: 'offset', options: { offset: [0, 14] } }] },
      },
    });

    pageSteps.forEach(function (stepDef) {
      var globalIdx  = allSteps.indexOf(stepDef);
      var stepNumber = globalIdx + 1;
      var sectionLabel = sectionDef.label || section;
      var dynamicTitle = sectionLabel + ' · ' + stepNumber + '/' + totalSteps;

      var buttons = _mapButtons(stepDef.buttons || [], section);

      var cfg = {
        id:      stepDef.id,
        title:   dynamicTitle,
        text:    stepDef.text,
        buttons: buttons,
        when: {
          // armazena o PRÓXIMO step a exibir
          show: function () { set(SK_STEP, String(globalIdx + 1)); },
        },
      };

      if (stepDef.attachTo && stepDef.attachTo.element) {
        cfg.attachTo = { element: stepDef.attachTo.element, on: stepDef.attachTo.on || 'bottom' };
      }

      if (stepDef.advanceOn) {
        cfg.advanceOn = stepDef.advanceOn;
      }

      if (stepDef.waitMs) {
        cfg.beforeShowPromise = (function (ms) {
          return function () { return new Promise(function (resolve) { setTimeout(resolve, ms); }); };
        })(stepDef.waitMs);
      }

      tour.addStep(cfg);
    });

    // Último page-step concluído normalmente → vai para a próxima seção
    tour.on('complete', function () { goToNextSection(section); });

    // X fechado → pausa (mantém estado no servidor)
    tour.on('cancel', function () {
      fetch('/tutorial/pause', {
        method:  'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      }).catch(function () {});
    });

    return tour;
  }

  function _mapButtons(defs, section) {
    return defs.map(function (btn) {
      switch (btn.action) {
        case 'next':
          return { text: btn.text, action: function () { return this.next(); }, classes: btn.classes || '' };
        case 'back':
          return { text: btn.text, action: function () { return this.back(); }, classes: btn.classes || '' };
        case 'complete':
          return { text: btn.text, action: function () { return this.complete(); }, classes: btn.classes || '' };
        case 'skip':
        case 'next-section':
          return { text: btn.text, action: function () { goToNextSection(section); }, classes: btn.classes || '' };
        default:
          return { text: btn.text, action: function () { return this.next(); }, classes: btn.classes || '' };
      }
    });
  }

  /* ── init ──────────────────────────────────────────────────────── */

  function init() {
    if (!window.__TUTORIAL_ACTIVE__) return;
    if (typeof Shepherd === 'undefined') return;

    syncSessionFromServer();

    var section    = get(SK_SECTION, '');
    var startGlobal = parseInt(get(SK_STEP, '0'), 10) || 0;

    var sectionDef = (window.TUTORIAL_SECTIONS || {})[section];
    if (!sectionDef) return;

    var allSteps = sectionDef.steps || [];

    // Steps que correspondem à página atual E ainda não foram concluídos
    var pageSteps = allSteps.filter(function (s, i) {
      return i >= startGlobal && matchesPage(s.pagePattern);
    });

    if (pageSteps.length === 0) return;

    document.addEventListener('DOMContentLoaded', function () {
      setTimeout(function () {
        try {
          var tour = buildTour(section, sectionDef, pageSteps);
          tour.start();
        } catch (e) {
          console.warn('[TutorialRunner] Erro:', e);
        }
      }, 350);
    });
  }

  window.TutorialRunner = { goToNextSection: goToNextSection };

  init();
})();
