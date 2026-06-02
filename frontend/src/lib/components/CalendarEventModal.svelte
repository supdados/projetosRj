<script lang="ts">
	/**
	 * Modal de criacao/edicao de evento do calendario. CONTROLADO por callbacks.
	 *
	 * O componente NAO chama API: recebe `event` (null = criar) e emite
	 * `onSave(input)` / `onDelete(id)` / `onGenerateMeet(id)`. A pagina chama os
	 * endpoints (rotas legadas via `Accept: application/json`, ver
	 * lib/api/calendars.ts) e RE-BUSCA o hub. Salvar e EXPLICITO (sem autosave).
	 *
	 * Acessibilidade: dialogo modal (`role="dialog"`, `aria-modal`, `tabindex=-1`),
	 * titulo rotulando o dialogo, foco inicial no campo titulo, Escape fecha, fundo
	 * clicavel fecha. O servidor e autoritativo; a validacao do cliente e minima
	 * (titulo nao vazio; ends_at >= starts_at).
	 *
	 * Se o evento estiver com `sync_status === "error"` e `sync_error`, mostra um
	 * aviso DEGRADADO que NAO bloqueia o formulario.
	 */
	import { tick } from 'svelte';
	import type { CalendarEvent, CalendarEventInput } from '$lib/types/calendar';

	interface Props {
		/** Dialogo aberto? (controlado pela pagina). */
		open: boolean;
		/** Evento a editar; `null` cria um novo. */
		event: CalendarEvent | null;
		/** Operacao em andamento (salvar/excluir/gerar-meet). */
		busy?: boolean;
		/** Erro da operacao (server-autoritativo). */
		error?: string | null;
		/** Salva o evento; a pagina chama o endpoint. */
		onSave: (input: CalendarEventInput) => void;
		/** Exclui o evento (apenas no modo editar). */
		onDelete?: (id: number) => void;
		/** Gera o link do Google Meet (apenas no modo editar, sem meet_link). */
		onGenerateMeet?: (id: number) => void;
		/** Fecha o modal sem salvar. */
		onClose: () => void;
	}

	let {
		open,
		event,
		busy = false,
		error = null,
		onSave,
		onDelete,
		onGenerateMeet,
		onClose
	}: Props = $props();

	let title = $state('');
	let description = $state('');
	let location = $state('');
	let startsAt = $state('');
	let endsAt = $state('');
	let allDay = $state(false);
	let createConference = $state(false);
	let clientError = $state<string | null>(null);
	let titleEl = $state<HTMLInputElement | null>(null);

	const isEdit = $derived(event !== null);
	const meetLink = $derived(event?.meet_link ?? '');
	const showSyncWarning = $derived(
		event?.sync_status === 'error' && !!event?.sync_error
	);
	const canGenerateMeet = $derived(
		isEdit && !meetLink && typeof onGenerateMeet === 'function'
	);

	// Ao abrir, preenche o formulario a partir do evento (ou reseta) e foca o titulo.
	$effect(() => {
		if (!open) return;
		title = event?.title ?? '';
		description = event?.description ?? '';
		location = event?.location ?? '';
		startsAt = event?.starts_at ?? '';
		endsAt = event?.ends_at ?? '';
		allDay = event?.is_all_day ?? false;
		createConference = false;
		clientError = null;
		void tick().then(() => titleEl?.focus());
	});

	function validate(): string | null {
		if (title.trim() === '') return 'Informe um titulo para o evento.';
		if (startsAt !== '' && endsAt !== '' && endsAt < startsAt) {
			return 'O termino deve ser igual ou posterior ao inicio.';
		}
		return null;
	}

	function save(): void {
		if (busy) return;
		const problem = validate();
		if (problem) {
			clientError = problem;
			return;
		}
		clientError = null;
		onSave({
			title: title.trim(),
			description,
			location,
			starts_at: startsAt,
			ends_at: endsAt,
			is_all_day: allDay,
			create_conference: !isEdit && createConference
		});
	}

	function remove(): void {
		if (busy || !event || !onDelete) return;
		if (!confirm('Excluir este evento? Esta acao nao pode ser desfeita.')) return;
		onDelete(event.id);
	}

	function generateMeet(): void {
		if (busy || !event || !onGenerateMeet) return;
		onGenerateMeet(event.id);
	}

	function onKeydown(keyEvent: KeyboardEvent): void {
		if (keyEvent.key === 'Escape') {
			keyEvent.preventDefault();
			onClose();
		}
	}
</script>

