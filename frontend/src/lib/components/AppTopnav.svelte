<script lang="ts">
	/**
	 * Topnav do app shell: barra azul com brand + navegacao + busca global LIVE +
	 * notificacoes + menu de conta/admin + theme toggle rolling.
	 *
	 * Visual e micro-interacoes portados de templates/partials/app_topnav.html
	 * (v4.5), das regras .app-topnav e .app-notifications-* de
	 * static/css/legacy/00-foundation.css, e dos comportamentos de
	 * static/js/app-shell/{global-search,notifications,theme}.js.
	 *
	 * Fiacao base-aware (`$app/paths`), link ativo via `aria-current="page"`
	 * comparando `$page.url.pathname`, store de tema (`$theme`/`toggleTheme`) e o
	 * menu Admin acessivel ja existentes. A busca live vive em GlobalSearchBox.
	 */
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import { theme, toggleTheme } from '$lib/stores/theme';
	import {
		fetchNotificacoes,
		marcarNotificacoesLidas
	} from '$lib/api/notifications';
	import GlobalSearchBox from '$lib/components/GlobalSearchBox.svelte';
	import Nav3dIcon from '$lib/components/Nav3dIcon.svelte';
	import type { NavIconKind } from '$lib/nav3d/palettes';
	import type { User } from '$lib/types/entities';
	import type { Notificacao } from '$lib/types/notifications';

	interface Props {
		user: User | null;
	}

	let { user }: Props = $props();

	interface NavLink {
		label: string;
		path: string;
		icon: string;
	}

	/** Item da nav principal: tem modelo 3D; o FA continua sendo o fallback. */
	interface MainNavLink extends NavLink {
		kind: NavIconKind;
	}

	// Ordem do v4.5 (sem item "Busca" — a busca virou o campo live a direita).
	const navLinks: MainNavLink[] = [
		{ label: 'Inicio', path: '/dashboard', icon: 'fa-home', kind: 'inicio' },
		{ label: 'Projetos', path: '/projetos', icon: 'fa-folder-open', kind: 'projetos' },
		{
			label: 'Pendentes',
			path: '/projetos/pendentes',
			icon: 'fa-exclamation-triangle',
			kind: 'pendentes'
		},
		{ label: 'Tarefas', path: '/tarefas', icon: 'fa-tasks', kind: 'tarefas' },
		{ label: 'Calendario', path: '/calendarios', icon: 'fa-calendar-alt', kind: 'calendario' }
	];

	// Item com o ponteiro/Enter pressionado — dirige o "pop" de acionamento do
	// icone 3D. So visual e reversivel (WCAG 2.5.2): navegar continua no click.
	let pressedPath = $state<string | null>(null);

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

	// Acompanha mudancas de largura da viewport (quebra de layout reposiciona itens)
	// E reflows internos do nav. O ResizeObserver e essencial no RELOAD: a fonte
	// custom (Manrope/Inter) costuma trocar DEPOIS do 1o measurePill, alargando o
	// rotulo ativo; sem remedir, o texto vazava a pilula. fonts.ready cobre o swap
	// inicial; o observer cobre qualquer reflow posterior.
	$effect(() => {
		if (!navEl) return;
		const onResize = () => measurePill();
		window.addEventListener('resize', onResize);
		const ro = new ResizeObserver(() => measurePill());
		ro.observe(navEl);
		document.fonts?.ready.then(() => measurePill());
		return () => {
			window.removeEventListener('resize', onResize);
			ro.disconnect();
		};
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
		// (ex.: "/projetos" vs "/projetos/pendentes"). Considera nav + admin
		// para desambiguar.
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
	// iconHover: cor do icone no hover do item — uma cor por item (tokens DS).
	const adminLinks: (NavLink & { iconHover: string })[] = [
		{ label: 'Usuarios', path: '/admin/usuarios', icon: 'fa-users-cog', iconHover: 'group-hover:text-brand' },
		{ label: 'Orgaos', path: '/admin/orgaos', icon: 'fa-sitemap', iconHover: 'group-hover:text-brand' },
		{ label: 'Templates', path: '/admin/templates', icon: 'fa-clone', iconHover: 'group-hover:text-success' }
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
			if (adminOpen || notifOpen) {
				// Consome o gesto: o FlashToasts (listener irmão no window) checa
				// defaultPrevented para não dispensar um toast no MESMO Esc que
				// fechou este dropdown.
				event.preventDefault();
			}
			if (adminOpen) {
				closeAdmin();
				adminToggleEl?.focus();
			}
			if (notifOpen) {
				closeNotif();
				notifToggleEl?.focus();
			}
		}
	}

	// Notificacoes (sino): GET /api/notificacoes + POST marcar-lidas (api/notifications.ts)
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
		// S4: convite por projeto (`projeto_convite`) — nao casa com `project_`.
		if (t === 'projeto_convite') return 'fa-user-plus';
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
		if (notifOpen && notifMenuEl && !notifMenuEl.contains(target)) closeNotif();
	}
