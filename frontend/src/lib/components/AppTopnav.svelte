<script lang="ts">
	/**
	 * Topnav do app shell: barra azul com brand + navegacao por icones +
	 * busca global (placeholder visual) + seletor de orgao (placeholder) +
	 * notificacoes (placeholder) + menu de conta/admin + theme toggle rolling.
	 *
	 * Visual portado 1:1 de templates/partials/app_topnav.html (v4.5) e das
	 * regras .app-topnav* de static/css/legacy/00-foundation.css + o switch de
	 * tema de codepen.io/jkantner. Fiacao 100% preservada: links base-aware
	 * (`$app/paths`), link ativo via `aria-current="page"` comparando
	 * `$page.url.pathname`, store de tema (`$theme`/`toggleTheme`) e o menu
	 * Admin acessivel ja existentes.
	 */
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import { theme, toggleTheme } from '$lib/stores/theme';
	import type { User } from '$lib/types/entities';

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

	const navLinks: NavLink[] = [
		{ label: 'Dashboard', path: '/dashboard', icon: 'fa-home' },
		{ label: 'Projetos', path: '/projetos', icon: 'fa-folder-open' },
		{ label: 'Pendentes', path: '/projetos/pendentes', icon: 'fa-exclamation-triangle' },
		{ label: 'Tarefas', path: '/tarefas', icon: 'fa-tasks' },
		{ label: 'Calendarios', path: '/calendarios', icon: 'fa-calendar-alt' },
		{ label: 'Busca', path: '/busca', icon: 'fa-search' }
	];

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

	/** Fecha ao clicar fora do menu (somente quando aberto). */
	function handleWindowPointer(event: MouseEvent): void {
		if (!adminOpen) return;
		if (adminMenuEl && !adminMenuEl.contains(event.target as Node)) {
			closeAdmin();
		}
	}

	let adminToggleEl = $state<HTMLButtonElement | null>(null);

	/** Esc fecha o menu e devolve foco ao botao acionador. */
	function handleWindowKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape' && adminOpen) {
			closeAdmin();
			adminToggleEl?.focus();
		}
	}
</script>

<svelte:window onclick={handleWindowPointer} onkeydown={handleWindowKeydown} />

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

			<nav aria-label="Navegacao principal" class="inline-flex items-center gap-2">
				{#each navLinks as link (link.path)}
					{@const active = isActive(link.path, pathname)}
					<a
						href={`${base}${link.path}`}
						aria-current={active ? 'page' : undefined}
						title={link.label}
						aria-label={link.label}
						class="inline-flex h-[1.95rem] w-[1.95rem] items-center justify-center rounded-md border border-transparent text-[0.9rem] no-underline transition-all duration-[180ms] ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70 {active
							? 'border-white bg-white text-primary-700'
							: 'bg-transparent text-white/[0.78] hover:bg-white/10 hover:text-white'}"
					>
						<i class="fas {link.icon}" aria-hidden="true"></i>
					</a>
				{/each}
			</nav>
		</div>

		<!-- Centro: seletor de orgao (placeholder visual, sem chamada de API) -->
		<div
			class="absolute left-1/2 z-[2] hidden -translate-x-1/2 items-center justify-center lg:flex"
		>
			<span
				class="inline-flex max-w-[320px] items-center gap-[0.55rem] rounded-md px-[0.7rem] py-[0.32rem] text-[0.85rem] font-medium leading-snug text-white"
			>
				<span class="text-[0.92rem] text-white/90" aria-hidden="true">
					<i class="fas fa-sitemap"></i>
				</span>
				<span class="truncate font-semibold tracking-[0.01em]">Todos os orgaos</span>
				<span class="ml-[0.2rem] text-[0.7rem] text-white/85" aria-hidden="true">
					<i class="fas fa-chevron-down"></i>
				</span>
			</span>
		</div>

		<!-- Direita: busca + notificacoes + conta/admin + theme toggle -->
		<div class="ml-auto flex flex-[0_0_auto] items-center justify-end gap-[1.1rem]">
			<!-- Busca global (placeholder visual; link para a rota de busca existente) -->
			<a
				href={`${base}/busca`}
				role="search"
				aria-label="Busca global"
				class="hidden w-[clamp(210px,24vw,340px)] items-center gap-[0.4rem] rounded-md border border-white/65 bg-white/[0.92] px-[0.6rem] py-[0.32rem] no-underline transition-colors duration-[180ms] hover:border-white hover:bg-white focus:outline-none focus-visible:border-white focus-visible:bg-white focus-visible:ring-[3px] focus-visible:ring-white/25 md:inline-flex"
			>
				<i class="fas fa-search text-[0.8rem] text-primary-700" aria-hidden="true"></i>
				<span class="truncate text-[0.85rem] leading-snug text-primary-700/65">
					Buscar projetos, etapas, tarefas e eventos...
				</span>
			</a>

			<!-- Notificacoes (placeholder visual; sem badge ativo / sem fetch) -->
			<button
				type="button"
				title="Notificacoes"
				aria-label="Notificacoes"
				disabled
				class="relative inline-flex h-[1.95rem] w-[1.95rem] cursor-default items-center justify-center rounded-md border border-transparent text-[0.9rem] text-white/[0.78] transition-all duration-[180ms] hover:bg-white/10 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
			>
				<i class="fas fa-bell" aria-hidden="true"></i>
			</button>

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
				<svg class="app-theme-switch__icon" width="24" height="24" aria-hidden="true">
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
				<svg class="app-theme-switch__icon" width="24" height="24" aria-hidden="true">
					<path
						fill="currentColor"
						d="M15.1,14.9c-3-0.5-5.5-3-6-6C8.8,7.1,9.1,5.4,9.9,4c0.4-0.8-0.4-1.7-1.2-1.4C4.6,4,1.8,7.9,2,12.5c0.2,5.1,4.4,9.3,9.5,9.5c4.5,0.2,8.5-2.6,9.9-6.6c0.3-0.8-0.6-1.7-1.4-1.2C18.6,14.9,16.9,15.2,15.1,14.9z"
					/>
				</svg>
				<span class="app-theme-switch__inner"></span>
				<span class="app-theme-switch__inner-icons">
					<svg class="app-theme-switch__icon" width="24" height="24" aria-hidden="true">
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
					<svg class="app-theme-switch__icon" width="24" height="24" aria-hidden="true">
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
