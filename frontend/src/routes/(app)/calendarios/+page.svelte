<script lang="ts">
	/**
	 * Tela "Calendario": agenda do usuario + estado da conexao Google Calendar.
	 *
	 * No mount carrega o hub (`getCalendarHub` -> `GET /api/calendarios`) e
	 * renderiza, do topo para baixo:
	 *   1. <CalendarConnectionBanner> com o estado da conexao Google e acoes
	 *      (sincronizar / renovar watch / desconectar) que chamam a api e
	 *      RE-BUSCAM o hub.
	 *   2. Botao "Novo evento" + lista/agenda dos eventos, ordenada por data e
	 *      agrupada por dia. Cada evento mostra titulo, horario, local, Meet e —
	 *      quando `sync_status === "error"` — um aviso DEGRADADO por evento (o
	 *      evento NUNCA e escondido).
	 *
	 * O CRUD de evento e delegado ao <CalendarEventModal> (controlado): a pagina
	 * chama `createEvent`/`updateEvent`/`deleteEvent`/`generateMeet` (rotas
	 * legadas via `Accept: application/json`, ver lib/api/calendars.ts) e
	 * recarrega o hub. Falha de SYNC nunca bloqueia o salvar (o evento persiste
	 * com `sync_status` pending/error); por isso so o erro estruturado de escrita
	 * mantem o modal aberto via prop `error`.
	 *
	 * Estados de loading/erro sao anunciados via aria-live (role=status/alert).
	 * Foco/Esc do modal sao tratados pelo proprio componente.
	 */
	import { onMount } from 'svelte';
	import {
		getCalendarHub,
		disconnectGoogle,
		syncNow,
		renewWatch,
		createEvent,
		updateEvent,
		deleteEvent,
		generateMeet
	} from '$lib/api/calendars';
	import { ApiClientError } from '$lib/api/client';
	import type {
		CalendarEvent,
		CalendarEventInput,
		CalendarHub
	} from '$lib/types/calendar';
	import CalendarConnectionBanner from '$lib/components/CalendarConnectionBanner.svelte';
	import CalendarEventModal from '$lib/components/CalendarEventModal.svelte';

	type LoadState = 'loading' | 'ready' | 'error';

	let loadState = $state<LoadState>('loading');
	let hub = $state<CalendarHub | null>(null);
	let errorMessage = $state<string>('');

	/** Operacao de conexao (sync/watch/disconnect) em andamento. */
	let connectionBusy = $state<boolean>(false);

	// Estado do modal de evento.
	let modalOpen = $state<boolean>(false);
	let modalEvent = $state<CalendarEvent | null>(null);
	let modalBusy = $state<boolean>(false);
	let modalError = $state<string | null>(null);

	let inFlight: AbortController | null = null;

	function readErrorMessage(err: unknown, fallback: string): string {
		if (err instanceof Error && err.message) return err.message;
		return fallback;
	}

	/** Carrega (ou recarrega) o hub. 401 ja redireciona em client.ts. */
	async function load(): Promise<void> {
		loadState = hub ? loadState : 'loading';
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		try {
			const next = await getCalendarHub(controller.signal);
			if (controller.signal.aborted) return;
			hub = next;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage = readErrorMessage(err, 'Falha ao carregar o calendario.');
			loadState = 'error';
		}
	}

	onMount(() => {
		void load();
		return () => inFlight?.abort();
	});

	// --- Acoes de conexao Google. Recarregam o hub no sucesso; erro vira alerta
	// de pagina (o banner nao tem slot de erro proprio). ---

	async function runConnectionAction(
		action: () => Promise<unknown>,
		fallback: string
	): Promise<void> {
		if (connectionBusy) return;
		connectionBusy = true;
		errorMessage = '';
		try {
			await action();
			await load();
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			errorMessage = readErrorMessage(err, fallback);
			loadState = 'error';
		} finally {
			connectionBusy = false;
		}
	}

	function handleSync(): void {
		void runConnectionAction(() => syncNow(), 'Falha ao sincronizar com o Google.');
	}

	function handleRenewWatch(): void {
		void runConnectionAction(() => renewWatch(), 'Falha ao renovar o watch.');
	}

	function handleDisconnect(): void {
		void runConnectionAction(
			() => disconnectGoogle(),
			'Falha ao desconectar a conta Google.'
		);
	}

	// --- Modal de evento. ---

	function openCreate(): void {
		modalEvent = null;
		modalError = null;
		modalBusy = false;
		modalOpen = true;
	}

	function openEdit(event: CalendarEvent): void {
		modalEvent = event;
		modalError = null;
		modalBusy = false;
		modalOpen = true;
	}

	function closeModal(): void {
		if (modalBusy) return;
		modalOpen = false;
		modalEvent = null;
		modalError = null;
	}

	/**
	 * Executa uma operacao de escrita do modal e, no sucesso, recarrega o hub e
	 * fecha o modal. Erro estruturado de escrita mantem o modal aberto (prop
	 * `error`). Falha de sync nunca cai aqui: o backend salva o evento e responde
	 * `{ok:true}` mesmo com `sync_status` pending/error.
	 */
	async function runModalAction(
		action: () => Promise<unknown>,
		fallback: string
	): Promise<void> {
		if (modalBusy) return;
		modalBusy = true;
		modalError = null;
		try {
			await action();
			await load();
			modalBusy = false;
			modalOpen = false;
			modalEvent = null;
		} catch (err) {
			modalBusy = false;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			modalError = readErrorMessage(err, fallback);
		}
	}

	function handleSave(input: CalendarEventInput): void {
		const editing = modalEvent;
		if (editing) {
			void runModalAction(
				() => updateEvent(editing.id, input),
				'Nao foi possivel salvar o evento.'
			);
			return;
		}
		void runModalAction(
			() => createEvent(input),
			'Nao foi possivel criar o evento.'
		);
	}

	function handleDelete(id: number): void {
		void runModalAction(() => deleteEvent(id), 'Nao foi possivel excluir o evento.');
	}

	function handleGenerateMeet(id: number): void {
		void runModalAction(
			() => generateMeet(id),
			'Nao foi possivel gerar o Google Meet.'
		);
	}

	// --- Agrupamento por dia. ---

	interface DayGroup {
		key: string;
		label: string;
		events: CalendarEvent[];
	}

	/**
	 * Rotulo do dia a partir do `starts_at` de input (`YYYY-MM-DDTHH:mm`). Cai
	 * para o trecho de data quando nao houver hora; eventos sem data vao para um
	 * grupo "Sem data" ao final (chave vazia ordena primeiro, entao a movemos).
	 */
	function dayKeyOf(event: CalendarEvent): string {
		const raw = event.starts_at ?? '';
		const datePart = raw.split('T')[0] ?? '';
		return datePart;
	}

	function dayLabelOf(key: string): string {
		if (key === '') return 'Sem data';
		const date = new Date(`${key}T00:00:00`);
		if (Number.isNaN(date.getTime())) return key;
		return date.toLocaleDateString('pt-BR', {
			weekday: 'long',
			day: '2-digit',
			month: 'long',
			year: 'numeric'
		});
	}

	const dayGroups = $derived.by<DayGroup[]>(() => {
		const events = hub?.events ?? [];
		const byKey = new Map<string, CalendarEvent[]>();
		for (const event of events) {
			const key = dayKeyOf(event);
			const bucket = byKey.get(key);
			if (bucket) bucket.push(event);
			else byKey.set(key, [event]);
		}
		const groups: DayGroup[] = [];
		for (const [key, list] of byKey) {
			groups.push({ key, label: dayLabelOf(key), events: list });
		}
		// Eventos ja vem ordenados por starts_at asc; a Map preserva a ordem de
		// insercao, entao basta empurrar o grupo "Sem data" (key vazia) ao final.
		groups.sort((a, b) => {
			if (a.key === b.key) return 0;
			if (a.key === '') return 1;
			if (b.key === '') return -1;
			return 0;
		});
		return groups;
	});

	const eventCount = $derived(hub?.events.length ?? 0);

	function timeRangeOf(event: CalendarEvent): string {
		if (event.is_all_day) return 'Dia inteiro';
		const start = event.starts_at_display ?? '';
		const end = event.ends_at_display ?? '';
		if (start && end) return `${start} — ${end}`;
		return start || end;
	}
