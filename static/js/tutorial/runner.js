/**
 * Orquestrador do tutorial guiado.
 * Lê a seção e step do localStorage, filtra steps pela página atual
 * e inicializa o Shepherd.js.
 *
 * Estado persistido (sobrevive a navegações):
 *   localStorage['tutorial_section']  — nome da seção ativa
 *   localStorage['tutorial_step']     — índice do step dentro dos steps da página atual
 */
(function () {
  'use strict';

  var STORAGE_KEY_SECTION = 'projetosrj.tutorial.section';
  var STORAGE_KEY_STEP    = 'projetosrj.tutorial.step';

  function getStored(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; }
  }
  function setStored(key, val) {
    try { localStorage.setItem(key, val); } catch (e) {}
  }
  function clearStored() {
    try { localStorage.removeItem(STORAGE_KEY_SECTION); localStorage.removeItem(STORAGE_KEY_STEP); } catch (e) {}
  }

  function matchesPage(pattern) {
    var path = window.location.pathname;
    return path === pattern || path.startsWith(pattern) || path.indexOf(pattern) !== -1;
  }

  function buildShepherdTour(section, pageSteps, startIndex) {
    var tour = new Shepherd.Tour({
      useModalOverlay: true,
      defaultStepOptions: {
        cancelIcon: { enabled: true },
        scrollTo: { behavior: 'smooth', block: 'center' },
        classes: 'tutorial-shepherd-step',
      },
    });

    pageSteps.forEach(function (stepDef, i) {
      var buttons = (stepDef.buttons || []).map(function (btn) {
        if (btn.action === 'next')         return { text: btn.text, action: function () { return this.next(); }, classes: btn.classes || '' };
        if (btn.action === 'back')         return { text: btn.text, action: function () { return this.back(); }, classes: btn.classes || '' };
        if (btn.action === 'complete')     return { text: btn.text, action: function () { return this.complete(); }, classes: btn.classes || '' };
        if (btn.action === 'skip')         return { text: btn.text, action: function () { window.TutorialRunner.skipSection(); }, classes: btn.classes || '' };
        if (btn.action === 'next-section') return { text: btn.text, action: function () { window.TutorialRunner.goToNextSection(section); }, classes: btn.classes || '' };
        return { text: btn.text, action: function () { return this.next(); }, classes: btn.classes || '' };
      });

      var stepConfig = {
        id: stepDef.id,
        title: stepDef.title,
        text: stepDef.text,
        buttons: buttons,
        when: {
          show: function () { setStored(STORAGE_KEY_STEP, i); },
        },
      };

      if (stepDef.attachTo && stepDef.attachTo.element) {
        stepConfig.attachTo = { element: stepDef.attachTo.element, on: stepDef.attachTo.on || 'bottom' };
      }
      if (stepDef.advanceOn) {
        stepConfig.advanceOn = stepDef.advanceOn;
      }

      tour.addStep(stepConfig);
    });

    tour.on('complete', function () {
      clearStored();
      _postToServer('/tutorial/finish');
    });

    tour.on('cancel', function () {
      _postToServer('/tutorial/pause');
    });

    return tour;
  }

  function _postToServer(path) {
    var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).getAttribute('content') || '';
    fetch(path, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken, 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
    }).catch(function () {});
  }

  function init() {
    if (!window.__TUTORIAL_ACTIVE__) return;
    if (typeof Shepherd === 'undefined') return;

    var section = getStored(STORAGE_KEY_SECTION, window.__TUTORIAL_SECTION__ || '');
    var startStep = parseInt(getStored(STORAGE_KEY_STEP, '0'), 10) || 0;

    var sections = window.TUTORIAL_SECTIONS || {};
    var sectionDef = sections[section];
    if (!sectionDef) return;

    var pageSteps = (sectionDef.steps || []).filter(function (s) { return matchesPage(s.pagePattern); });
    if (pageSteps.length === 0) return;

    // Clamp startStep dentro dos steps disponíveis para esta página
    if (startStep >= pageSteps.length) startStep = 0;

    document.addEventListener('DOMContentLoaded', function () {
      // Pequeno delay para que modais/overlays terminem de abrir
      setTimeout(function () {
        try {
          var tour = buildShepherdTour(section, pageSteps, startStep);
          tour.start();
          if (startStep > 0) {
            for (var i = 0; i < startStep; i++) { tour.next(); }
          }
        } catch (e) {
          console.warn('[TutorialRunner] Erro ao iniciar Shepherd:', e);
        }
      }, 400);
    });
  }

  window.TutorialRunner = {
    skipSection: function () {
      clearStored();
      _postToServer('/tutorial/pause');
      window.location.href = '/tutorial';
    },
    goToNextSection: function (currentSection) {
      var order = ['criar_projeto', 'explorar_projeto', 'criar_etapa', 'criar_tarefa', 'navegar'];
      var idx = order.indexOf(currentSection);
      clearStored();
      if (idx >= 0 && idx < order.length - 1) {
        var nextSection = order[idx + 1];
        setStored(STORAGE_KEY_SECTION, nextSection);
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = '/tutorial/start';
        var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).getAttribute('content') || '';
        var csrfInput = document.createElement('input');
        csrfInput.type = 'hidden'; csrfInput.name = 'csrf_token'; csrfInput.value = csrfToken;
        var sectionInput = document.createElement('input');
        sectionInput.type = 'hidden'; sectionInput.name = 'section'; sectionInput.value = nextSection;
        form.appendChild(csrfInput);
        form.appendChild(sectionInput);
        document.body.appendChild(form);
        form.submit();
      } else {
        _postToServer('/tutorial/finish');
        window.location.href = '/tutorial';
      }
    },
    setSection: function (section) {
      setStored(STORAGE_KEY_SECTION, section);
      setStored(STORAGE_KEY_STEP, '0');
    },
  };

  init();
})();
