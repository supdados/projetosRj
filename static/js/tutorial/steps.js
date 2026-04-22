/**
 * Definição declarativa dos steps do tutorial.
 *
 * Cada step tem:
 *   pagePattern  — prefixo de URL para filtrar quando mostrar o step
 *   id           — identificador único
 *   text         — corpo do tooltip (HTML)
 *   attachTo     — { element: seletor CSS, on: posição }
 *   advanceOn    — { selector, event } para avançar ao interagir com o elemento real
 *   waitMs       — delay em ms antes de mostrar (usado após animações)
 *   buttons      — array de { text, action, classes? }
 *
 * Ações disponíveis: next | back | skip | next-section | complete
 * "skip" e "next-section" são equivalentes — navegam para a próxima seção.
 *
 * O título dinâmico ("Seção · N/M") é injetado pelo runner.js.
 * Os títulos aqui são apenas o nome da seção.
 */

var _skip        = { text: 'Pular seção', action: 'skip',         classes: 'shepherd-button-secondary' };
var _next        = { text: 'Próximo →',   action: 'next' };
var _prev        = { text: '← Voltar',    action: 'back',         classes: 'shepherd-button-secondary' };
var _nextSection = { text: 'Próxima seção →', action: 'next-section' };
var _finish      = { text: 'Concluir',    action: 'complete' };