</script>

<svelte:head>
	<title>Calendarios — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="calendarios-title" class="flex flex-col gap-6">
	<header class="flex flex-col gap-2">
		<div class="flex flex-wrap items-center gap-3">
			<h1
				id="calendarios-title"
				class="font-heading text-2xl font-bold text-text-primary"
			>
				Calendarios
			</h1>
			{#if loadState === 'ready'}
				<span
					class="inline-flex items-center gap-1 rounded-sm border border-primary-500 bg-primary-100 px-2 py-1 text-xs font-medium text-primary-700"
				>
					{eventCount} evento{eventCount === 1 ? '' : 's'}
				</span>
			{/if}
		</div>
		<p class="text-sm text-text-secondary">
			Seus eventos, ordenados por data. Conecte o Google Calendar para
			sincronizar automaticamente.
		</p>
	</header>

	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">
			Carregando calendario…
		</p>
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			<p class="text-text-primary">{errorMessage}</p>
			<button
				type="button"
				onclick={() => load()}
				class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Tentar novamente
			</button>
		</div>
	{:else if hub}
		<CalendarConnectionBanner
			connection={hub.connection}
			googleEnabled={hub.google_calendar_enabled}
			onSync={handleSync}
			onRenewWatch={handleRenewWatch}
			onDisconnect={handleDisconnect}
			busy={connectionBusy}
		/>

		<div class="flex flex-wrap items-center justify-between gap-3">
			<h2 class="font-heading text-lg font-semibold text-text-primary">Agenda</h2>
			<button
				type="button"
				onclick={openCreate}
				class="rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Novo evento
			</button>
		</div>

		{#if eventCount === 0}
			<div
				role="status"
				aria-live="polite"
				class="rounded-lg border border-border-subtle bg-surface px-5 py-8 text-center text-text-muted"
			>
				Nenhum evento ainda. Crie o primeiro com "Novo evento".
			</div>
		{:else}
			<div class="flex flex-col gap-5" aria-busy={connectionBusy}>
				{#each dayGroups as group (group.key)}
					<div class="flex flex-col gap-2">
						<h3
							class="text-xs font-semibold uppercase tracking-wide text-text-muted"
						>
							{group.label}
						</h3>
						<ul class="flex flex-col gap-2">
							{#each group.events as event (event.id)}
								<li
									class="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface px-4 py-3"
								>
									<button
										type="button"
										onclick={() => openEdit(event)}
										class="flex flex-col gap-1 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
									>
										<span
											class="text-sm font-medium text-text-primary hover:text-primary-700"
										>
											{event.title}
										</span>
										<span class="text-xs text-text-secondary">
											{timeRangeOf(event)}
										</span>
									</button>

									{#if event.location}
										<p class="text-xs text-text-muted">{event.location}</p>
									{/if}

									{#if event.meet_link}
										<p class="text-xs">
											<a
												href={event.meet_link}
												target="_blank"
												rel="noopener noreferrer"
												class="text-primary-700 underline hover:text-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
											>
												Entrar no Google Meet
											</a>
										</p>
									{/if}

									{#if event.sync_status === 'error'}
										<!-- Aviso degradado por evento: NUNCA esconde o evento. -->
										<p
											role="status"
											aria-live="polite"
											class="rounded-md border border-warning bg-surface-muted px-2 py-1 text-xs text-warning"
										>
											Falha de sincronizacao com o Google{event.sync_error
												? `: ${event.sync_error}`
												: '.'}
										</p>
									{:else if event.sync_status === 'pending'}
										<p class="text-xs text-text-muted">
											Aguardando sincronizacao com o Google.
										</p>
									{/if}
								</li>
							{/each}
						</ul>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</section>

<CalendarEventModal
	open={modalOpen}
	event={modalEvent}
	busy={modalBusy}
	error={modalError}
	onSave={handleSave}
	onDelete={handleDelete}
	onGenerateMeet={handleGenerateMeet}
	onClose={closeModal}
/>
