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

var _skip            = { text: 'Pular seção', action: 'skip',         classes: 'shepherd-button-secondary' };
var _next            = { text: 'Próximo →',   action: 'next' };
var _prev            = { text: '← Voltar',    action: 'back',         classes: 'shepherd-button-secondary' };
var _nextSection     = { text: 'Próxima seção →', action: 'next-section' };
var _finish          = { text: 'Concluir',    action: 'complete' };

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
        text: 'Selecione o <strong>órgão responsável</strong> pelo projeto.',
        attachTo: { element: '#project_orgao_id', on: 'bottom' },
        buttons: [_skip, _prev, _next],
      },
      {
        pagePattern: '/dashboard',
        id: 'cp-submit',
        text: 'Preencha os campos que quiser e clique em <strong>Criar Projeto</strong> para salvar. Você será redirecionado para a página do projeto.',
        attachTo: { element: '#createProjectSubmitBtn', on: 'top' },
        // Sem advanceOn: o submit do form já navega para /project/<id>
        // e o próximo step (cp-done) aparece automaticamente lá.
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
     Tour informacional. Apresenta a área de etapas, o botão de criação
     e as colunas da tabela. Não dirige o fluxo de save — o usuário
     experimenta criar etapas por conta própria depois.
  ──────────────────────────────────────────────────────────────────── */
  criar_etapa: {
    label: 'Criar etapa',
    startUrl: '/project/',
    steps: [
      {
        pagePattern: '/project/',
        id: 'ce-overview',
        text: 'As <strong>etapas</strong> dividem o projeto em partes com início, fim, responsável e status próprios. É aqui embaixo que elas ficam listadas.',
        attachTo: { element: 'section.etapa-list', on: 'top' },
        buttons: [_skip, _next],
      },
      {
        pagePattern: '/project/',
        id: 'ce-add-btn',
        text: 'Para criar uma etapa, clique em <strong>Adicionar Etapa</strong>. Uma linha editável aparece no final da lista — é só preencher a descrição e clicar em confirmar (<i class="fas fa-check"></i>) ou pressionar Enter. Datas, responsável e status são opcionais e podem ser ajustados depois.',
        attachTo: { element: '#btnOpenInlineEtapaAdd', on: 'bottom' },
        buttons: [_skip, _prev, _next],
      },
      {
        pagePattern: '/project/',
        id: 'ce-done',
        text: 'Pronto! Crie quantas etapas precisar. Você pode editar cada campo direto na tabela, reordenar arrastando, iniciar/concluir com os botões de status e acompanhar o progresso conforme avançam.',
        attachTo: { element: 'section.etapa-list', on: 'top' },
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
        text: 'O <strong>hub de tarefas</strong> reúne todas as tarefas — independentes ou vinculadas a projetos. Use-o para acompanhar tudo em um só lugar.',
        // Sem attachTo: step centralizado para apresentação do hub
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
