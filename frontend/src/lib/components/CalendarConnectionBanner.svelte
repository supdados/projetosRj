<script lang="ts">
	/**
	 * Controles de conexao Google Calendar — cluster compacto que vive DENTRO do
	 * header do hub (paridade v4.5: templates/calendars/calendars.html). NAO e um
	 * card grande; sao os botoes de acao a direita do toggle de visao.
	 *
	 * Tres estados:
	 *   1. Conectado (`connection`): botao-icone "Sincronizar agora" (com tooltip
	 *      da ultima sync), botao "Renovar watch" (apenas quando o watch expira em
	 *      breve) e botao "Desconectar" sutil.
	 *   2. Habilitado e sem conexao (`googleEnabled && !connection`): link
	 *      "Conectar" (com icone de elo) — navegacao top-level para o OAuth do
	 *      Flask, FORA da SPA (base `/static/spa`).
	 *   3. Integracao desabilitada (`!googleEnabled`): nada (o aviso fica na pagina).
	 *
	 * O fluxo OAuth de inicio (`/calendar/oauth/start`) NAO esta sob a SPA; por
	 * isso usamos `<a href>` absoluto para a origem do Flask, navegacao full-page.
	 */
	import type { CalendarConnection } from '$lib/types/calendar';

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

	const connectUrl = $derived(
		typeof window !== 'undefined'
			? `${window.location.origin}/calendar/oauth/start`
			: '/calendar/oauth/start'
	);

	const syncTitle = $derived(
		connection?.last_sync_at_display
			? `Última sincronização: ${connection.last_sync_at_display}`
			: 'Sincronizar agora'
	);

	function handleDisconnect(): void {
		if (typeof window !== 'undefined') {
			const ok = window.confirm(
				'Desconectar a conta Google Calendar? A sincronização será interrompida.'
			);
			if (!ok) return;
		}
		onDisconnect();
	}
</script>

{#if connection}
	<!-- Sincronizar agora (cal-btn-icon). -->
	<button
		type="button"
		class="cal-btn-icon"
		title={syncTitle}
		aria-label="Sincronizar com o Google agora"
		disabled={busy}
		onclick={onSync}
	>
		<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
			<polyline points="1 4 1 10 7 10" />
			<polyline points="23 20 23 14 17 14" />
			<path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15" />
		</svg>
	</button>
	{#if connection.watch_expiring_soon}
		<!-- Renovar watch — icone-sino, visivel apenas quando expira em breve. -->
		<button
			type="button"
			class="cal-btn-icon cal-btn-icon--warn"
			title={connection.watch_expiration_display
				? `Renovar watch (expira em ${connection.watch_expiration_display})`
				: 'Renovar watch (expira em breve)'}
			aria-label="Renovar watch do Google Calendar"
			disabled={busy}
			onclick={onRenewWatch}
		>
			<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
				<path d="M13.73 21a2 2 0 0 1-3.46 0" />
			</svg>
		</button>
	{/if}
	<!-- Desconectar — icone de elo partido (espelha o "Conectar"). -->
	<button
		type="button"
		class="cal-btn-icon cal-btn-icon--danger"
		title="Desconectar a conta Google Calendar"
		aria-label="Desconectar a conta Google Calendar"
		disabled={busy}
		onclick={handleDisconnect}
	>
		<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
			<path d="M18.84 12.25l1.72-1.71a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
			<path d="M5.17 11.75l-1.71 1.71a5 5 0 0 0 7.07 7.07l1.71-1.71" />
			<line x1="8" y1="2" x2="8" y2="5" />
			<line x1="2" y1="8" x2="5" y2="8" />
			<line x1="16" y1="19" x2="16" y2="22" />
			<line x1="19" y1="16" x2="22" y2="16" />
		</svg>
	</button>
{:else if googleEnabled}
	<!-- Conectar (cal-btn-sm) com icone de elo. -->
	<a href={connectUrl} class="cal-btn-sm">
		<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
			<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
			<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
		</svg>
		Conectar
	</a>
{/if}

<style>
	/* Botao-icone (sync) — cal-btn-icon de calendars.css. */
	.cal-btn-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.9rem;
		height: 1.9rem;
		border-radius: 0.4rem;
		border: 1px solid var(--color-border);
		background: none;
		color: var(--color-text-secondary);
		cursor: pointer;
		flex-shrink: 0;
		transition:
			background 0.12s,
			color 0.12s;
	}
	.cal-btn-icon:hover:not(:disabled) {
		background: var(--color-surface-muted);
		color: var(--color-text-primary);
	}
	.cal-btn-icon:disabled {
		opacity: 0.5;
		cursor: default;
	}
	/* Renovar watch: tom de alerta (so aparece quando o watch expira em breve). */
	.cal-btn-icon--warn {
		color: var(--ds-color-warning-600);
		border-color: rgba(202, 138, 4, 0.3);
	}
	.cal-btn-icon--warn:hover:not(:disabled) {
		background: rgba(202, 138, 4, 0.08);
		color: var(--ds-color-warning-600);
	}
	/* Desconectar: tom de perigo, borda sutil ate o hover. */
	.cal-btn-icon--danger {
		color: var(--ds-color-danger-600);
		border-color: transparent;
	}
	.cal-btn-icon--danger:hover:not(:disabled) {
		border-color: rgba(220, 38, 38, 0.18);
		background: rgba(220, 38, 38, 0.07);
		color: var(--ds-color-danger-600);
	}

	.cal-btn-sm {
		display: inline-flex;
		align-items: center;
		gap: 0.28rem;
		padding: 0.36rem 0.65rem;
		background: none;
		border: 1px solid var(--color-border);
		border-radius: 0.4rem;
		font-size: 0.8rem;
		color: var(--color-text-secondary);
		cursor: pointer;
		white-space: nowrap;
		transition:
			background 0.12s,
			border-color 0.12s;
		text-decoration: none;
		flex-shrink: 0;
	}
	.cal-btn-sm:hover:not(:disabled) {
		background: var(--color-surface-muted);
	}
	.cal-btn-sm:disabled {
		opacity: 0.5;
		cursor: default;
	}

	@media (prefers-reduced-motion: reduce) {
		.cal-btn-icon,
		.cal-btn-sm {
			transition: none;
		}
	}
</style>
