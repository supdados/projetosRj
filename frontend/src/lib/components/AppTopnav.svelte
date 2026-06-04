<script lang="ts">
	/**
	 * Topnav do app shell: barra azul com brand + navegacao por icones +
	 * busca global LIVE + seletor de orgao em arvore + notificacoes + menu de
	 * conta/admin + theme toggle rolling.
	 *
	 * Visual e micro-interacoes portados de templates/partials/app_topnav.html
	 * (v4.5), das regras .app-topnav, .orgao-tree-* e .app-notifications-* de
	 * static/css/legacy/00-foundation.css + static/css/partials/orgao-tree-picker.css,
	 * e dos comportamentos de static/js/app-shell/{global-search,notifications,theme}.js
	 * e static/js/components/orgao-tree-picker.js.
	 *
	 * Fiacao base-aware (`$app/paths`), link ativo via `aria-current="page"`
	 * comparando `$page.url.pathname`, store de tema (`$theme`/`toggleTheme`) e o
	 * menu Admin acessivel ja existentes. A busca live vive em GlobalSearchBox; o
	 * escopo de orgao vive em `$lib/stores/orgaoScope`.
	 */
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import { theme, toggleTheme } from '$lib/stores/theme';
	import { orgaoScope, selectOrgaoScope } from '$lib/stores/orgaoScope';
	import { fetchOrgaoScopeTree } from '$lib/api/orgaos';
	import {
		fetchNotificacoes,
		marcarNotificacoesLidas
	} from '$lib/api/notifications';
	import GlobalSearchBox from '$lib/components/GlobalSearchBox.svelte';
	import type { User } from '$lib/types/entities';
	import type { OrgaoTreeNode } from '$lib/types/orgaoScope';
	import type { Notificacao } from '$lib/types/notifications';

	interface Props {
		user: User | null;
	}

	let { user }: Props = $props();

	interface NavLink {
		label: string;
		path: string;
		/** Classe Font Awesome do icone (presentacional, 1:1 do markup v4.5). */
		icon: string;
	}

	// Ordem do v4.5 (sem item "Busca" — a busca virou o campo live a direita).
	const navLinks: NavLink[] = [
		{ label: 'Inicio', path: '/dashboard', icon: 'fa-home' },
		{ label: 'Projetos', path: '/projetos', icon: 'fa-folder-open' },
		{ label: 'Tarefas', path: '/tarefas', icon: 'fa-tasks' },
		{ label: 'Pendentes', path: '/projetos/pendentes', icon: 'fa-exclamation-triangle' },
		{ label: 'Calendario', path: '/calendarios', icon: 'fa-calendar-alt' }
	];

	// Indicador unico (pilula branca) que DESLIZA entre os itens da nav. Um so
	// elemento persistente, posicionado por transform+width medindo o <a> ativo —
	// nao a dupla send/receive do crossfade. Por que: o crossfade remede AS DUAS
	// pontas depois do reflow; como o item ativo ganha rotulo e empurra os
	// vizinhos, o ponto de partida "saltava" antes de deslizar. Aqui a partida e a
	// posicao ATUAL real do indicador (transform anterior), entao ele vai direto de
	// um item ao outro. Detalhes em micro/docs/transicao-topnav.md.
	let navEl = $state<HTMLElement | null>(null);
	let pill = $state<{ x: number; w: number; ready: boolean }>({ x: 0, w: 0, ready: false });
	// Sem transicao no 1o posicionamento (senao desliza do x=0); liga depois.
	let pillSlides = $state(false);

	function measurePill(): void {
		if (!navEl) return;
		const activeEl = navEl.querySelector<HTMLElement>('a[aria-current="page"]');
		if (!activeEl) {
			pill = { ...pill, ready: false };
			return;
		}
		// rect relativo ao <nav> (robusto a offsetParent).
		const nav = navEl.getBoundingClientRect();
		const r = activeEl.getBoundingClientRect();
		pill = { x: r.left - nav.left, w: r.width, ready: true };
		if (!pillSlides) requestAnimationFrame(() => (pillSlides = true));
	}

	// Re-mede quando a rota muda (o rotulo do ativo expande -> larguras mudam). O
	// rAF garante medir DEPOIS do reflow, ja na geometria final.
	$effect(() => {
		pathname;
		requestAnimationFrame(measurePill);
	});

	// Acompanha mudancas de largura da viewport (quebra de layout reposiciona itens).
	$effect(() => {
		if (!navEl) return;
		const onResize = () => measurePill();
		window.addEventListener('resize', onResize);
		return () => window.removeEventListener('resize', onResize);
	});

	/**
	 * Considera ativo quando o pathname e o link em si ou um descendente dele
	 * (ex.: /projetos/123 ativa "Projetos"), evitando que "/projetos" tambem
	 * marque "Pendentes". O caminho mais especifico vence pelo prefixo exato.
	 */
	function isActive(linkPath: string, current: string): boolean {
		const target = `${base}${linkPath}`;
		if (current === target) return true;
		if (!current.startsWith(`${target}/`)) return false;
		// Nao marcar um link quando outro mais especifico cobre o path
		// (ex.: "/projetos" vs "/projetos/pendentes", "/admin/orgaos" vs
		// "/admin/orgaos/tipos"). Considera nav + admin para desambiguar.
		return ![...navLinks, ...adminLinks].some(
			(other) =>
				other.path !== linkPath &&
				other.path.startsWith(linkPath) &&
				(current === `${base}${other.path}` ||
					current.startsWith(`${base}${other.path}/`))
		);
	}

	const pathname = $derived($page.url.pathname);

	// Links do menu Admin (so renderizados quando user.is_admin === true).
	const adminLinks: NavLink[] = [
		{ label: 'Usuarios', path: '/admin/usuarios', icon: 'fa-users-cog' },
		{ label: 'Orgaos', path: '/admin/orgaos', icon: 'fa-sitemap' },
		{ label: 'Tipos de orgao', path: '/admin/orgaos/tipos', icon: 'fa-layer-group' },
		{ label: 'Templates', path: '/admin/templates', icon: 'fa-clone' }
	];

	// Dropdown acessivel: estado aberto + ativacao por teclado/aria.
	let adminOpen = $state(false);
	let adminMenuEl = $state<HTMLDivElement | null>(null);

	// Marca o botao "Admin" como ativo quando qualquer rota /admin/* esta aberta.
	const adminActive = $derived(
		pathname === `${base}/admin` || pathname.startsWith(`${base}/admin/`)
	);

	function closeAdmin(): void {
		adminOpen = false;
	}

	function toggleAdmin(): void {
		adminOpen = !adminOpen;
	}

	let adminToggleEl = $state<HTMLButtonElement | null>(null);

	/** Esc fecha o menu e devolve foco ao botao acionador. */
	function handleWindowKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			if (adminOpen) {
				closeAdmin();
				adminToggleEl?.focus();
			}
			if (orgaoOpen) {
				closeOrgao();
				orgaoToggleEl?.focus();
			}
			if (notifOpen) {
				closeNotif();
				notifToggleEl?.focus();
			}
		}
	}

	// ============================================================
	// Seletor de orgao em arvore (porte de orgao-tree-picker.js + .css)
	// Agora consome a ARVORE ANINHADA de GET /api/orgaos/escopo (api/orgaos.ts):
	// cada no traz `children` + flags (`is_user_orgao`/`is_user_ancestor`/`tipo`).
	// ============================================================
	let orgaoOpen = $state(false);
	let orgaoMenuEl = $state<HTMLDivElement | null>(null);
	let orgaoToggleEl = $state<HTMLButtonElement | null>(null);
	let orgaoFilter = $state('');
	let orgaoTree = $state<OrgaoTreeNode[]>([]);
	let orgaoLoaded = $state(false);
	/** IDs dos nos expandidos (chevron aberto). Vazio => recolhido. */
	let expandedOrgaos = $state<Set<number>>(new Set());

	/** Achata a arvore (DFS) para resolver labels e contar nos visiveis. */
	function flattenTree(nodes: OrgaoTreeNode[], out: OrgaoTreeNode[] = []): OrgaoTreeNode[] {
		for (const node of nodes) {
			out.push(node);
			if (node.children?.length) flattenTree(node.children, out);
		}
		return out;
	}

	const flatOrgaoNodes = $derived(flattenTree(orgaoTree));

	/** Mostra o seletor so quando ha mais de um orgao visivel (igual v4.5). */
	const hasOrgaoTree = $derived(flatOrgaoNodes.length > 0);

	/** Mostra a busca de filtro so quando vale a pena (admin / muitos orgaos). */
	const showOrgaoFilter = $derived(Boolean(user?.is_admin) || flatOrgaoNodes.length > 8);

	/** Rotulo do trigger: sigla selecionada ou "Todos os orgaos". */
	const orgaoTriggerLabel = $derived(
		$orgaoScope.selectedSigla ?? deriveSelectedSigla() ?? 'Todos os orgaos'
	);

	/** Tenta resolver a sigla a partir da arvore quando so temos o id persistido. */
	function deriveSelectedSigla(): string | null {
		if ($orgaoScope.selectedId === null) return null;
		const hit = flatOrgaoNodes.find((o) => o.id === $orgaoScope.selectedId);
		return hit?.sigla ?? null;
	}

	const orgaoQuery = $derived(orgaoFilter.trim().toLowerCase());
	const isFiltering = $derived(orgaoQuery.length > 0);

	/** Casa um no (ou qualquer descendente) contra o filtro textual. */
	function nodeMatchesFilter(node: OrgaoTreeNode, q: string): boolean {
		const sigla = (node.sigla ?? '').toLowerCase();
		const nome = (node.nome ?? '').toLowerCase();
		if (sigla.includes(q) || nome.includes(q)) return true;
		return (node.children ?? []).some((child) => nodeMatchesFilter(child, q));
	}

	/** Um no e visivel se ele ou um descendente casa o filtro (igual v4.5). */
	function nodeVisible(node: OrgaoTreeNode): boolean {
		if (!isFiltering) return true;
		return nodeMatchesFilter(node, orgaoQuery);
	}

	/**
	 * Estado de expansao efetivo de um no: ao filtrar, TUDO expande (igual
	 * applyFilter do v4.5); sem filtro, segue `expandedOrgaos`.
	 */
	function isExpanded(node: OrgaoTreeNode): boolean {
		if (isFiltering) return true;
		return expandedOrgaos.has(node.id);
	}

	function toggleExpand(node: OrgaoTreeNode): void {
		const next = new Set(expandedOrgaos);
		if (next.has(node.id)) next.delete(node.id);
		else next.add(node.id);
		expandedOrgaos = next;
	}

	/** Slug do tipo p/ a classe de cor do bullet (mesma normalizacao do v4.5). */
	function tipoSlug(tipo: string | null): string {
		if (!tipo) return '';
		return tipo
			.toLowerCase()
			.normalize('NFD')
			.replace(/[̀-ͯ]/g, '')
			.replace(/\s+/g, '-');
	}

	/**
	 * Abre o caminho ate o orgao do usuario (ou ate o selecionado) ao carregar,
	 * deixando o destaque visivel sem clique — espelha collapseAllExceptSelectedPath.
	 */
	function expandPathToHighlight(nodes: OrgaoTreeNode[]): Set<number> {
		const open = new Set<number>();
		const walk = (list: OrgaoTreeNode[]): boolean => {
			let onPath = false;
			for (const node of list) {
				const childOnPath = walk(node.children ?? []);
				const selfTarget =
					node.is_user_orgao ||
					node.is_user_ancestor ||
					node.id === $orgaoScope.selectedId;
				if (childOnPath) open.add(node.id);
				if (childOnPath || selfTarget) onPath = true;
			}
			return onPath;
		};
		walk(nodes);
		return open;
	}

	/** Carrega a arvore visivel de orgaos (uma unica vez). */
	async function loadOrgaoTree(): Promise<void> {
		if (orgaoLoaded) return;
		orgaoLoaded = true;
		try {
			const tree = await fetchOrgaoScopeTree();
			orgaoTree = tree;
			expandedOrgaos = expandPathToHighlight(tree);
		} catch {
			// Sem acesso/erro: deixa o seletor vazio (some quando nao ha arvore).
			orgaoTree = [];
		}
	}

	function closeOrgao(): void {
		orgaoOpen = false;
		orgaoFilter = '';
	}

	function toggleOrgao(): void {
		orgaoOpen = !orgaoOpen;
		if (orgaoOpen) void loadOrgaoTree();
	}

	function pickOrgao(node: OrgaoTreeNode | null): void {
		if (node === null) {
			selectOrgaoScope(null, null);
		} else {
			selectOrgaoScope(node.id, node.sigla ?? '');
		}
		closeOrgao();
	}

	// Carrega a arvore cedo (na montagem) para popular o trigger/label e o
	// gate `hasOrgaoTree` sem depender da primeira abertura do dropdown.
	void loadOrgaoTree();

	// ============================================================
	// Notificacoes (sino): GET /api/notificacoes + POST marcar-lidas (api/notifications.ts)
	// ============================================================
	let notifOpen = $state(false);
	let notifMenuEl = $state<HTMLDivElement | null>(null);
	let notifToggleEl = $state<HTMLButtonElement | null>(null);
	let notifItems = $state<Notificacao[]>([]);
	let notifUnread = $state(0);
	let notifLoading = $state(false);
	let notifError = $state(false);
	let notifLoadedOnce = $state(false);

	/** Texto do badge: contagem nao-lida, com teto "99+" (igual v4.5). */
	const notifBadgeText = $derived(notifUnread > 99 ? '99+' : String(notifUnread));

	/**
	 * Resolve icone FA por `event_type` (porte de resolveNotificationVisual do
	 * v4.5). Cobre delecao/finalizacao/atribuicao/comentario/projeto/tarefa.
	 */
	function notifIcon(eventType: string): string {
		const t = (eventType ?? '').toString().trim().toLowerCase();
		if (t.endsWith('_deleted') || t === 'task_deleted' || t === 'project_delete')
			return 'fa-trash-can';
		if (
			t === 'task_finalized' ||
			t === 'project_finalize' ||
			t === 'project_toggle_done'
		)
			return 'fa-check-circle';
		if (t === 'task_assignment' || t === 'task_item_assignment') return 'fa-user-check';
		if (t.startsWith('task_comment_') || t.startsWith('task_item_comment_'))
			return 'fa-comments';
		if (t.startsWith('project_')) return 'fa-folder-tree';
		if (t.startsWith('task_')) return 'fa-list-check';
		return 'fa-bell';
	}

	/** Tempo relativo em PT a partir de ISO 8601 (ex.: "há 2 dias"). */
	function relativeTime(iso: string | null): string {
		if (!iso) return '';
		const then = Date.parse(iso);
		if (Number.isNaN(then)) return '';
		const diffMs = Date.now() - then;
		const sec = Math.round(diffMs / 1000);
		if (sec < 45) return 'agora mesmo';
		const min = Math.round(sec / 60);
		if (min < 60) return `há ${min} min`;
		const hours = Math.round(min / 60);
		if (hours < 24) return `há ${hours} h`;
		const days = Math.round(hours / 24);
		if (days < 7) return `há ${days} dia${days > 1 ? 's' : ''}`;
		const weeks = Math.round(days / 7);
		if (weeks < 5) return `há ${weeks} semana${weeks > 1 ? 's' : ''}`;
		const months = Math.round(days / 30);
		if (months < 12) return `há ${months} ${months > 1 ? 'meses' : 'mês'}`;
		const years = Math.round(days / 365);
		return `há ${years} ano${years > 1 ? 's' : ''}`;
	}

	/**
	 * Igual ao v4.5: ao ABRIR o sino, carrega os itens E marca-lidas (o badge
	 * zera). A lista renderizada preserva `is_unread` da carga (destaque dos
	 * novos), mas a contagem do badge passa a refletir `unread_count` pos-marca.
	 */
	async function loadNotifications(): Promise<void> {
		if (notifLoading) return;
		notifLoading = true;
		notifError = false;
		try {
			const list = await fetchNotificacoes();
			notifItems = list.items;
			notifUnread = list.unread_count;
			notifLoadedOnce = true;
			// Marcar-lidas em seguida (badge volta a zero), como no legado.
			try {
				const marked = await marcarNotificacoesLidas();
				notifUnread = marked.unread_count;
			} catch {
				// Falha ao marcar nao deve apagar a lista ja carregada.
			}
		} catch {
			notifError = true;
		} finally {
			notifLoading = false;
		}
	}

	function closeNotif(): void {
		notifOpen = false;
	}

	function toggleNotif(): void {
		notifOpen = !notifOpen;
		if (notifOpen) void loadNotifications();
	}

	/** Roteia o clique-fora para qualquer dropdown aberto. */
	function handleAnyOutside(event: MouseEvent): void {
		const target = event.target as Node;
		if (adminOpen && adminMenuEl && !adminMenuEl.contains(target)) closeAdmin();
		if (orgaoOpen && orgaoMenuEl && !orgaoMenuEl.contains(target)) closeOrgao();
		if (notifOpen && notifMenuEl && !notifMenuEl.contains(target)) closeNotif();
	}