</script>

<svelte:window onclick={handleAnyOutside} onkeydown={handleWindowKeydown} />

<header
	class="app-topnav sticky top-0 z-sticky border-b border-b-on-brand-divider bg-topnav"
>
	<div
		class="relative mx-auto flex min-h-[var(--app-topnav-height)] items-center justify-between gap-6 px-5"
	>
		<!-- Esquerda: brand + navegacao por icones -->
		<div class="flex min-w-0 flex-[0_1_auto] items-center gap-[1.1rem]">
			<a
				href={`${base}/dashboard`}
				aria-label="ProjetosRJ"
				class="inline-flex items-center font-heading text-lg font-bold leading-none text-on-topnav no-underline transition-opacity duration-fast hover:opacity-85 focus:outline-none focus-visible:ring-2 focus-visible:ring-on-brand"
			>
				ProjetosRJ
			</a>

			<!-- Indicador unico (pilula branca) que DESLIZA entre os itens. Um so
			     elemento, posicionado por transform+width medindo o <a> ativo. TODOS
			     os itens mostram icone + nome SEMPRE (largura estavel): assim navegar
			     so move a pilula e cruza a cor do texto — sem reflow/"salto" dos itens
			     (era a causa da animacao travada). Detalhes em
			     micro/docs/transicao-topnav.md. -->
			<nav
				bind:this={navEl}
				aria-label="Navegacao principal"
				class="relative inline-flex items-center gap-0.5"
			>
				{#if pill.ready}
					<span
						class="nav-pill pointer-events-none absolute left-0 top-0 z-0 h-[1.95rem] rounded-md bg-surface-elevated dark:bg-[color-mix(in_srgb,var(--ds-color-neutral-0)_15%,transparent)] {pillSlides
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
						onpointerdown={(e) => {
							// Botao direito/meio: o menu de contexto engole o pointerup e o
							// icone ficaria afundado.
							if (e.button === 0) pressedPath = link.path;
						}}
						onpointerup={() => (pressedPath = null)}
						onpointerleave={() => (pressedPath = null)}
						onpointercancel={() => (pressedPath = null)}
						onblur={() => (pressedPath = null)}
						onkeydown={(e) => {
							// Espaco fica de fora de proposito: em <a href> ele rola a pagina.
							if (e.key === 'Enter' && !e.repeat) pressedPath = link.path;
						}}
						onkeyup={(e) => {
							if (e.key === 'Enter') pressedPath = null;
						}}
						class="relative z-[1] inline-flex h-[1.95rem] items-center gap-2 rounded-md px-3 text-[0.85rem] font-medium leading-none no-underline transition-colors duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] focus:outline-none focus-visible:ring-2 focus-visible:ring-on-brand {active
							? 'text-brand'
							: 'text-on-brand-muted hover:text-on-topnav'}"
					>
						<Nav3dIcon
							faIcon={link.icon}
							kind={link.kind}
							{active}
							pressed={pressedPath === link.path}
						/>
						<span class="whitespace-nowrap">{link.label}</span>
					</a>
				{/each}
			</nav>
		</div>

		<!-- Direita: busca + notificacoes + conta/admin + theme toggle -->
		<!-- Sem ml-auto: o justify-between do container alinha este grupo à
		     direita; um auto-margin aqui roubaria o espaço livre do seletor
		     central (mx-auto) e o empurraria para a esquerda. -->
		<div class="flex flex-[0_0_auto] items-center justify-end gap-[1.1rem]">
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
					title="Notificações"
					aria-label="Notificações"
					class="relative inline-flex h-[1.95rem] w-[1.95rem] items-center justify-center rounded-md border border-transparent text-[0.9rem] transition-all duration-[180ms] focus:outline-none focus-visible:ring-2 focus-visible:ring-on-brand {notifOpen
						? 'border-surface-elevated bg-surface-elevated text-brand dark:border-[color-mix(in_srgb,var(--ds-color-neutral-0)_10%,transparent)] dark:bg-[color-mix(in_srgb,var(--ds-color-neutral-0)_15%,transparent)] dark:text-white'
						: 'bg-transparent text-on-brand-muted hover:bg-on-brand-hover hover:text-on-topnav'}"
				>
					<i class="fas fa-bell" aria-hidden="true"></i>
					{#if notifUnread > 0}
						<span
							class="absolute -right-1 -top-1 inline-flex min-w-[1.05rem] items-center justify-center rounded-full bg-danger px-1 text-[0.62rem] font-bold leading-[1.05rem] text-on-danger ring-2 ring-on-brand"
							aria-label={`${notifUnread} não lida(s)`}
						>
							{notifBadgeText}
						</span>
					{/if}
				</button>

				{#if notifOpen}
					<div
						role="menu"
						aria-label="Notificações"
						class="app-notifications-dropdown absolute right-0 top-full z-dropdown mt-2 w-[min(360px,90vw)] origin-top-right animate-dropdown-in overflow-hidden rounded-xl border border-border-subtle bg-surface"
						style="box-shadow: var(--ds-shadow-popover);"
					>
						<div
							class="app-notifications-dropdown-header flex items-center justify-between gap-2 border-b border-border-subtle px-4 py-3"
							aria-hidden="true"
						>
							<span class="text-sm font-semibold text-text-primary">Notificações</span>
							<span class="text-xs text-text-secondary">{notifUnread} não lida(s)</span>
						</div>
						<div class="app-notifications-list max-h-[60vh] overflow-y-auto p-2">
							{#if notifLoading && !notifLoadedOnce}
								<div
									class="app-notifications-state rounded-lg border border-border-subtle bg-surface-muted px-3 py-3 text-sm text-text-secondary"
								>
									Carregando notificações…
								</div>
							{:else if notifError}
								<div
									class="app-notifications-state rounded-lg border border-border-subtle bg-surface-muted px-3 py-3 text-sm text-text-secondary"
								>
									Não foi possível carregar as notificações.
								</div>
							{:else if notifItems.length === 0}
								<div
									class="app-notifications-state rounded-lg border border-border-subtle bg-surface-muted px-3 py-3 text-sm text-text-secondary"
								>
									Nenhuma notificação no momento.
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
													class="absolute -left-1.5 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-brand"
													aria-hidden="true"
												></span>
											{/if}
											<span class="flex h-8 w-8 items-center justify-center text-brand">
												<i class="fas {notifIcon(item.event_type)}" aria-hidden="true"></i>
											</span>
										</span>
										<span class="min-w-0 flex-1">
											<span class="flex items-baseline justify-between gap-2">
												<span class="truncate text-sm font-semibold text-text-primary"
													>{item.title || 'Atualização'}</span
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

			{#if user}
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
						class="inline-flex h-[1.95rem] w-[1.95rem] items-center justify-center rounded-md border border-transparent text-[0.9rem] transition-all duration-[180ms] focus:outline-none focus-visible:ring-2 focus-visible:ring-on-brand {adminActive ||
						adminOpen
							? 'border-surface-elevated bg-surface-elevated text-brand dark:border-[color-mix(in_srgb,var(--ds-color-neutral-0)_10%,transparent)] dark:bg-[color-mix(in_srgb,var(--ds-color-neutral-0)_15%,transparent)] dark:text-white'
							: 'bg-transparent text-on-brand-muted hover:bg-on-brand-hover hover:text-on-topnav'}"
					>
						<i class="fas fa-user-circle" aria-hidden="true"></i>
					</button>

					{#if adminOpen}
						<div
							role="menu"
							aria-label="Administracao"
							class="absolute right-0 top-full z-dropdown mt-2 min-w-[14rem] origin-top-right animate-dropdown-in overflow-hidden rounded-lg border border-border-subtle bg-surface py-1"
							style="box-shadow: var(--ds-shadow-popover);"
						>
							<div class="px-4 py-2" aria-hidden="true">
								<span class="block truncate text-sm font-semibold text-text-primary">
									{user.name}
								</span>
								<span class="block text-xs text-text-secondary">
									{user.is_admin ? 'Administrador' : user.username}
								</span>
							</div>
							<hr class="my-1 border-border-subtle" />
							{#if user.is_admin}
								{#each adminLinks as link (link.path)}
									{@const active = isActive(link.path, pathname)}
									<a
										role="menuitem"
										href={`${base}${link.path}`}
										aria-current={active ? 'page' : undefined}
										onclick={closeAdmin}
										class="group flex items-center gap-3 px-4 py-2 text-sm no-underline transition-colors duration-fast focus:outline-none focus-visible:bg-surface-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand {active
											? 'bg-surface-muted text-text-primary'
											: 'text-text-secondary hover:bg-surface-muted hover:text-text-primary'}"
									>
										<i
											class="fas {link.icon} w-4 text-center text-text-muted transition-colors duration-fast {link.iconHover}"
											aria-hidden="true"
										></i>
										<span>{link.label}</span>
									</a>
								{/each}
								<hr class="my-1 border-border-subtle" />
							{/if}
							<!-- Exportar CSV de projetos: link direto para a rota Flask
								 nativa /projects/download (attachment, FORA do envelope JSON).
								 Migrado da tela de Projetos para o menu de usuário. -->
							<a
								role="menuitem"
								href="/projects/download"
								download
								onclick={closeAdmin}
								class="group flex items-center gap-3 px-4 py-2 text-sm text-text-secondary no-underline transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:bg-surface-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
							>
								<i
									class="fas fa-file-csv w-4 text-center text-text-muted transition-colors duration-fast group-hover:text-attention"
									aria-hidden="true"
								></i>
								<span>Exportar CSV de projetos</span>
							</a>
							<hr class="my-1 border-border-subtle" />
							<!-- Logout: rota Flask nativa /logout (fluxo fora da SPA), como no
								 dropdown do topnav Jinja v4.5. -->
							<a
								role="menuitem"
								href="/logout"
								data-sveltekit-reload
								class="flex items-center gap-3 px-4 py-2 text-sm text-danger no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:bg-surface-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
							>
								<i class="fas fa-sign-out-alt w-4 text-center" aria-hidden="true"></i>
								<span>Sair</span>
							</a>
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
		</div>
	</div>
</header>

<style>
	/* Indicador deslizante da nav: anima transform (compositor) + width (UM elemento
	   fora de fluxo). Mesma duracao/curva (300ms) do crossfade de cor dos itens,
	   para a pilula chegar JUNTO com o texto escurecendo (sem o trecho azul-sobre-
	   azul de antes). Como os itens tem largura estavel (rotulo sempre visivel),
	   a pilula desliza sobre uma linha que nao reflui. .nav-pill--slide so entra
	   apos o 1o posicionamento, para nao deslizar a partir do x=0 ao montar. */
	.nav-pill--slide {
		transition:
			transform 300ms cubic-bezier(0.4, 0, 0.2, 1),
			width 300ms cubic-bezier(0.4, 0, 0.2, 1);
	}
	@media (prefers-reduced-motion: reduce) {
		.nav-pill--slide {
			transition: none;
		}
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

	:global(html[data-theme='dark']) .app-theme-switch__input:focus-visible {
		box-shadow:
			0 0 0 0.0625em var(--primary),
			0 0.125em 0.5em rgba(255, 255, 255, 0.2);
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
		color: var(--ds-color-text-brand);
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
