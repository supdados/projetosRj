/**
 * Definição declarativa de todos os steps do tutorial.
 * Cada seção é uma lista de steps com `pagePattern` para filtragem por rota.
 * O runner usa `pagePattern` para mostrar apenas os steps da página atual.
 */
window.TUTORIAL_SECTIONS = {
  criar_projeto: {
    label: 'Criar projeto',
    startUrl: '/dashboard',
    steps: [
      {
        pagePattern: '/dashboard',
        id: 'cp-welcome',
        title: 'Criar um novo projeto',
        text: 'Para começar, clique no botão <strong>Novo Projeto</strong> no canto superior direito da tela.',
        attachTo: { element: '.dashboard-new-project-btn', on: 'bottom' },
        advanceOn: { selector: '.dashboard-new-project-btn', event: 'click' },
        buttons: [{ text: 'Pular seção', action: 'skip', classes: 'shepherd-button-secondary' }],
      },
      {
        pagePattern: '/dashboard',
        id: 'cp-titulo',
        title: 'Nome do projeto',
        text: 'Preencha o título do projeto. Use um nome claro e descritivo.',
        attachTo: { element: '#project_titulo', on: 'bottom' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/dashboard',
        id: 'cp-area',
        title: 'Área responsável',
        text: 'Selecione a área responsável pelo projeto.',
        attachTo: { element: '#project_area_responsavel', on: 'bottom' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/dashboard',
        id: 'cp-submit',
        title: 'Salvar projeto',
        text: 'Quando preencher os campos desejados, clique em <strong>Adicionar Projeto</strong> para criar. Você será redirecionado para a página do projeto.',
        attachTo: { element: '#addProjectModal .btn-primary', on: 'top' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Entendido', action: 'complete' },
        ],
      },
      {
        pagePattern: '/project/',
        id: 'cp-done',
        title: 'Projeto criado!',
        text: 'Seu projeto foi criado. Aqui você vê todos os detalhes, etapas e tarefas vinculadas a ele.',
        attachTo: { element: '.page-hero-title, h1', on: 'bottom' },
        buttons: [
          { text: 'Encerrar', action: 'complete', classes: 'shepherd-button-secondary' },
          { text: 'Próxima seção →', action: 'next-section' },
        ],
      },
    ],
  },

  explorar_projeto: {
    label: 'Explorar projeto',
    startUrl: '/project/',
    steps: [
      {
        pagePattern: '/project/',
        id: 'ep-overview',
        title: 'Visão geral do projeto',
        text: 'Esta é a página principal do projeto. Aqui você vê o status, datas, objetivos e todas as etapas.',
        attachTo: { element: '.page-hero-title, h1', on: 'bottom' },
        buttons: [
          { text: 'Pular seção', action: 'skip', classes: 'shepherd-button-secondary' },
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/project/',
        id: 'ep-etapas',
        title: 'Etapas do projeto',
        text: 'A seção de etapas mostra o cronograma do projeto. Cada etapa pode ser marcada como iniciada ou concluída.',
        attachTo: { element: '.etapas-section, #etapas', on: 'top' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/project/',
        id: 'ep-tarefas-link',
        title: 'Tarefas vinculadas',
        text: 'Clique em <strong>Tarefas</strong> para ver e gerenciar as tarefas deste projeto.',
        attachTo: { element: 'a[href*="tarefas"]', on: 'bottom' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Encerrar seção', action: 'complete' },
        ],
      },
    ],
  },

  criar_etapa: {
    label: 'Criar etapa',
    startUrl: '/project/',
    steps: [
      {
        pagePattern: '/project/',
        id: 'ce-intro',
        title: 'Etapas do projeto',
        text: 'Etapas são as fases do seu projeto. Vamos adicionar uma nova etapa.',
        attachTo: { element: '.etapas-section, #etapas', on: 'top' },
        buttons: [
          { text: 'Pular seção', action: 'skip', classes: 'shepherd-button-secondary' },
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/project/',
        id: 'ce-add-btn',
        title: 'Adicionar etapa',
        text: 'Clique em <strong>+ Adicionar Etapa</strong> para abrir o formulário.',
        attachTo: { element: '.add-etapa-btn, [data-add-etapa]', on: 'bottom' },
        advanceOn: { selector: '.add-etapa-btn, [data-add-etapa]', event: 'click' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
        ],
      },
      {
        pagePattern: '/etapa/',
        id: 'ce-form',
        title: 'Formulário da etapa',
        text: 'Preencha a descrição, datas de início e fim, e o responsável pela etapa.',
        attachTo: { element: '#descricao, input[name="descricao"]', on: 'bottom' },
        buttons: [
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/etapa/',
        id: 'ce-save',
        title: 'Salvar etapa',
        text: 'Clique em <strong>Salvar</strong> para criar a etapa no projeto.',
        attachTo: { element: 'button[type="submit"], input[type="submit"]', on: 'top' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Entendido', action: 'complete' },
        ],
      },
      {
        pagePattern: '/project/',
        id: 'ce-done',
        title: 'Etapa criada!',
        text: 'A etapa aparece agora no cronograma do projeto. Você pode marcar etapas como iniciadas ou concluídas clicando nos ícones.',
        attachTo: { element: '.etapas-section, #etapas', on: 'top' },
        buttons: [
          { text: 'Encerrar', action: 'complete', classes: 'shepherd-button-secondary' },
          { text: 'Próxima seção →', action: 'next-section' },
        ],
      },
    ],
  },

  criar_tarefa: {
    label: 'Criar tarefa',
    startUrl: '/tarefas',
    steps: [
      {
        pagePattern: '/tarefas',
        id: 'ct-intro',
        title: 'Hub de tarefas',
        text: 'Aqui você gerencia todas as tarefas — independentes ou vinculadas a projetos. Vamos criar uma nova.',
        attachTo: { element: '.add-task-btn, [data-add-task], button[data-bs-target*="tarefa"]', on: 'bottom' },
        buttons: [
          { text: 'Pular seção', action: 'skip', classes: 'shepherd-button-secondary' },
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/tarefas',
        id: 'ct-descricao',
        title: 'Descrição da tarefa',
        text: 'Preencha a descrição da tarefa. Seja específico sobre o que precisa ser feito.',
        attachTo: { element: 'textarea[name="descricao"], input[name="descricao"]', on: 'bottom' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/tarefas',
        id: 'ct-status',
        title: 'Status da tarefa',
        text: 'Depois de criar, você pode alterar o status da tarefa: <em>Não iniciada</em>, <em>Em andamento</em> ou <em>Finalizada</em>.',
        attachTo: { element: 'select[name="status"]', on: 'bottom' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Encerrar seção', action: 'complete' },
        ],
      },
    ],
  },

  navegar: {
    label: 'Navegar pelo app',
    startUrl: '/dashboard',
    steps: [
      {
        pagePattern: '/dashboard',
        id: 'nav-dashboard',
        title: 'Dashboard',
        text: 'O dashboard mostra um resumo dos seus projetos, tarefas e indicadores. É a sua página inicial.',
        attachTo: { element: '.dashboard-kpi-row, .dashboard-welcome-strip', on: 'bottom' },
        buttons: [
          { text: 'Pular seção', action: 'skip', classes: 'shepherd-button-secondary' },
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-topnav',
        title: 'Navegação principal',
        text: 'Use os ícones do menu superior para navegar entre Projetos, Tarefas e Calendário.',
        attachTo: { element: '.app-nav-icons', on: 'bottom' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-search',
        title: 'Busca global',
        text: 'Use a barra de busca para encontrar qualquer projeto, etapa, tarefa ou evento rapidamente.',
        attachTo: { element: '.app-global-search', on: 'bottom' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-notifications',
        title: 'Notificações',
        text: 'O sino exibe notificações sobre tarefas atribuídas a você, mudanças de status e outros eventos.',
        attachTo: { element: '.app-notifications-menu', on: 'bottom' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Próximo', action: 'next' },
        ],
      },
      {
        pagePattern: '/dashboard',
        id: 'nav-tutorial-link',
        title: 'Este tutorial',
        text: 'Você pode revisitar qualquer seção do tutorial a qualquer momento pelo ícone <i class="fas fa-graduation-cap"></i> no menu.',
        attachTo: { element: '.app-tutorial-link', on: 'bottom' },
        buttons: [
          { text: 'Voltar', action: 'back', classes: 'shepherd-button-secondary' },
          { text: 'Concluir tutorial', action: 'complete' },
        ],
      },
    ],
  },
};
