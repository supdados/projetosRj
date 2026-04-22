/**
 * Orquestrador do tutorial guiado.
 *
 * Estado persistido (sobrevive a navegações entre páginas):
 *   localStorage['tutorial_section']  — seção ativa
 *   localStorage['tutorial_step']     — índice do step dentro dos steps da página atual
 *
 * Detecção de nova sessão:
 *   Se window.__TUTORIAL_SECTION__ (servidor) difere do localStorage, o usuário
 *   clicou no ícone de reinício → zera step e adota a seção do servidor.
 */
(function () {
  'use strict';

  var STORAGE_KEY_SECTION = 'projetosrj.tutorial.section';
  var STORAGE_KEY_STEP    = 'projetosrj.tutorial.step';
  var SECTION_ORDER       = ['criar_projeto', 'explorar_projeto', 'criar_etapa', 'criar_tarefa', 'navegar'];

  function getStored(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; }
  }
  function setStored(key, val) {
    try { localStorage.setItem(key, String(val)); } catch (e) {}
  }
  function clearStored() {
    try {
      localStorage.removeItem(STORAGE_KEY_SECTION);
      localStorage.removeItem(STORAGE_KEY_STEP);
    } catch (e) {}
  }

  function matchesPage(pattern) {
    var path = window.location.pathname;
    return path === pattern || path.startsWith(pattern) || path.indexOf(pattern) !== -1;
  }

  // Navega para a próxima seção submetendo um formulário a /tutorial/start.
  // Se não houver próxima seção, encerra o tutorial.
  function goToNextSection(currentSection) {
    var idx = SECTION_ORDER.indexOf(currentSection);
    clearStored();
    if (idx >= 0 && idx < SECTION_ORDER.length - 1) {
      var nextSection = SECTION_ORDER[idx + 1];
      setStored(STORAGE_KEY_SECTION, nextSection);
      var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).getAttribute('content') || '';
      var form = document.createElement('form');
      form.method = 'POST';
      form.action = '/tutorial/start';
      var csrfInput = document.createElement('input');
      csrfInput.type = 'hidden'; csrfInput.name = 'csrf_token'; csrfInput.value = csrf;
      var sectionInput = document.createElement('input');
      sectionInput.type = 'hidden'; sectionInput.name = 'section'; sectionInput.value = nextSection;
      form.appendChild(csrfInput);
      form.appendChild(sectionInput);
      document.body.appendChild(form);
      form.submit();
    } else {
      // Última seção concluída → encerrar
      _postToServer('/tutorial/finish', function () {
        window.location.href = '/tutorial/finish-redirect';
      });
    }
  }

  function _postToServer(path, callback) {
    var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).getAttribute('content') || '';
    fetch(path, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
    })
      .then(function () { if (callback) callback(); })
      .catch(function () { if (callback) callback(); });
  }

  function buildShepherdTour(section, pageSteps) {
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
        switch (btn.action) {
          case 'next':         return { text: btn.text, action: function () { return this.next(); }, classes: btn.classes || '' };
          case 'back':         return { text: btn.text, action: function () { return this.back(); }, classes: btn.classes || '' };
          case 'complete':     return { text: btn.text, action: function () { return this.complete(); }, classes: btn.classes || '' };
          case 'skip':         return { text: btn.text, action: function () { goToNextSection(section); }, classes: btn.classes || '' };
          case 'next-section': return { text: btn.text, action: function () { goToNextSection(section); }, classes: btn.classes || '' };
          default:             return { text: btn.text, action: function () { return this.next(); }, classes: btn.classes || '' };
        }
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

    // Último step da página concluído → avança para próxima seção automaticamente
    tour.on('complete', function () {
      goToNextSection(section);
    });

    // X (cancelar) → pausa o tutorial (mantém sessão ativa no servidor, apenas para shepherd)
    tour.on('cancel', function () {
      _postToServer('/tutorial/pause');
    });

    return tour;
  }

  function init() {
    if (!window.__TUTORIAL_ACTIVE__) return;
    if (typeof Shepherd === 'undefined') return;

    var serverSection = window.__TUTORIAL_SECTION__ || '';
    var storedSection = getStored(STORAGE_KEY_SECTION, '');

    // Nova sessão detectada (ícone clicado novamente) → zera progresso
    if (serverSection && serverSection !== storedSection) {
      setStored(STORAGE_KEY_SECTION, serverSection);
      setStored(STORAGE_KEY_STEP, '0');
    }

    var section   = getStored(STORAGE_KEY_SECTION, serverSection);
    var startStep = parseInt(getStored(STORAGE_KEY_STEP, '0'), 10) || 0;

    var sectionDef = (window.TUTORIAL_SECTIONS || {})[section];
    if (!sectionDef) return;

    var pageSteps = (sectionDef.steps || []).filter(function (s) { return matchesPage(s.pagePattern); });
    if (pageSteps.length === 0) return;

    if (startStep >= pageSteps.length) startStep = 0;

    document.addEventListener('DOMContentLoaded', function () {
      setTimeout(function () {
        try {
          var tour = buildShepherdTour(section, pageSteps);
          tour.start();
          // Avança silenciosamente até o step salvo
          for (var i = 0; i < startStep; i++) { tour.next(); }
        } catch (e) {
          console.warn('[TutorialRunner] Erro ao iniciar Shepherd:', e);
        }
      }, 400);
    });
  }

  window.TutorialRunner = { goToNextSection: goToNextSection };

  init();
})();