</script>

<svelte:window onclick={handleAnyOutside} onkeydown={handleWindowKeydown} />

<header class="app-topnav sticky top-0 z-sticky border-b border-white/10 bg-topnav-gradient">
	<div
		class="relative mx-auto flex min-h-[48px] items-center justify-between gap-6 px-5"
	>
		<!-- Esquerda: brand + navegacao por icones -->
		<div class="flex min-w-0 flex-[0_1_auto] items-center gap-[1.1rem]">
			<a
				href={`${base}/dashboard`}
				aria-label="ProjetosRJ"
				class="inline-flex items-center font-heading text-lg font-bold leading-none text-white no-underline transition-opacity duration-fast hover:opacity-85 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
			>
				ProjetosRJ
			</a>

			<!-- Indicador unico (pilula branca) que DESLIZA entre os itens. Um so
			     elemento, posicionado por transform+width medindo o <a> ativo, entao
			     vai DIRETO de um item ao outro (sem o "salto" do reflow). O item ATIVO
			     mostra icone + nome (texto escuro sobre a pilula); os demais ficam so
			     icone. Detalhes/alternativas em micro/docs/transicao-topnav.md. -->
			<nav
				bind:this={navEl}
				aria-label="Navegacao principal"
				class="relative inline-flex items-center gap-1"
			>
				{#if pill.ready}
					<span
						class="nav-pill pointer-events-none absolute left-0 top-0 z-0 h-[1.95rem] rounded-full bg-white {pillSlides
							? 'nav-pill--slide'
							: ''}"
						style="width: {pill.w}px; transform: translate3d({pill.x}px, 0, 0);"
						aria-hidden="true"
					></span>
				{/if}
				{#each navLinks as link (link.path)}
					{@const active = isActive(link.path, pathname)}
					<a
						href={`${base}${link.path}`}
						aria-current={active ? 'page' : undefined}
						title={link.label}
						aria-label={link.label}
						class="relative z-[1] inline-flex h-[1.95rem] items-center rounded-full pl-[0.5rem] text-[0.9rem] no-underline transition-colors duration-150 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70 {active
							? 'pr-3 text-primary-700'
							: 'pr-[0.5rem] text-white/[0.78] hover:bg-white/10 hover:text-white'}"
					>
						<i class="fas {link.icon} shrink-0" aria-hidden="true"></i>
						{#if active}
							<span class="ml-2 whitespace-nowrap font-semibold leading-none">{link.label}</span>
						{/if}
					</a>
				{/each}
			</nav>
		</div>

		<!-- Centro: seletor de orgao em ARVORE ANINHADA (porte de orgao-tree-picker) -->
		{#if hasOrgaoTree}
			<div
				bind:this={orgaoMenuEl}
				class="orgao-tree-control app-area-control absolute left-1/2 z-[2] hidden -translate-x-1/2 lg:inline-flex"
			>
				<button
					bind:this={orgaoToggleEl}
					type="button"
					class="orgao-tree-trigger"
					onclick={toggleOrgao}
					aria-haspopup="menu"
					aria-expanded={orgaoOpen}
					aria-label="Selecionar orgao"
				>
					<span class="orgao-tree-trigger-icon" aria-hidden="true"><i class="fas fa-sitemap"></i></span>
					<span class="orgao-tree-trigger-body">
						<span class="orgao-tree-trigger-title">{orgaoTriggerLabel}</span>
					</span>
					<span class="orgao-tree-trigger-caret" aria-hidden="true"><i class="fas fa-chevron-down"></i></span>
				</button>

				{#if orgaoOpen}
					<div class="orgao-tree-menu show" role="menu" aria-label="Orgaos">
						{#if showOrgaoFilter}
							<div class="orgao-tree-search">
								<i class="fas fa-search orgao-tree-search-icon" aria-hidden="true"></i>
								<!-- svelte-ignore a11y_autofocus -->
								<input
									type="text"
									class="orgao-tree-search-input"
									placeholder="Filtrar por nome ou sigla..."
									bind:value={orgaoFilter}
									autocomplete="off"
									autofocus
								/>
							</div>
						{/if}
						<div class="orgao-tree-body">
							<button
								type="button"
								class="orgao-tree-all"
								class:is-active={$orgaoScope.selectedId === null}
								onclick={() => pickOrgao(null)}
							>
								<i class="fas fa-layer-group" aria-hidden="true"></i>
								<span>Todos os orgaos</span>
							</button>
							<ul class="orgao-tree-list">
								{#each orgaoTree as node (node.id)}
									{@render orgaoNode(node)}
								{/each}
							</ul>
							{#if isFiltering && !orgaoTree.some((n) => nodeVisible(n))}
								<p class="orgao-tree-empty">Nenhum orgao encontrado.</p>
							{/if}
						</div>
					</div>
				{/if}
			</div>
		{/if}

		<!-- No recursivo da arvore: bullet por tipo, destaque do orgao do usuario,
		     chevron de expand/collapse hierarquico (porte do macro render_orgao_node). -->
		{#snippet orgaoNode(node: OrgaoTreeNode)}
			{@const hasChildren = (node.children ?? []).length > 0}
			{@const selected = $orgaoScope.selectedId === node.id}
			{@const expanded = isExpanded(node)}
			{#if nodeVisible(node)}
				<li class="orgao-tree-node">
					<div
						class="orgao-tree-row"
						class:is-user-orgao={node.is_user_orgao}
						class:is-selected={selected}
						class:is-inactive={node.is_inactive}
					>
						{#if hasChildren}
							<button
								type="button"
								class="orgao-tree-toggle"
								class:is-expanded={expanded}
								aria-label={expanded ? 'Recolher' : 'Expandir'}
								aria-expanded={expanded}
								onclick={() => toggleExpand(node)}
							>
								<i class="fas fa-chevron-right" aria-hidden="true"></i>
							</button>
						{:else}
							<span class="orgao-tree-toggle-spacer"></span>
						{/if}
						<span
							class="orgao-tree-bullet tipo-{tipoSlug(node.tipo)}"
							class:is-self={node.is_user_orgao}
							class:is-selected={selected}
							title={node.tipo ?? ''}
						></span>
						<button type="button" class="orgao-tree-link" onclick={() => pickOrgao(node)}>
							<span class="orgao-tree-sigla">{node.sigla}</span>
							<span class="orgao-tree-nome">{node.nome}</span>
						</button>
					</div>
					{#if hasChildren && expanded}
						<ul class="orgao-tree-children">
							{#each node.children as child (child.id)}
								{@render orgaoNode(child)}
							{/each}
						</ul>
					{/if}
				</li>
			{/if}
		{/snippet}

		<!-- Direita: busca + notificacoes + conta/admin + theme toggle -->
		<div class="ml-auto flex flex-[0_0_auto] items-center justify-end gap-[1.1rem]">
			<!-- Busca global LIVE (input + dropdown com debounce/teclado) -->
			<GlobalSearchBox />

			<!-- Notificacoes: sino com badge + dropdown (GET /api/notificacoes) -->
			<div bind:this={notifMenuEl} class="relative inline-flex">
				<button
					bind:this={notifToggleEl}
					type="button"
					onclick={toggleNotif}
					aria-haspopup="menu"
					aria-expanded={notifOpen}
					title="Notificacoes"
					aria-label="Notificacoes"
					class="relative inline-flex h-[1.95rem] w-[1.95rem] items-center justify-center rounded-md border border-transparent text-[0.9rem] transition-all duration-[180ms] focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70 {notifOpen
						? 'border-white bg-white text-primary-700'
						: 'bg-transparent text-white/[0.78] hover:bg-white/10 hover:text-white'}"
				>
					<i class="fas fa-bell" aria-hidden="true"></i>
					{#if notifUnread > 0}
						<span
							class="absolute -right-1 -top-1 inline-flex min-w-[1.05rem] items-center justify-center rounded-full bg-danger px-1 text-[0.62rem] font-bold leading-[1.05rem] text-white ring-2 ring-white/90"
							aria-label={`${notifUnread} nao lida(s)`}
						>
							{notifBadgeText}
						</span>
					{/if}
				</button>

				{#if notifOpen}
					<div
						role="menu"
						aria-label="Notificacoes"
						class="app-notifications-dropdown absolute right-0 top-full z-dropdown mt-2 w-[min(360px,90vw)] origin-top-right animate-dropdown-in overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
					>
						<div
							class="app-notifications-dropdown-header flex items-center justify-between gap-2 border-b border-border-subtle px-4 py-3"
							aria-hidden="true"
						>
							<span class="text-sm font-semibold text-text-primary">Notificacoes</span>
							<span class="text-xs text-text-secondary">{notifUnread} nao lida(s)</span>
						</div>
						<div class="app-notifications-list max-h-[60vh] overflow-y-auto p-2">
							{#if notifLoading && !notifLoadedOnce}
								<div
									class="app-notifications-state rounded-lg border border-border-subtle bg-surface-muted px-3 py-3 text-sm text-text-secondary"
								>
									Carregando notificacoes...
								</div>
							{:else if notifError}
								<div
									class="app-notifications-state rounded-lg border border-border-subtle bg-surface-muted px-3 py-3 text-sm text-text-secondary"
								>
									Nao foi possivel carregar as notificacoes.
								</div>
							{:else if notifItems.length === 0}
								<div
									class="app-notifications-state rounded-lg border border-border-subtle bg-surface-muted px-3 py-3 text-sm text-text-secondary"
								>
									Nenhuma notificacao no momento.
								</div>
							{:else}
								{#each notifItems as item (item.id)}
									<a
										href={item.target_url ?? '#'}
										role="menuitem"
										onclick={closeNotif}
										class="app-notification-item flex items-start gap-3 rounded-lg px-3 py-2.5 no-underline transition-colors duration-fast hover:bg-surface-muted {item.is_unread
											? 'bg-surface-muted'
											: ''}"
									>
										<span class="relative flex shrink-0 items-center justify-center">
											{#if item.is_unread}
												<span
													class="absolute -left-1.5 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-primary-500"
													aria-hidden="true"
												></span>
											{/if}
											<span
												class="flex h-8 w-8 items-center justify-center rounded-full bg-primary-100 text-primary-600"
											>
												<i class="fas {notifIcon(item.event_type)}" aria-hidden="true"></i>
											</span>
										</span>
										<span class="min-w-0 flex-1">
											<span class="flex items-baseline justify-between gap-2">
												<span class="truncate text-sm font-semibold text-text-primary"
													>{item.title || 'Atualizacao'}</span
												>
												<span class="shrink-0 text-[0.68rem] text-text-muted"
													>{relativeTime(item.created_at)}</span
												>
											</span>
											{#if item.message || item.actor_name}
												<span class="mt-0.5 block text-xs text-text-secondary">
													{#if item.actor_name}<span class="font-medium text-text-primary"
															>{item.actor_name}</span
														>{/if}{#if item.actor_name && item.message}&nbsp;{/if}{item.message}
												</span>
											{/if}
										</span>
									</a>
								{/each}
							{/if}
						</div>
					</div>
				{/if}
			</div>

			{#if user?.is_admin}
				<div bind:this={adminMenuEl} class="relative inline-flex">
					<button
						type="button"
						bind:this={adminToggleEl}
						onclick={toggleAdmin}
						aria-haspopup="menu"
						aria-expanded={adminOpen}
						aria-current={adminActive ? 'page' : undefined}
						title="Conta e administracao"
						aria-label="Conta e administracao"
						class="inline-flex h-[1.95rem] w-[1.95rem] items-center justify-center rounded-md border border-transparent text-[0.9rem] transition-all duration-[180ms] focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70 {adminActive ||
						adminOpen
							? 'border-white bg-white text-primary-700'
							: 'bg-transparent text-white/[0.78] hover:bg-white/10 hover:text-white'}"
					>
						<i class="fas fa-user-circle" aria-hidden="true"></i>
					</button>

					{#if adminOpen}
						<div
							role="menu"
							aria-label="Administracao"
							class="absolute right-0 top-full z-dropdown mt-2 min-w-[14rem] origin-top-right animate-dropdown-in overflow-hidden rounded-lg border border-border-subtle bg-surface py-1 shadow-lg"
						>
							{#if user}
								<div class="px-4 py-2" aria-hidden="true">
									<span class="block truncate text-sm font-semibold text-text-primary">
										{user.name}
									</span>
									<span class="block text-xs text-text-secondary">Administrador</span>
								</div>
								<hr class="my-1 border-border-subtle" />
							{/if}
							{#each adminLinks as link (link.path)}
								{@const active = isActive(link.path, pathname)}
								<a
									role="menuitem"
									href={`${base}${link.path}`}
									aria-current={active ? 'page' : undefined}
									onclick={closeAdmin}
									class="flex items-center gap-3 px-4 py-2 text-sm no-underline transition-colors duration-fast focus:outline-none focus-visible:bg-surface-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500 {active
										? 'bg-surface-muted text-text-primary'
										: 'text-text-secondary hover:bg-surface-muted hover:text-text-primary'}"
								>
									<i
										class="fas {link.icon} w-4 text-center text-text-muted"
										aria-hidden="true"
									></i>
									<span>{link.label}</span>
								</a>
							{/each}
						</div>
					{/if}
				</div>
			{/if}

			<!-- Theme switch rolling (portado 1:1 de app_topnav.html + 00-foundation.css) -->
			<label class="app-theme-switch" title="Alternar tema">
				<input
					type="checkbox"
					class="app-theme-switch__input"
					role="switch"
					checked={$theme === 'dark'}
					onchange={toggleTheme}
					aria-label="Alternar tema claro/escuro"
				/>
				<!-- SOL: viewBox 0 0 24 24 OBRIGATORIO. No v4.5 os icones vinham de
				     <symbol viewBox="0 0 24 24"> via <use>; ao inlinar o desenho sem
				     viewBox, o CSS encolhia o <svg> para 0.75em e CLIPAVA o desenho
				     (so o canto aparecia = "placeholder"). Com o viewBox o desenho
				     de 24 unidades ESCALA para a caixa, ficando nitido. -->
				<svg class="app-theme-switch__icon" viewBox="0 0 24 24" aria-hidden="true">
					<g stroke="currentColor" stroke-width="2" stroke-linecap="round">
						<line x1="12" y1="17" x2="12" y2="20" transform="rotate(0,12,12)" />
						<line x1="12" y1="17" x2="12" y2="20" transform="rotate(45,12,12)" />
						<line x1="12" y1="17" x2="12" y2="20" transform="rotate(90,12,12)" />
						<line x1="12" y1="17" x2="12" y2="20" transform="rotate(135,12,12)" />
						<line x1="12" y1="17" x2="12" y2="20" transform="rotate(180,12,12)" />
						<line x1="12" y1="17" x2="12" y2="20" transform="rotate(225,12,12)" />
						<line x1="12" y1="17" x2="12" y2="20" transform="rotate(270,12,12)" />
						<line x1="12" y1="17" x2="12" y2="20" transform="rotate(315,12,12)" />
					</g>
					<circle fill="currentColor" cx="12" cy="12" r="5" />
				</svg>
				<!-- LUA: mesmo motivo — viewBox 0 0 24 24 para escalar o crescente. -->
				<svg class="app-theme-switch__icon" viewBox="0 0 24 24" aria-hidden="true">
					<path
						fill="currentColor"
						d="M15.1,14.9c-3-0.5-5.5-3-6-6C8.8,7.1,9.1,5.4,9.9,4c0.4-0.8-0.4-1.7-1.2-1.4C4.6,4,1.8,7.9,2,12.5c0.2,5.1,4.4,9.3,9.5,9.5c4.5,0.2,8.5-2.6,9.9-6.6c0.3-0.8-0.6-1.7-1.4-1.2C18.6,14.9,16.9,15.2,15.1,14.9z"
					/>
				</svg>
				<span class="app-theme-switch__inner"></span>
				<span class="app-theme-switch__inner-icons">
					<svg class="app-theme-switch__icon" viewBox="0 0 24 24" aria-hidden="true">
						<g stroke="currentColor" stroke-width="2" stroke-linecap="round">
							<line x1="12" y1="17" x2="12" y2="20" transform="rotate(0,12,12)" />
							<line x1="12" y1="17" x2="12" y2="20" transform="rotate(45,12,12)" />
							<line x1="12" y1="17" x2="12" y2="20" transform="rotate(90,12,12)" />
							<line x1="12" y1="17" x2="12" y2="20" transform="rotate(135,12,12)" />
							<line x1="12" y1="17" x2="12" y2="20" transform="rotate(180,12,12)" />
							<line x1="12" y1="17" x2="12" y2="20" transform="rotate(225,12,12)" />
							<line x1="12" y1="17" x2="12" y2="20" transform="rotate(270,12,12)" />
							<line x1="12" y1="17" x2="12" y2="20" transform="rotate(315,12,12)" />
						</g>
						<circle fill="currentColor" cx="12" cy="12" r="5" />
					</svg>
					<svg class="app-theme-switch__icon" viewBox="0 0 24 24" aria-hidden="true">
						<path
							fill="currentColor"
							d="M15.1,14.9c-3-0.5-5.5-3-6-6C8.8,7.1,9.1,5.4,9.9,4c0.4-0.8-0.4-1.7-1.2-1.4C4.6,4,1.8,7.9,2,12.5c0.2,5.1,4.4,9.3,9.5,9.5c4.5,0.2,8.5-2.6,9.9-6.6c0.3-0.8-0.6-1.7-1.4-1.2C18.6,14.9,16.9,15.2,15.1,14.9z"
						/>
					</svg>
				</span>
				<span class="app-theme-switch__sr">Alternar tema</span>
			</label>

			{#if user && !user.is_admin}
				<span class="hidden text-sm text-white/90 sm:inline" title={user.username}>
					{user.name}
				</span>
			{/if}
		</div>
	</div>
</header>

<style>
	/* Indicador deslizante da nav: anima transform (compositor) + width (custo de
	   layout trivial por ser UM elemento fora de fluxo). cubic-bezier in-out =
	   passada suave. .nav-pill--slide so e aplicada apos o 1o posicionamento, para
	   nao deslizar a partir do x=0 ao montar. */
	.nav-pill--slide {
		transition:
			transform 320ms cubic-bezier(0.65, 0, 0.35, 1),
			width 320ms cubic-bezier(0.65, 0, 0.35, 1);
	}
	@media (prefers-reduced-motion: reduce) {
		.nav-pill--slide {
			transition: none;
		}
	}

	/* === Seletor de orgao em arvore ===
	   Porte de static/css/partials/orgao-tree-picker.css (v4.5). O trigger vive na
	   barra azul (cores brancas fixas, como no original); o painel e branco com
	   destaque azul para o orgao do usuario. A arvore e ANINHADA (children + flags)
	   vinda de GET /api/orgaos/escopo, com expand/collapse por chevron e bullets
	   coloridos por tipo — fiel ao macro render_orgao_node do legado. */
	.orgao-tree-control {
		position: relative;
	}

	.orgao-tree-control.app-area-control {
		border: 1px solid rgba(255, 255, 255, 0.22);
		border-radius: 8px;
		background: transparent;
		overflow: visible;
	}

	.orgao-tree-control.app-area-control:hover {
		border-color: rgba(255, 255, 255, 0.4);
	}

	.orgao-tree-trigger {
		display: inline-flex;
		align-items: center;
		gap: 0.55rem;
		padding: 0.32rem 0.7rem;
		background: transparent;
		border: none;
		color: #ffffff;
		font-weight: 500;
		font-size: 0.85rem;
		line-height: 1.24;
		cursor: pointer;
		min-height: 1.95rem;
		max-width: 320px;
		transition: background-color 0.18s ease;
	}

	.orgao-tree-trigger:hover,
	.orgao-tree-trigger[aria-expanded='true'] {
		background: rgba(255, 255, 255, 0.12);
	}

	.orgao-tree-trigger:focus,
	.orgao-tree-trigger:focus-visible {
		outline: none;
		box-shadow: none;
	}

	.orgao-tree-trigger-icon {
		color: rgba(255, 255, 255, 0.9);
		font-size: 0.92rem;
	}

	.orgao-tree-trigger-body {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.02rem;
		line-height: 1.15;
		min-width: 0;
	}

	.orgao-tree-trigger-title {
		font-weight: 600;
		color: #ffffff;
		font-size: 0.88rem;
		letter-spacing: 0.01em;
		max-width: 220px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.orgao-tree-trigger-caret {
		color: rgba(255, 255, 255, 0.85);
		font-size: 0.7rem;
		margin-left: 0.2rem;
	}

	.orgao-tree-menu {
		position: absolute;
		top: calc(100% + 0.4rem);
		left: 50%;
		transform: translateX(-50%);
		z-index: 1080;
		border: 1px solid #dbe6f2;
		border-radius: 14px;
		padding: 0;
		width: min(420px, 92vw);
		max-height: min(70vh, 560px);
		background: #ffffff;
		box-shadow: 0 18px 36px rgba(21, 34, 56, 0.16);
		overflow: hidden;
		animation: app-dropdown-in 0.16s ease-out;
	}

	.orgao-tree-menu.show {
		display: flex;
		flex-direction: column;
	}

	@keyframes app-dropdown-in {
		from {
			opacity: 0;
			transform: translate(-50%, -0.4rem);
		}
		to {
			opacity: 1;
			transform: translate(-50%, 0);
		}
	}

	.orgao-tree-search {
		position: relative;
		padding: 0.7rem 0.85rem;
		border-bottom: 1px solid #eef2f7;
		background: #fafbfd;
	}

	.orgao-tree-search-icon {
		position: absolute;
		left: 1.4rem;
		top: 50%;
		transform: translateY(-50%);
		color: #94a3b8;
		font-size: 0.85rem;
		pointer-events: none;
	}

	.orgao-tree-search-input {
		width: 100%;
		padding: 0.5rem 0.75rem 0.5rem 2.1rem;
		border: 1px solid #e1e7ef;
		border-radius: 10px;
		background: #ffffff;
		font-size: 0.9rem;
		color: #1f2d3d;
		outline: none;
		transition:
			border-color 0.15s,
			box-shadow 0.15s;
	}

	.orgao-tree-search-input:focus {
		border-color: #94b3d8;
		box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
	}

	.orgao-tree-body {
		overflow-y: auto;
		padding: 0.4rem 0.5rem 0.6rem;
		flex: 1;
	}

	.orgao-tree-all {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		width: 100%;
		padding: 0.55rem 0.7rem;
		border: none;
		background: transparent;
		border-radius: 8px;
		color: #1d4ed8;
		text-decoration: none;
		font-weight: 600;
		font-size: 0.9rem;
		margin-bottom: 0.3rem;
		cursor: pointer;
	}

	.orgao-tree-all:hover {
		background: #eef4ff;
		color: #1d4ed8;
	}

	.orgao-tree-all.is-active {
		background: #e0ecff;
		color: #1d4ed8;
	}

	.orgao-tree-list,
	.orgao-tree-children {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	/* Indentacao hierarquica com guia tracejada (porte 1:1 do v4.5). */
	.orgao-tree-children {
		padding-left: 1.1rem;
		border-left: 1px dashed #e6ebf2;
		margin-left: 0.8rem;
	}

	/* Chevron de expand/collapse — gira 90deg quando expandido. */
	.orgao-tree-toggle {
		width: 18px;
		height: 18px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		background: transparent;
		border: none;
		color: #8c9bad;
		cursor: pointer;
		padding: 0;
		border-radius: 4px;
		transition: transform 0.15s;
		flex-shrink: 0;
	}

	.orgao-tree-toggle:hover {
		background: #e6ebf2;
		color: #1f2d3d;
	}

	.orgao-tree-toggle.is-expanded {
		transform: rotate(90deg);
	}

	.orgao-tree-row {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		padding: 0.32rem 0.4rem;
		border-radius: 8px;
		transition: background 0.12s;
	}

	.orgao-tree-row:hover {
		background: #f3f7fc;
	}

	.orgao-tree-row.is-selected {
		background: #e7f0ff;
	}

	.orgao-tree-toggle-spacer {
		width: 18px;
		height: 18px;
		flex-shrink: 0;
	}

	.orgao-tree-bullet {
		width: 9px;
		height: 9px;
		border-radius: 50%;
		background: #c1cad6;
		flex-shrink: 0;
	}

	/* Cores do bullet por tipo de orgao (porte 1:1 de orgao-tree-picker.css). */
	.orgao-tree-bullet.tipo-estado {
		background: #0b4d86;
	}
	.orgao-tree-bullet.tipo-secretaria {
		background: #1d4ed8;
	}
	.orgao-tree-bullet.tipo-subsecretaria {
		background: #0891b2;
	}
	.orgao-tree-bullet.tipo-autarquia {
		background: #7c3aed;
	}
	.orgao-tree-bullet.tipo-fundacao {
		background: #db2777;
	}
	.orgao-tree-bullet.tipo-empresa-publica {
		background: #be185d;
	}
	.orgao-tree-bullet.tipo-assessoria {
		background: #0d9488;
	}
	.orgao-tree-bullet.tipo-coordenacao {
		background: #b45309;
	}
	.orgao-tree-bullet.tipo-nucleo {
		background: #b45309;
	}
	.orgao-tree-bullet.tipo-departamento {
		background: #6b7280;
	}

	/* Selecionado/proprio orgao: anel azul mantendo a cor do tipo (igual v4.5). */
	.orgao-tree-bullet.is-selected,
	.orgao-tree-bullet.is-self {
		box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.22);
	}

	/* Orgao inativo: leve esmaecimento (sem mudar a estrutura). */
	.orgao-tree-row.is-inactive .orgao-tree-link {
		opacity: 0.6;
	}

	.orgao-tree-link {
		flex: 1;
		display: inline-flex;
		align-items: baseline;
		gap: 0.4rem;
		color: inherit;
		text-decoration: none;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		padding: 0.05rem 0;
		border: none;
		background: transparent;
		cursor: pointer;
		text-align: left;
	}

	.orgao-tree-sigla {
		font-weight: 700;
		color: #6b7a8d;
		font-size: 0.93rem;
	}

	.orgao-tree-row.is-user-orgao .orgao-tree-sigla,
	.orgao-tree-row.is-user-orgao .orgao-tree-nome {
		color: #2563eb;
	}

	.orgao-tree-row.is-user-orgao .orgao-tree-sigla {
		font-weight: 800;
	}

	.orgao-tree-nome {
		color: #6b7a8d;
		font-size: 0.83rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.orgao-tree-empty {
		text-align: center;
		color: #8c9bad;
		font-size: 0.85rem;
		padding: 1rem;
		margin: 0;
	}

	/* === Theme switch (rolling) ===
	   Portado 1:1 de static/css/legacy/00-foundation.css:354-503 (adaptado de
	   codepen.io/jkantner). Estrutura/animacao preservadas: duracao 0.6s,
	   easing cubic-bezier(0.65,0,0.35,1), translate +/-1.25em e rotacao 360deg.
	   O estado dark e dirigido por html[data-theme="dark"] (mesmo que no v4.5). */
	.app-theme-switch {
		--primary: #ffffff;
		--rail-light: rgba(255, 255, 255, 0.1);
		--rail-dark: rgba(255, 255, 255, 0.08);
		--rail-border-light: rgba(255, 255, 255, 0.22);
		--rail-border-dark: rgba(255, 255, 255, 0.18);
		--icon-light: rgba(255, 255, 255, 0.62);
		--icon-dark: rgba(255, 255, 255, 0.5);
		--trans-dur: 0.6s;
		--trans-timing: cubic-bezier(0.65, 0, 0.35, 1);
		font-size: 17px;
		position: relative;
		display: inline-flex;
		align-items: center;
		margin: 0;
		cursor: pointer;
		-webkit-tap-highlight-color: transparent;
		user-select: none;
	}

	.app-theme-switch__input {
		appearance: none;
		-webkit-appearance: none;
		display: block;
		margin: 0;
		background-color: var(--rail-light);
		border: 1px solid var(--rail-border-light);
		border-radius: 0.75em;
		box-shadow: none;
		outline: transparent;
		width: 2.75em;
		height: 1.5em;
		cursor: pointer;
		transition:
			background-color var(--trans-dur),
			border-color var(--trans-dur),
			box-shadow var(--trans-dur);
	}

	:global(html[data-theme='dark']) .app-theme-switch__input {
		background-color: var(--rail-dark);
		border-color: var(--rail-border-dark);
	}

	:global(html[data-theme='dark']) .app-theme-switch__inner:before {
		background-color: #93c5e8;
	}

	:global(html[data-theme='dark']) .app-theme-switch__inner-icons .app-theme-switch__icon {
		color: #0f2540;
	}

	.app-theme-switch__input:focus-visible {
		box-shadow:
			0 0 0 0.0625em var(--primary),
			0 0.125em 0.5em rgba(15, 28, 47, 0.18);
	}

	/* Icones do trilho — fixos nas pontas; o lado oposto a pilula atua como hint. */
	.app-theme-switch__icon {
		color: var(--icon-light);
		pointer-events: none;
		position: absolute;
		top: 0.375em;
		left: 0.375em;
		width: 0.75em;
		height: 0.75em;
		transition:
			color var(--trans-dur),
			transform var(--trans-dur) var(--trans-timing);
	}

	.app-theme-switch__icon:nth-of-type(2) {
		right: 0.375em;
		left: auto;
	}

	:global(html[data-theme='dark']) .app-theme-switch__icon {
		color: var(--icon-dark);
	}

	/* Vagao (.inner) e clip de icones internos (.inner-icons): geometria + translate. */
	.app-theme-switch__inner,
	.app-theme-switch__inner-icons {
		border-radius: 0.5em;
		display: block;
		overflow: hidden;
		position: absolute;
		top: 0.25em;
		left: 0.25em;
		width: 2.25em;
		height: 1em;
	}

	.app-theme-switch__inner:before,
	.app-theme-switch__inner-icons {
		transition: transform var(--trans-dur) var(--trans-timing);
		transform: translateX(-1.25em);
	}

	.app-theme-switch__inner:before {
		background-color: var(--primary);
		border-radius: inherit;
		content: '';
		display: block;
		width: 100%;
		height: 100%;
	}

	.app-theme-switch__inner-icons {
		pointer-events: none;
	}

	.app-theme-switch__inner-icons .app-theme-switch__icon {
		color: #1769a8;
		top: 0.125em;
		left: 0.125em;
		transform: translateX(1.25em);
	}

	.app-theme-switch__inner-icons .app-theme-switch__icon:nth-of-type(2) {
		right: 0.125em;
		left: auto;
	}

	/* Em dark: pilula desliza pra DIREITA; icones internos contra-translam e giram 360deg */
	:global(html[data-theme='dark']) .app-theme-switch__inner:before,
	:global(html[data-theme='dark']) .app-theme-switch__inner-icons {
		transform: translateX(1.25em);
	}

	:global(html[data-theme='dark'])
		.app-theme-switch__inner-icons
		.app-theme-switch__icon:first-of-type {
		transform: translateX(-1.25em) rotate(-360deg);
	}

	:global(html[data-theme='dark'])
		.app-theme-switch__inner-icons
		.app-theme-switch__icon:nth-of-type(2) {
		transform: translateX(-1.25em) rotate(360deg);
	}

	/* Rotacao suave dos icones do trilho ao trocar de estado */
	.app-theme-switch__input:not(:checked) ~ .app-theme-switch__icon:first-of-type,
	:global(html[data-theme='dark']) .app-theme-switch__icon:nth-of-type(2) {
		transform: rotate(360deg);
	}

	@media (prefers-reduced-motion: reduce) {
		.app-theme-switch {
			--trans-dur: 0s;
		}
	}

	.app-theme-switch__sr {
		overflow: hidden;
		position: absolute;
		width: 1px;
		height: 1px;
	}
</style>