window.TUTORIAL_SECTIONS = {

  /* ── 1. Criar projeto ─────────────────────────────────────────────
     Todos os steps no dashboard (/dashboard).
     Após o submit do modal, Flask redireciona para /project/<id>.
     O step cp-done está em /project/ — aparece automaticamente após redirect.
  ──────────────────────────────────────────────────────────────────── */
  criar_projeto: {
    label: 'Criar projeto',
    startUrl: '/dashboard',
    steps: [
      {
        pagePattern: '/dashboard',
        id: 'cp-welcome',
        text: 'Clique em <strong>Novo Projeto</strong> para abrir o formulário de criação.',
        attachTo: { element: '.dashboard-new-project-btn', on: 'bottom' },
        advanceOn: { selector: '.dashboard-new-project-btn', event: 'click' },
        buttons: [_skip],
      },
      {
        pagePattern: '/dashboard',
        id: 'cp-titulo',
        text: 'Preencha o <strong>título</strong> do projeto — use um nome claro e descritivo.',
        attachTo: { element: '#project_titulo', on: 'bottom' },
        waitMs: 400,
        buttons: [_skip, _next],
      },
      {
        pagePattern: '/dashboard',
        id: 'cp-area',
        text: 'Selecione a <strong>área responsável</strong> pelo projeto.',
        attachTo: { element: '#project_area_responsavel', on: 'bottom' },
        buttons: [_skip, _prev, _next],
      },
      {
        pagePattern: '/dashboard',
        id: 'cp-submit',
        text: 'Preencha os campos que quiser e clique em <strong>Criar Projeto</strong> para salvar. Você será redirecionado para a página do projeto.',
        attachTo: { element: '#createProjectSubmitBtn', on: 'top' },
        advanceOn: { selector: '#createProjectSubmitBtn', event: 'click' },
        buttons: [_skip, _prev],
      },
      {
        pagePattern: '/project/',
        id: 'cp-done',
        text: 'Projeto criado! Aqui você acompanha status, datas, objetivos e todas as etapas e tarefas vinculadas.',
        attachTo: { element: 'h1', on: 'bottom' },
        buttons: [_skip, _nextSection],
      },
    ],
  },

  /* ── 2. Criar etapa ───────────────────────────────────────────────
     Todos os steps em /project/<id> — a criação é inline, sem troca de página.
     Fluxo:
       ce-intro     → visão geral das etapas
       ce-add-btn   → usuário CLICA no botão real (#btnOpenInlineEtapaAdd)
                       → advanceOn dispara → próximo step (waitMs espera o form aparecer)
       ce-form      → destaque do textarea inline
       ce-save-hint → instrução para salvar; usuário clica no ✓ real
                       → form submete → page reload
       ce-done      → aparece após o reload (global step já passou ce-save-hint)
  ──────────────────────────────────────────────────────────────────── */
  criar_etapa: {
    label: 'Criar etapa',
    startUrl: '/project/',
    steps: [
      {
        pagePattern: '/project/',
        id: 'ce-intro',
        text: 'Etapas representam as <strong>fases do projeto</strong>. Você pode definir datas, responsáveis e acompanhar o progresso de cada uma.',
        attachTo: { element: 'section.etapa-list', on: 'top' },
        buttons: [_skip, _next],
      },
      {
        pagePattern: '/project/',
        id: 'ce-add-btn',
        text: 'Clique no botão <strong>Adicionar Etapa</strong> para abrir o formulário inline.',
        attachTo: { element: '#btnOpenInlineEtapaAdd', on: 'bottom' },
        advanceOn: { selector: '#btnOpenInlineEtapaAdd', event: 'click' },
        buttons: [_skip, _prev],
      },
      {
        pagePattern: '/project/',
        id: 'ce-form',
        text: 'Digite a <strong>descrição</strong> da etapa. Você também pode definir datas e responsável.',
        attachTo: { element: '#etapa_inline_descricao', on: 'top' },
        waitMs: 500,
        buttons: [_skip, _next],
      },
      {
        pagePattern: '/project/',
        id: 'ce-save-hint',
        text: 'Clique no ícone <strong>✓</strong> para salvar a etapa. O tutorial retomará automaticamente.',
        attachTo: { element: '#btnSubmitInlineEtapaAdd', on: 'left' },
        buttons: [_skip],
      },
      {
        pagePattern: '/project/',
        id: 'ce-done',
        text: 'Etapa criada com sucesso! Ela aparece na lista abaixo. Você pode adicionar quantas etapas quiser.',
        attachTo: { element: 'section.etapa-list', on: 'top' },
        buttons: [_skip, _nextSection],
      },
    ],
  },

  /* ── 3. Explorar projeto ──────────────────────────────────────────
     Vem DEPOIS de criar etapa, então o projeto de demo já tem etapas.
     Mostra o que existe — não cria nada novo.
  ──────────────────────────────────────────────────────────────────── */
  explorar_projeto: {
    label: 'Explorar projeto',
    startUrl: '/project/',
    steps: [
      {
        pagePattern: '/project/',
        id: 'ep-overview',
        text: 'Esta é a <strong>página do projeto</strong>. Aqui você acompanha status, datas, objetivos e indicadores.',
        attachTo: { element: 'h1', on: 'bottom' },
        buttons: [_skip, _next],
      },
      {
        pagePattern: '/project/',
        id: 'ep-etapas',
        text: 'Na seção de <strong>Etapas</strong> você vê o cronograma. Clique nos ícones de cada etapa para marcá-la como iniciada ou concluída.',
        attachTo: { element: 'section.etapa-list', on: 'top' },
        buttons: [_skip, _prev, _next],
      },
      {
        pagePattern: '/project/',
        id: 'ep-add-etapa-btn',
        text: 'O botão <strong>Adicionar Etapa</strong> cria uma nova fase no projeto, de forma inline — sem sair desta página.',
        attachTo: { element: '#btnOpenInlineEtapaAdd', on: 'bottom' },
        buttons: [_skip, _prev, _nextSection],
      },
    ],
  },

  /* ── 4. Criar tarefa ──────────────────────────────────────────────
     Hub de tarefas em /tarefas
  ──────────────────────────────────────────────────────────────────── */
  criar_tarefa: {
    label: 'Criar tarefa',
    startUrl: '/tarefas',
    steps: [
      {
        pagePattern: '/tarefas',
        id: 'ct-intro',
        text: 'O <strong>hub de tarefas</strong> reúne todas as tarefas — independentes ou vinculadas a projetos.',
        attachTo: { element: '.app-page-shell, main', on: 'bottom' },
        buttons: [_skip, _next],
      },
      {
        pagePattern: '/tarefas',
        id: 'ct-nav',
        text: 'Use a <strong>barra lateral</strong> ou o botão de nova tarefa para criar e filtrar tarefas por status, prioridade ou projeto.',
        buttons: [_skip, _prev, _nextSection],
      },
    ],
  },

  /* ── 5. Navegar pelo app ──────────────────────────────────────────
     Dashboard
  ──────────────────────────────────────────────────────────────────── */
  navegar: {
    label: 'Navegar pelo app',
    startUrl: '/dashboard',
    steps: [
      {
        pagePattern: '/dashboard',
        id: 'nav-dashboard',
        text: 'O <strong>dashboard</strong> resume seus projetos e tarefas. É sua página inicial.',
        attachTo: { element: '.dashboard-kpi-row, .dashboard-welcome-strip', on: 'bottom' },
        buttons: [_next],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-topnav',
        text: 'Use os <strong>ícones do menu</strong> para acessar Projetos, Tarefas e Calendário.',
        attachTo: { element: '.app-nav-icons', on: 'bottom' },
        buttons: [_prev, _next],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-search',
        text: 'Use a <strong>busca global</strong> para encontrar qualquer projeto, etapa ou tarefa rapidamente.',
        attachTo: { element: '.app-global-search', on: 'bottom' },
        buttons: [_prev, _next],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-notifications',
        text: 'O <strong>sino</strong> exibe notificações sobre tarefas atribuídas a você e mudanças de status.',
        attachTo: { element: '.app-notifications-menu', on: 'bottom' },
        buttons: [_prev, _next],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-fim',
        text: 'Tutorial concluído! Clique no ícone de graduação a qualquer momento para refazê-lo.',
        attachTo: { element: '.app-tutorial-link', on: 'bottom' },
        buttons: [_prev, _finish],
      },
    ],
  },
};
