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
		<div class="flex items-center gap-2">
			<!-- Badge Google desligado (cal-google-badge--off): pilula muted. -->
			<span
				class="inline-flex flex-shrink-0 items-center gap-[0.3rem] whitespace-nowrap rounded-full border border-border-subtle bg-surface-muted px-2 py-[0.2rem] text-2xs font-medium leading-none text-text-muted"
			>
				<svg width="6" height="6" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="4" fill="currentColor" /></svg>
				Google
			</span>
			<p class="text-sm text-text-secondary">
				A integracao com o Google Calendar nao esta habilitada neste servidor.
			</p>
		</div>
	{:else if !connection}
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div class="flex items-center gap-2">
				<span
					class="inline-flex flex-shrink-0 items-center gap-[0.3rem] whitespace-nowrap rounded-full border border-border-subtle bg-surface-muted px-2 py-[0.2rem] text-2xs font-medium leading-none text-text-muted"
				>
					<svg width="6" height="6" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="4" fill="currentColor" /></svg>
					Google
				</span>
				<p class="text-sm text-text-secondary">
					Conecte sua conta Google para sincronizar eventos automaticamente.
				</p>
			</div>
			<!-- Botao conectar (cal-btn-sm) com icone de elo. -->
			<a
				href={connectUrl}
				class="inline-flex items-center gap-[0.28rem] whitespace-nowrap rounded-[0.4rem] border border-border-subtle bg-surface px-[0.65rem] py-[0.36rem] text-sm text-text-secondary no-underline transition-[background,border-color] duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<svg
					width="12"
					height="12"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2.5"
					stroke-linecap="round"
					stroke-linejoin="round"
					aria-hidden="true"
				>
					<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
					<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
				</svg>
				Conectar Google Calendar
			</a>
		</div>
	{:else}
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div class="space-y-1">
				<div class="flex flex-wrap items-center gap-2">
					<!-- Badge Google ligado (cal-google-badge--on): pilula verde. -->
					<span
						class="inline-flex flex-shrink-0 items-center gap-[0.3rem] whitespace-nowrap rounded-full border border-success/20 bg-success/10 px-2 py-[0.2rem] text-2xs font-medium leading-none text-success"
					>
						<svg width="6" height="6" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="4" fill="currentColor" /></svg>
						Google
					</span>
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
				<!-- Sincronizar agora: botao com icone de refresh (cal-btn-icon + texto). -->
				<button
					type="button"
					onclick={onSync}
					disabled={busy}
					class="inline-flex items-center gap-[0.3rem] whitespace-nowrap rounded-[0.4rem] border border-border-subtle bg-surface px-[0.65rem] py-[0.36rem] text-sm text-text-secondary transition-[background,border-color] duration-fast hover:bg-surface-muted disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<svg
						width="13"
						height="13"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2.5"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<polyline points="1 4 1 10 7 10" />
						<polyline points="23 20 23 14 17 14" />
						<path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15" />
					</svg>
					Sincronizar agora
				</button>
				<!-- Renovar watch (cal-btn-sm). -->
				<button
					type="button"
					onclick={onRenewWatch}
					disabled={busy}
					class="inline-flex items-center gap-[0.28rem] whitespace-nowrap rounded-[0.4rem] border border-border-subtle bg-surface px-[0.65rem] py-[0.36rem] text-sm text-text-secondary transition-[background,border-color] duration-fast hover:bg-surface-muted disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Renovar watch
				</button>
				<!-- Desconectar (cal-btn-sm--subtle): borda transparente que aparece no hover. -->
				<button
					type="button"
					onclick={handleDisconnect}
					disabled={busy}
					class="inline-flex items-center gap-[0.28rem] whitespace-nowrap rounded-[0.4rem] border border-transparent bg-transparent px-[0.65rem] py-[0.36rem] text-sm text-danger transition-[background,border-color] duration-fast hover:border-danger/20 hover:bg-danger/5 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
				>
					Desconectar
				</button>
			</div>
		</div>
	{/if}
</section>
