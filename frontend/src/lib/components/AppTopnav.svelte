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
	 * Icones: sistema duotone SVG do redesign 2026 (TopnavIcon/AdminMenuIcon/
	 * AppIcon) — substituiu o nav3d (three.js).
	 */
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import { theme, toggleTheme } from '$lib/stores/theme';

	// Modo escuro incompleto: toggle escondido até o tema ser finalizado.
	const THEME_TOGGLE_ENABLED = false;
	import GlobalSearchBox from '$lib/components/GlobalSearchBox.svelte';
	import NotificationBell from '$lib/components/NotificationBell.svelte';
	import NovidadesBotao from '$lib/components/novidades/NovidadesBotao.svelte';
	import TopnavIcon, { type NavIconKind } from '$lib/components/TopnavIcon.svelte';
	import AdminMenuIcon, { type AdminIconKind } from '$lib/components/AdminMenuIcon.svelte';
	import { CALENDAR_ENABLED } from '$lib/config/features';
	import type { User } from '$lib/types/entities';
	import ExportarProjetosModal from '$lib/components/ExportarProjetosModal.svelte';
	import ImportarCsvModal from '$lib/components/ImportarCsvModal.svelte';
	import { fetchProjects, peekProjects, invalidateProjects } from '$lib/api/projects';
	import { bumpProjectsRevision } from '$lib/stores/projectsRevision';
	import type { ProjectsListOptions } from '$lib/types/projects';

	interface Props {
		user: User | null;
	}

	let { user }: Props = $props();

	// Ordem do v4.5 (sem item "Busca" — a busca virou o campo live a direita).
	const allNavLinks: {
		label: string;
		path: string;
		kind: NavIconKind;
		enabled?: boolean;
	}[] = [
		{ label: 'Início', path: '/dashboard', kind: 'inicio' },
		{ label: 'Projetos', path: '/projetos', kind: 'projetos' },
		{ label: 'Coleções', path: '/colecoes', kind: 'colecoes' },
		{ label: 'Pendentes', path: '/projetos/pendentes', kind: 'pendentes' },
		{ label: 'Tarefas', path: '/tarefas', kind: 'tarefas' },
		{ label: 'Calendário', path: '/calendarios', kind: 'calendario', enabled: CALENDAR_ENABLED }
	];

	const navLinks = allNavLinks.filter((link) => link.enabled !== false);

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
	const ajustesActive = $derived(isActive('/conta/ajustes', pathname));

	// Tela de Ajustes escondida do menu até o vínculo gov.br ser refinado (ver
	// docs/pendencias-seguranca-vinculo-govbr.txt). Rota, backend e página ficam.
	const AJUSTES_ENABLED = false;

	// Links do menu Admin (so renderizados quando user.is_admin === true).
	const adminLinks: { label: string; path: string; kind: AdminIconKind }[] = [
		{ label: 'Usuários', path: '/admin/usuarios', kind: 'usuarios' },
		{ label: 'Órgãos', path: '/admin/orgaos', kind: 'orgaos' },
		{ label: 'Templates', path: '/admin/templates', kind: 'templates' },
		{ label: 'Novidades', path: '/admin/novidades', kind: 'novidades' }
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

	// Modais de export/import de CSV abertos pelo menu de conta.
	let exportCsvOpen = $state(false);
	let importCsvOpen = $state(false);
	let importOptions = $state<ProjectsListOptions | null>(null);
	let importOptionsEmVoo = false;

	function abrirExportarCsv(): void {
		closeAdmin();
		exportCsvOpen = true;
	}

	function fecharExportarCsv(): void {
		exportCsvOpen = false;
		adminToggleEl?.focus();
	}

	function abrirImportarCsv(): void {
		closeAdmin();
		importCsvOpen = true;
		carregarImportOptions();
	}

	function fecharImportarCsv(): void {
		importCsvOpen = false;
		adminToggleEl?.focus();
	}

	/** Options sob demanda: cache SWR primeiro; falha deixa null (o modal tolera). */
	function carregarImportOptions(): void {
		if (importOptions || importOptionsEmVoo) return;
		const cached = peekProjects();
		if (cached) {
			importOptions = cached.options;
			return;
		}
		// Guarda de voo: reabrir o modal antes da resposta nao dispara um 2o GET.
		importOptionsEmVoo = true;
		fetchProjects()
			.then((data) => (importOptions = data.options))
			.catch(() => {})
			.finally(() => (importOptionsEmVoo = false));
	}

	function handleCsvImported(): void {
		importCsvOpen = false;
		invalidateProjects();
		bumpProjectsRevision();
		adminToggleEl?.focus();
	}

	/** Esc fecha o menu e devolve foco ao botao acionador (o sino trata o seu). */
	function handleWindowKeydown(event: KeyboardEvent): void {
		if (event.key !== 'Escape' || !adminOpen) return;
		// Consome o gesto: o FlashToasts (listener irmão no window) checa
		// defaultPrevented para não dispensar um toast no MESMO Esc que
		// fechou este dropdown.
		event.preventDefault();
		closeAdmin();
		adminToggleEl?.focus();
	}

	/** Clique fora fecha o menu de conta (o sino cuida do próprio dropdown). */
	function handleAnyOutside(event: MouseEvent): void {
		const target = event.target as Node;
		if (adminOpen && adminMenuEl && !adminMenuEl.contains(target)) closeAdmin();
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
						class="relative z-[1] inline-flex h-[1.95rem] items-center gap-2 rounded-md px-3 text-md font-medium leading-none no-underline transition-colors duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] focus:outline-none focus-visible:ring-2 focus-visible:ring-on-brand {active
							? 'text-brand'
							: 'text-on-brand-muted hover:text-on-topnav'}"
					>
						<TopnavIcon kind={link.kind} {active} />
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

			<!-- Novidades: reabre o onboarding; ponto enquanto houver novidade não vista. -->
			<NovidadesBotao />

			<!-- Notificacoes: sino com ponto, polling do resumo e dropdown (NotificationBell). -->
			<NotificationBell userId={user?.id ?? null} />

			{#if user}
				<div bind:this={adminMenuEl} class="relative inline-flex">
					<button
						type="button"
						bind:this={adminToggleEl}
						onclick={toggleAdmin}
						aria-haspopup="menu"
						aria-expanded={adminOpen}
						aria-current={adminActive ? 'page' : undefined}
						title="Conta e administração"
						aria-label="Conta e administração"
						class="inline-flex h-[1.95rem] w-[1.95rem] items-center justify-center rounded-md border border-transparent text-md transition-ui duration-[180ms] focus:outline-none focus-visible:ring-2 focus-visible:ring-on-brand {adminActive ||
						adminOpen
							? 'border-surface-elevated bg-surface-elevated text-brand dark:border-[color-mix(in_srgb,var(--ds-color-neutral-0)_10%,transparent)] dark:bg-[color-mix(in_srgb,var(--ds-color-neutral-0)_15%,transparent)] dark:text-white'
							: 'bg-transparent text-on-brand-muted hover:bg-on-brand-hover hover:text-on-topnav'}"
					>
						<svg
							width="20"
							height="20"
							viewBox="0 0 24 24"
							fill="currentColor"
							class="shrink-0"
							aria-hidden="true"
						>
							<g class="nav-fade" opacity={adminOpen || adminActive ? 0 : 1}
								><path
									fill-rule="evenodd"
									d="M12 2.4A9.6 9.6 0 1 1 12 21.6A9.6 9.6 0 1 1 12 2.4ZM12 7A2.2 2.2 0 1 1 12 11.4A2.2 2.2 0 1 1 12 7ZM8.6 16.4A3.4 3.4 0 0 1 15.4 16.4Z"
								/></g
							>
							<g class="nav-fade" opacity={adminOpen || adminActive ? 1 : 0}
								><path
									fill-rule="evenodd"
									d="M12 2.4A9.6 9.6 0 1 1 12 21.6A9.6 9.6 0 1 1 12 2.4ZM12 8.1A3.1 3.1 0 1 1 12 14.3A3.1 3.1 0 1 1 12 8.1ZM7.36 19A4.9 4.9 0 0 1 16.64 19A8.4 8.4 0 0 1 7.36 19Z"
								/></g
							>
						</svg>
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
										<AdminMenuIcon kind={link.kind} />
										<span>{link.label}</span>
									</a>
								{/each}
								<hr class="my-1 border-border-subtle" />
							{/if}
							{#if AJUSTES_ENABLED}
							<a
								role="menuitem"
								href={`${base}/conta/ajustes`}
								aria-current={ajustesActive ? 'page' : undefined}
								onclick={closeAdmin}
								class="group flex items-center gap-3 px-4 py-2 text-sm no-underline transition-colors duration-fast focus:outline-none focus-visible:bg-surface-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand {ajustesActive
									? 'bg-surface-muted text-text-primary'
									: 'text-text-secondary hover:bg-surface-muted hover:text-text-primary'}"
							>
								<AdminMenuIcon kind="usuarios" />
								<span>Ajustes</span>
							</a>
							<hr class="my-1 border-border-subtle" />
							{/if}
							<button
								type="button"
								role="menuitem"
								onclick={abrirExportarCsv}
								class="group flex w-full items-center gap-3 px-4 py-2 text-left text-sm text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:bg-surface-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
							>
								<AdminMenuIcon kind="csv" />
								<span>Exportar CSV de projetos</span>
							</button>
							{#if user.is_admin}
								<button
									type="button"
									role="menuitem"
									onclick={abrirImportarCsv}
									class="group flex w-full items-center gap-3 px-4 py-2 text-left text-sm text-text-secondary transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:bg-surface-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
								>
									<AdminMenuIcon kind="csv-upload" />
									<span>Importar CSV de projetos</span>
								</button>
							{/if}
							<hr class="my-1 border-border-subtle" />
							<!-- Logout: rota Flask nativa /logout (fluxo fora da SPA), como no
								 dropdown do topnav Jinja v4.5. -->
							<a
								role="menuitem"
								href="/logout"
								data-sveltekit-reload
								class="group flex items-center gap-3 px-4 py-2 text-sm text-danger no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:bg-surface-muted focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
							>
								<AdminMenuIcon kind="sair" />
								<span>Sair</span>
							</a>
						</div>
					{/if}
				</div>
			{/if}

			<!-- Theme switch rolling (portado 1:1 de app_topnav.html + 00-foundation.css).
			     Escondido enquanto o modo escuro estiver incompleto (THEME_TOGGLE_ENABLED). -->
			{#if THEME_TOGGLE_ENABLED}
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
			{/if}
		</div>
	</div>
</header>

<ExportarProjetosModal open={exportCsvOpen} permitirEscopoLista={false} onClose={fecharExportarCsv} />
<ImportarCsvModal
	open={importCsvOpen}
	options={importOptions}
	onClose={fecharImportarCsv}
	onImported={handleCsvImported}
/>

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

	.nav-fade {
		transition: opacity 0.22s;
	}
	@media (prefers-reduced-motion: reduce) {
		.nav-fade {
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
