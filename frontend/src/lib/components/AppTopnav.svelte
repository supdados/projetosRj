<script lang="ts">
	/**
	 * Topnav minima do app shell (PILOTO): titulo + theme toggle + nome do
	 * usuario. Stubs visuais (busca/notificacoes/chatbot) NAO sao implementados
	 * nesta etapa — apenas o necessario para o Dashboard renderizar.
	 */
	import { base } from '$app/paths';
	import { theme, toggleTheme } from '$lib/stores/theme';
	import type { User } from '$lib/types/entities';

	interface Props {
		user: User | null;
	}

	let { user }: Props = $props();
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
