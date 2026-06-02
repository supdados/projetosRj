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
	 * chama `createEvent`/`updateEvent`/`deleteEvent`/`generateMeet` (endpoints
	 * /api dedicados no envelope `{ok,data}`, ver lib/api/calendars.ts) e
	 * recarrega o hub. Falha de SYNC nunca bloqueia o salvar (o evento persiste
	 * com `sync_status` pending/error); por isso so o erro estruturado de escrita
	 * mantem o modal aberto via prop `error`.
	 *
	 * FIDELIDADE ao flash legado: criar/editar devolvem `sync_message` e excluir
	 * devolve `remote_warning` opcional; a pagina os exibe num aviso aria-live
	 * pos-acao (`actionNotice`), equivalente ao flash success/warning do Jinja,
	 * alem do badge degradado por evento que ja existia. Gerar Meet copia o link
	 * para a area de transferencia e mostra um aviso efemero "Link copiado!".
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
		CalendarEventMutationResult,
		CalendarEventDeleteResult,
		CalendarHub
	} from '$lib/types/calendar';
	import CalendarConnectionBanner from '$lib/components/CalendarConnectionBanner.svelte';
	import CalendarEventModal from '$lib/components/CalendarEventModal.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';

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

	/**
	 * Aviso pos-acao (equivalente ao flash legado): mensagem de sync ao salvar,
	 * remote_warning ao excluir, ou "Link copiado!" ao gerar Meet. `tone` mapeia
	 * o estilo (success/warning) e a semantica aria (status/alert).
	 */
	let actionNotice = $state<{ message: string; tone: 'success' | 'warning' } | null>(
		null
	);
	let noticeTimer: ReturnType<typeof setTimeout> | null = null;

	/**
	 * Mostra o aviso pos-acao e o auto-descarta em ~2.2s (paridade com o
	 * auto-dismiss do flash legado, static/js/app-shell/flash.js).
	 */
	function showNotice(message: string, tone: 'success' | 'warning'): void {
		if (noticeTimer) clearTimeout(noticeTimer);
		actionNotice = { message, tone };
		noticeTimer = setTimeout(() => {
			actionNotice = null;
			noticeTimer = null;
		}, 2200);
	}

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
		return () => {
			inFlight?.abort();
			if (noticeTimer) clearTimeout(noticeTimer);
		};
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
	 * Executa uma operacao de escrita do modal e, no sucesso, recarrega o hub,
	 * fecha o modal e devolve o resultado (para o chamador exibir o aviso de
	 * sync). Erro estruturado de escrita mantem o modal aberto (prop `error`).
	 * Falha de sync nunca cai aqui: o backend salva o evento e responde `{ok}`
	 * mesmo com `sync_status` pending/error (vem em `sync_outcome`/`sync_message`).
	 */
	async function runModalAction<T>(
		action: () => Promise<T>,
		fallback: string
	): Promise<T | null> {
		if (modalBusy) return null;
		modalBusy = true;
		modalError = null;
		try {
			const result = await action();
			await load();
			modalBusy = false;
			modalOpen = false;
			modalEvent = null;
			return result;
		} catch (err) {
			modalBusy = false;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return null;
			modalError = readErrorMessage(err, fallback);
			return null;
		}
	}

	/** tone do aviso a partir do desfecho de sync (success exceto em sync_error). */
	function noticeToneFor(result: CalendarEventMutationResult): 'success' | 'warning' {
		return result.sync_outcome === 'sync_error' ? 'warning' : 'success';
	}

	function handleSave(input: CalendarEventInput): void {
		const editing = modalEvent;
		const action = editing
			? () => updateEvent(editing.id, input)
			: () => createEvent(input);
		const fallback = editing
			? 'Nao foi possivel salvar o evento.'
			: 'Nao foi possivel criar o evento.';
		void runModalAction(action, fallback).then((result) => {
			if (result) showNotice(result.sync_message, noticeToneFor(result));
		});
	}

	function handleDelete(id: number): void {
		void runModalAction<CalendarEventDeleteResult>(
			() => deleteEvent(id),
			'Nao foi possivel excluir o evento.'
		).then((result) => {
			if (!result) return;
			if (result.remote_warning) {
				showNotice(
					`Evento removido localmente, mas falhou no Google: ${result.remote_warning}`,
					'warning'
				);
			} else {
				showNotice('Evento removido com sucesso.', 'success');
			}
		});
	}

	/**
	 * Gera o link do Meet e, no sucesso, copia-o para a area de transferencia
	 * mostrando o aviso efemero "Link copiado!" (paridade com o toast legado
	 * `showCopyToast` ~1.7s; aqui reusamos o `actionNotice` ~2.2s). A copia e
	 * best-effort: se a Clipboard API falhar/indisponivel, ainda confirmamos a
	 * geracao do link.
	 */
	function handleGenerateMeet(id: number): void {
		void runModalAction<{ event: CalendarEvent }>(
			() => generateMeet(id),
			'Nao foi possivel gerar o Google Meet.'
		).then(async (result) => {
			const link = result?.event.meet_link;
			if (!link) return;
			try {
				await navigator.clipboard?.writeText(link);
				showNotice('Link copiado!', 'success');
			} catch {
				showNotice('Link do Meet gerado com sucesso.', 'success');
			}
		});
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

	/**
	 * Cor da barra lateral do evento na lista (cal-list-bar) por estado de sync,
	 * 1:1 com o original: erro = danger, pendente = cinza (#94a3b8), sincronizado
	 * com o Google = verde (#0f9d58), local = primary.
	 */
	function syncBarClass(event: CalendarEvent): string {
		if (event.sync_status === 'error') return 'bg-danger';
		if (event.sync_status === 'pending') return 'bg-[#94a3b8]';
		if (event.source === 'google') return 'bg-[#0f9d58]';
		return 'bg-primary-600';
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
		<LoadErrorState message={errorMessage} onRetry={() => load()} />
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
				class="inline-flex items-center gap-[0.3rem] whitespace-nowrap rounded-[0.45rem] bg-primary-600 px-[0.85rem] py-[0.42rem] text-sm font-medium text-white transition-colors duration-fast hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				<svg
					width="12"
					height="12"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2.5"
					stroke-linecap="round"
					aria-hidden="true"
				>
					<line x1="12" y1="5" x2="12" y2="19" />
					<line x1="5" y1="12" x2="19" y2="12" />
				</svg>
				Novo evento
			</button>
		</div>

		{#if actionNotice}
			<!-- Aviso pos-acao equivalente ao flash legado (auto-dismiss ~2.2s). -->
			<p
				role={actionNotice.tone === 'warning' ? 'alert' : 'status'}
				aria-live={actionNotice.tone === 'warning' ? 'assertive' : 'polite'}
				class={actionNotice.tone === 'warning'
					? 'rounded-md border border-warning bg-surface-muted px-4 py-2 text-sm text-warning'
					: 'rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm text-primary-700'}
			>
				{actionNotice.message}
			</p>
		{/if}

		{#if eventCount === 0}
			<div
				role="status"
				aria-live="polite"
				class="rounded-[0.7rem] border border-dashed border-border-subtle px-4 py-12 text-center text-sm text-text-muted"
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
						<ul class="flex flex-col gap-[0.35rem]">
							{#each group.events as event (event.id)}
								<!-- cal-list-event: borda + hover border-primary/shadow; barra lateral por sync. -->
								<li
									class="group flex items-start gap-[0.7rem] rounded-[0.55rem] border border-border-subtle bg-surface px-[0.7rem] py-[0.6rem] transition-[border-color,box-shadow] duration-fast hover:border-primary-500 hover:shadow-[0_2px_8px_rgba(0,90,146,0.08)]"
								>
									<!-- cal-list-bar: faixa colorida 3px. -->
									<span
										class="min-h-[2rem] w-[3px] flex-shrink-0 self-stretch rounded-[2px] {syncBarClass(
											event
										)}"
										aria-hidden="true"
									></span>

									<div class="min-w-0 flex-1">
										<button
											type="button"
											onclick={() => openEdit(event)}
											class="flex w-full flex-col gap-1 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
										>
											<span
												class="truncate text-md font-medium text-text-primary group-hover:text-primary-700"
											>
												{event.title}
											</span>
											<span class="text-xs text-text-muted">
												{timeRangeOf(event)}
											</span>
										</button>

										<div class="mt-[0.22rem] flex flex-wrap items-center gap-[0.6rem]">
											{#if event.location}
												<span class="text-xs text-text-muted">{event.location}</span>
											{/if}

											{#if event.meet_link}
												<!-- cal-meta-meet: pilula verde com icone de video. -->
												<a
													href={event.meet_link}
													target="_blank"
													rel="noopener noreferrer"
													class="inline-flex items-center gap-[0.25rem] rounded-[0.3rem] bg-[#00832d] py-[0.18rem] pl-[0.35rem] pr-[0.45rem] text-xs font-medium text-white no-underline transition-colors duration-fast hover:bg-[#006625] focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
												>
													<svg width="12" height="12" viewBox="0 0 24 24" fill="white" aria-hidden="true">
														<path
															d="M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4v-11l-4 4z"
														/>
													</svg>
													Meet
												</a>
											{/if}

											{#if event.sync_status === 'error'}
												<!-- cal-sync-badge--error: pilula danger. -->
												<span
													class="inline-flex items-center rounded-full border border-danger/20 bg-danger/[0.08] px-[0.38rem] py-[0.1rem] text-2xs text-danger"
												>
													Erro de sync
												</span>
											{:else if event.sync_status === 'pending'}
												<!-- cal-sync-badge--pending: pilula cinza. -->
												<span
													class="inline-flex items-center rounded-full border border-border-subtle bg-surface-muted px-[0.38rem] py-[0.1rem] text-2xs text-text-muted"
												>
													Pendente
												</span>
											{:else if event.source === 'google'}
												<!-- cal-sync-badge--ok: pilula verde (sincronizado). -->
												<span
													class="inline-flex items-center rounded-full border border-success/20 bg-success/10 px-[0.38rem] py-[0.1rem] text-2xs text-success"
												>
													Sincronizado
												</span>
											{/if}
										</div>

										{#if event.sync_status === 'error'}
											<!-- Aviso degradado por evento: NUNCA esconde o evento. -->
											<p
												role="status"
												aria-live="polite"
												class="mt-2 rounded-md border border-warning bg-surface-muted px-2 py-1 text-xs text-warning"
											>
												Falha de sincronizacao com o Google{event.sync_error
													? `: ${event.sync_error}`
													: '.'}
											</p>
										{/if}
									</div>
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
