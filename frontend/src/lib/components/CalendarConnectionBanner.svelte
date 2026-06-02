<script lang="ts">
	/**
	 * Banner do estado da conexao Google Calendar.
	 *
	 * Tres estados:
	 *   1. Integracao desabilitada no servidor (`!googleEnabled`): mensagem
	 *      informativa, sem acoes.
	 *   2. Habilitada e sem conexao (`googleEnabled && !connection`): botao
	 *      "Conectar Google Calendar".
	 *   3. Conectado (`connection`): email da conta, ultima sync e acoes de
	 *      sincronizar / renovar watch / desconectar.
	 *
	 * O fluxo OAuth de inicio (`/calendar/oauth/start`) NAO esta sob a SPA
	 * (base `/static/spa`); por isso usamos um `<a href>` absoluto para a
	 * origem do Flask (`window.location.origin + '/calendar/oauth/start'`),
	 * navegacao top-level, e NAO o router do SvelteKit / `base`.
	 */
	import type { CalendarConnection } from '$lib/types/calendar';
	import Badge from './Badge.svelte';

	interface Props {
		connection: CalendarConnection | null;
		googleEnabled: boolean;
		onDisconnect: () => void;
		onSync: () => void;
		onRenewWatch: () => void;
		busy?: boolean;
	}

	let {
		connection,
		googleEnabled,
		onDisconnect,
		onSync,
		onRenewWatch,
		busy = false
	}: Props = $props();

	/** URL absoluta do inicio do OAuth (fora da SPA). Navegacao full-page. */
	const connectUrl = $derived(
		typeof window !== 'undefined'
			? `${window.location.origin}/calendar/oauth/start`
			: '/calendar/oauth/start'
	);

	function handleDisconnect(): void {
		if (typeof window !== 'undefined') {
			const confirmed = window.confirm(
				'Desconectar a conta Google Calendar? A sincronizacao sera interrompida.'
			);
			if (!confirmed) return;
		}
		onDisconnect();
	}
</script>

<section
	class="rounded-md border border-border-subtle bg-surface px-4 py-3"
	aria-label="Conexao com o Google Calendar"
>
	{#if !googleEnabled}
		<p class="text-sm text-text-secondary">
			A integracao com o Google Calendar nao esta habilitada neste servidor.
		</p>
	{:else if !connection}
		<div class="flex flex-wrap items-center justify-between gap-3">
			<p class="text-sm text-text-secondary">
				Conecte sua conta Google para sincronizar eventos automaticamente.
			</p>
			<a
				href={connectUrl}
				class="rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Conectar Google Calendar
			</a>
		</div>
	{:else}
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div class="space-y-1">
				<div class="flex flex-wrap items-center gap-2">
					<Badge tone="success">Conectado</Badge>
					{#if connection.google_account_email}
						<span class="text-sm font-medium text-text-primary">
							{connection.google_account_email}
						</span>
					{/if}
				</div>
				{#if connection.last_sync_at_display}
					<p class="text-xs text-text-secondary">
						Ultima sincronizacao: {connection.last_sync_at_display}
					</p>
				{/if}
				{#if connection.watch_expiring_soon}
					<div class="pt-1">
						<Badge tone="warning">
							Watch expira em breve{connection.watch_expiration_display
								? `: ${connection.watch_expiration_display}`
								: ''}
						</Badge>
					</div>
				{/if}
			</div>

			<div class="flex flex-wrap items-center gap-2">
				<button
					type="button"
					onclick={onSync}
					disabled={busy}
					class="rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
				>
					Sincronizar agora
				</button>
				<button
					type="button"
					onclick={onRenewWatch}
					disabled={busy}
					class="rounded-md border border-border-subtle px-3 py-1.5 text-sm font-medium text-text-primary hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
				>
					Renovar watch
				</button>
				<button
					type="button"
					onclick={handleDisconnect}
					disabled={busy}
					class="rounded-md border border-danger px-3 py-1.5 text-sm font-medium text-danger hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
				>
					Desconectar
				</button>
			</div>
		</div>
	{/if}
</section>
