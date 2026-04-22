/**
 * Definição declarativa dos steps do tutorial.
 *
 * Botões padrão por tipo de step:
 *   - Intermediário : [Pular seção (skip), Próximo (next)]
 *   - Último da seção: [Pular seção (skip), Próxima seção → (next-section)]
 *   - Último de tudo : [Encerrar (complete)]
 *
 * "Pular seção" e "Próxima seção" disparam goToNextSection() no runner,
 * que navega automaticamente para a seção seguinte sem passar pela tela de menu.
 */

var _skip  = { text: 'Pular seção', action: 'skip', classes: 'shepherd-button-secondary' };
var _next  = { text: 'Próximo →', action: 'next' };
var _prev  = { text: '← Voltar', action: 'back', classes: 'shepherd-button-secondary' };
var _nextSection = { text: 'Próxima seção →', action: 'next-section' };
var _finish = { text: 'Concluir tutorial', action: 'complete' };

window.TUTORIAL_SECTIONS = {

  /* ── 1. Criar projeto ────────────────────────────────────────────── */
  criar_projeto: {
    label: 'Criar projeto',
    startUrl: '/dashboard',
    steps: [
      {
        pagePattern: '/dashboard',
        id: 'cp-welcome',
        title: '1/5 · Criar projeto',
        text: 'Clique em <strong>Novo Projeto</strong> para abrir o formulário de criação.',
        attachTo: { element: '.dashboard-new-project-btn', on: 'bottom' },
        advanceOn: { selector: '.dashboard-new-project-btn', event: 'click' },
        buttons: [_skip],
      },
      {
        pagePattern: '/dashboard',
        id: 'cp-titulo',
        title: '1/5 · Criar projeto',
        text: 'Preencha o <strong>título</strong> do projeto. Use um nome claro e descritivo.',
        attachTo: { element: '#project_titulo', on: 'bottom' },
        buttons: [_skip, _next],
      },
      {
        pagePattern: '/dashboard',
        id: 'cp-area',
        title: '1/5 · Criar projeto',
        text: 'Selecione a <strong>área responsável</strong> pelo projeto.',
        attachTo: { element: '#project_area_responsavel', on: 'bottom' },
        buttons: [_skip, _prev, _next],
      },
      {
        pagePattern: '/dashboard',
        id: 'cp-submit',
        title: '1/5 · Criar projeto',
        text: 'Preencha os demais campos que quiser e clique em <strong>Adicionar Projeto</strong>. Você será redirecionado para a página do projeto criado.',
        attachTo: { element: '#addProjectModal .btn-primary', on: 'top' },
        buttons: [_skip, _prev, _next],
      },
      {
        pagePattern: '/project/',
        id: 'cp-done',
        title: '1/5 · Criar projeto',
        text: 'Projeto criado! Aqui você vê todos os detalhes, etapas e tarefas vinculadas.',
        attachTo: { element: 'h1', on: 'bottom' },
        buttons: [_skip, _nextSection],
      },
    ],
  },

  /* ── 2. Explorar projeto ─────────────────────────────────────────── */
  explorar_projeto: {
    label: 'Explorar projeto',
    startUrl: '/project/',
    steps: [
      {
        pagePattern: '/project/',
        id: 'ep-overview',
        title: '2/5 · Explorar projeto',
        text: 'Esta é a página do projeto. Aqui você acompanha status, datas e objetivos.',
        attachTo: { element: 'h1', on: 'bottom' },
        buttons: [_skip, _next],
      },
      {
        pagePattern: '/project/',
        id: 'ep-etapas',
        title: '2/5 · Explorar projeto',
        text: 'A seção de <strong>etapas</strong> mostra o cronograma. Cada etapa pode ser marcada como iniciada ou concluída.',
        attachTo: { element: '.etapas-section, #etapas, [data-etapas]', on: 'top' },
        buttons: [_skip, _prev, _next],
      },
      {
        pagePattern: '/project/',
        id: 'ep-tarefas-link',
        title: '2/5 · Explorar projeto',
        text: 'Use o link <strong>Tarefas</strong> para ver e gerenciar as tarefas deste projeto.',
        attachTo: { element: 'a[href*="tarefas"]', on: 'bottom' },
        buttons: [_skip, _prev, _nextSection],
      },
    ],
  },

  /* ── 3. Criar etapa ──────────────────────────────────────────────── */
  criar_etapa: {
    label: 'Criar etapa',
    startUrl: '/project/',
    steps: [
      {
        pagePattern: '/project/',
        id: 'ce-intro',
        title: '3/5 · Criar etapa',
        text: 'Etapas representam as fases do projeto. Vamos adicionar uma nova.',
        attachTo: { element: '.etapas-section, #etapas, [data-etapas]', on: 'top' },
        buttons: [_skip, _next],
      },
      {
        pagePattern: '/project/',
        id: 'ce-add-btn',
        title: '3/5 · Criar etapa',
        text: 'Clique em <strong>+ Adicionar Etapa</strong> para abrir o formulário.',
        attachTo: { element: '.add-etapa-btn, [data-add-etapa], a[href*="etapa/add"]', on: 'bottom' },
        advanceOn: { selector: '.add-etapa-btn, [data-add-etapa], a[href*="etapa/add"]', event: 'click' },
        buttons: [_skip, _prev],
      },
      {
        pagePattern: '/etapa/',
        id: 'ce-form',
        title: '3/5 · Criar etapa',
        text: 'Preencha a <strong>descrição</strong> e, se quiser, as datas e o responsável.',
        attachTo: { element: '#descricao, textarea[name="descricao"]', on: 'bottom' },
        buttons: [_skip, _next],
      },
      {
        pagePattern: '/etapa/',
        id: 'ce-save',
        title: '3/5 · Criar etapa',
        text: 'Clique em <strong>Salvar</strong> para criar a etapa.',
        attachTo: { element: 'button[type="submit"]', on: 'top' },
        buttons: [_skip, _prev, _next],
      },
      {
        pagePattern: '/project/',
        id: 'ce-done',
        title: '3/5 · Criar etapa',
        text: 'Etapa criada! Clique nos ícones ao lado de cada etapa para marcá-la como iniciada ou concluída.',
        attachTo: { element: '.etapas-section, #etapas, [data-etapas]', on: 'top' },
        buttons: [_skip, _nextSection],
      },
    ],
  },

  /* ── 4. Criar tarefa ─────────────────────────────────────────────── */
  criar_tarefa: {
    label: 'Criar tarefa',
    startUrl: '/tarefas',
    steps: [
      {
        pagePattern: '/tarefas',
        id: 'ct-intro',
        title: '4/5 · Criar tarefa',
        text: 'Aqui ficam todas as tarefas — independentes ou vinculadas a projetos. Vamos criar uma.',
        attachTo: { element: '.add-task-btn, [data-add-task], button[data-bs-target*="tarefa"]', on: 'bottom' },
        buttons: [_skip, _next],
      },
      {
        pagePattern: '/tarefas',
        id: 'ct-descricao',
        title: '4/5 · Criar tarefa',
        text: 'Preencha a <strong>descrição</strong> da tarefa. Seja específico sobre o que precisa ser feito.',
        attachTo: { element: 'textarea[name="descricao"], input[name="descricao"]', on: 'bottom' },
        buttons: [_skip, _prev, _next],
      },
      {
        pagePattern: '/tarefas',
        id: 'ct-status',
        title: '4/5 · Criar tarefa',
        text: 'Após criar, você pode alterar o status: <em>Não iniciada</em>, <em>Em andamento</em> ou <em>Finalizada</em>.',
        attachTo: { element: 'select[name="status"]', on: 'bottom' },
        buttons: [_skip, _prev, _nextSection],
      },
    ],
  },

  /* ── 5. Navegar pelo app ─────────────────────────────────────────── */
  navegar: {
    label: 'Navegar pelo app',
    startUrl: '/dashboard',
    steps: [
      {
        pagePattern: '/dashboard',
        id: 'nav-dashboard',
        title: '5/5 · Navegar pelo app',
        text: 'O <strong>dashboard</strong> resume seus projetos e tarefas. É sua página inicial.',
        attachTo: { element: '.dashboard-kpi-row, .dashboard-welcome-strip', on: 'bottom' },
        buttons: [_next],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-topnav',
        title: '5/5 · Navegar pelo app',
        text: 'Use os ícones do menu superior para acessar Projetos, Tarefas e Calendário.',
        attachTo: { element: '.app-nav-icons', on: 'bottom' },
        buttons: [_prev, _next],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-search',
        title: '5/5 · Navegar pelo app',
        text: 'Use a <strong>busca global</strong> para encontrar qualquer projeto, etapa ou tarefa rapidamente.',
        attachTo: { element: '.app-global-search', on: 'bottom' },
        buttons: [_prev, _next],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-notifications',
        title: '5/5 · Navegar pelo app',
        text: 'O <strong>sino</strong> exibe notificações sobre tarefas atribuídas a você e mudanças de status.',
        attachTo: { element: '.app-notifications-menu', on: 'bottom' },
        buttons: [_prev, _next],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-tutorial-icon',
        title: '5/5 · Navegar pelo app',
        text: 'Este ícone reinicia o tutorial a qualquer momento. Você pode refazer quantas vezes quiser.',
        attachTo: { element: '.app-tutorial-link', on: 'bottom' },
        buttons: [_prev, _finish],
      },
    ],
  },
};
