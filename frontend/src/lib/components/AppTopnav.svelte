<script lang="ts">
	/**
	 * Topnav do app shell: titulo + navegacao principal + theme toggle + nome do
	 * usuario. Links base-aware (`$app/paths`); o link ativo recebe
	 * `aria-current="page"` comparando `$page.url.pathname` (mesmo padrao usado
	 * em projetos/[id]/historico/+page.svelte).
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
	}

	const navLinks: NavLink[] = [
		{ label: 'Dashboard', path: '/dashboard' },
		{ label: 'Projetos', path: '/projetos' },
		{ label: 'Pendentes', path: '/projetos/pendentes' },
		{ label: 'Tarefas', path: '/tarefas' },
		{ label: 'Busca', path: '/busca' }
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
		// Nao marcar "/projetos" quando um link mais especifico cobre o path.
		return !navLinks.some(
			(other) =>
				other.path !== linkPath &&
				other.path.startsWith(linkPath) &&
				(current === `${base}${other.path}` ||
					current.startsWith(`${base}${other.path}/`))
		);
	}

	const pathname = $derived($page.url.pathname);
</script>

<header
	class="sticky top-0 z-sticky flex items-center justify-between gap-4 border-b border-border-subtle bg-surface px-5 py-3"
>
	<a
		href={`${base}/dashboard`}
		class="font-heading text-xl font-bold text-text-primary no-underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
	>
		ProjetosRJ
	</a>

	<nav aria-label="Navegacao principal" class="min-w-0 flex-1">
		<ul class="flex flex-wrap items-center gap-1 sm:gap-2">
			{#each navLinks as link (link.path)}
				{@const active = isActive(link.path, pathname)}
				<li>
					<a
						href={`${base}${link.path}`}
						aria-current={active ? 'page' : undefined}
						class="inline-flex items-center rounded-md px-3 py-1.5 text-sm font-medium no-underline transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {active
							? 'bg-surface-muted text-text-primary'
							: 'text-text-secondary hover:bg-surface-muted hover:text-text-primary'}"
					>
						{link.label}
					</a>
				</li>
			{/each}
		</ul>
	</nav>

	<div class="flex items-center gap-3">
		<button
			type="button"
			onclick={toggleTheme}
			aria-pressed={$theme === 'dark'}
			aria-label={$theme === 'dark'
				? 'Mudar para tema claro'
				: 'Mudar para tema escuro'}
			class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border-subtle bg-surface text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
		>
			<span aria-hidden="true">{$theme === 'dark' ? '☀' : '☾'}</span>
		</button>

		{#if user}
			<span class="text-sm text-text-secondary" title={user.username}>
				{user.name}
			</span>
		{/if}
	</div>
</header>