{#if open}
	<!-- Fundo: clicar fora fecha. -->
	<div
		class="fixed inset-0 z-modal flex items-center justify-center bg-black/50 p-4"
		role="presentation"
		onclick={onClose}
		onkeydown={onKeydown}
	>
		<!-- Dialogo: para o clique de borbulhar para o fundo. -->
		<div
			role="dialog"
			aria-modal="true"
			aria-labelledby="calendar-event-title"
			class="flex max-h-full w-full max-w-lg flex-col gap-4 overflow-y-auto rounded-lg border border-border-subtle bg-surface p-5 shadow-lg"
			onclick={(e) => e.stopPropagation()}
			onkeydown={onKeydown}
			tabindex="-1"
		>
			<header class="flex items-center justify-between gap-3">
				<h2
					id="calendar-event-title"
					class="font-heading text-lg font-semibold text-text-primary"
				>
					{isEdit ? 'Editar evento' : 'Novo evento'}
				</h2>
				<button
					type="button"
					onclick={onClose}
					aria-label="Fechar"
					class="rounded-md border border-border-subtle bg-surface px-2 py-1 text-sm text-text-secondary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					✕
				</button>
			</header>

			{#if showSyncWarning}
				<!-- Aviso degradado: nao bloqueia a edicao. -->
				<p
					role="status"
					aria-live="polite"
					class="rounded-md border border-warning bg-surface-muted px-3 py-2 text-sm text-warning"
				>
					Falha de sincronizacao com o Google: {event?.sync_error}
				</p>
			{/if}

			<div class="flex flex-col gap-1">
				<label for="event-title" class="text-sm font-medium text-text-primary">
					Titulo
				</label>
				<input
					bind:this={titleEl}
					bind:value={title}
					id="event-title"
					type="text"
					required
					disabled={busy}
					class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
				/>
			</div>

			<div class="flex flex-col gap-1">
				<label for="event-description" class="text-sm font-medium text-text-primary">
					Descricao
				</label>
				<textarea
					bind:value={description}
					id="event-description"
					rows="3"
					disabled={busy}
					class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
				></textarea>
			</div>

			<div class="flex flex-col gap-1">
				<label for="event-location" class="text-sm font-medium text-text-primary">
					Local
				</label>
				<input
					bind:value={location}
					id="event-location"
					type="text"
					disabled={busy}
					class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
				/>
			</div>

			<div class="flex flex-wrap gap-3">
				<div class="flex min-w-44 flex-1 flex-col gap-1">
					<label for="event-starts-at" class="text-sm font-medium text-text-primary">
						Inicio
					</label>
					<input
						bind:value={startsAt}
						id="event-starts-at"
						type="datetime-local"
						disabled={busy}
						class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
					/>
				</div>
				<div class="flex min-w-44 flex-1 flex-col gap-1">
					<label for="event-ends-at" class="text-sm font-medium text-text-primary">
						Termino
					</label>
					<input
						bind:value={endsAt}
						id="event-ends-at"
						type="datetime-local"
						disabled={busy}
						class="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
					/>
				</div>
			</div>

			<label class="flex items-center gap-2 text-sm text-text-primary">
				<input
					bind:checked={allDay}
					type="checkbox"
					disabled={busy}
					class="rounded border-border-subtle text-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
				/>
				Dia inteiro
			</label>

			{#if !isEdit}
				<label class="flex items-center gap-2 text-sm text-text-primary">
					<input
						bind:checked={createConference}
						type="checkbox"
						disabled={busy}
						class="rounded border-border-subtle text-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-60"
					/>
					Criar Google Meet
				</label>
			{/if}

			{#if meetLink}
				<p class="text-sm text-text-secondary">
					Google Meet:
					<a
						href={meetLink}
						target="_blank"
						rel="noopener noreferrer"
						class="text-primary-700 underline hover:text-primary-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						{meetLink}
					</a>
				</p>
			{/if}

			{#if clientError}
				<p role="alert" class="text-sm text-danger">{clientError}</p>
			{:else if error}
				<p role="alert" class="text-sm text-danger">{error}</p>
			{/if}

			<footer class="flex flex-wrap items-center justify-end gap-2">
				{#if isEdit && onDelete}
					<button
						type="button"
						onclick={remove}
						disabled={busy}
						class="mr-auto rounded-md border border-danger bg-surface px-4 py-2 text-sm font-medium text-danger transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
					>
						Excluir
					</button>
				{/if}
				{#if canGenerateMeet}
					<button
						type="button"
						onclick={generateMeet}
						disabled={busy}
						class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						Gerar Meet
					</button>
				{/if}
				<button
					type="button"
					onclick={onClose}
					disabled={busy}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Cancelar
				</button>
				<button
					type="button"
					onclick={save}
					disabled={busy}
					class="rounded-md border border-primary-500 bg-primary-100 px-4 py-2 text-sm font-medium text-primary-700 transition-colors duration-fast hover:bg-primary-500 hover:text-white disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					{busy ? 'Salvando…' : 'Salvar'}
				</button>
			</footer>
		</div>
	</div>
{/if}
