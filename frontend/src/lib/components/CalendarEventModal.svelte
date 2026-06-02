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
	 * titulo rotulando o dialogo, Escape fecha, fundo clicavel fecha. O foco fica
	 * preso no dialogo via `use:focusTrap` (#19), que foca o primeiro elemento
	 * focavel ao abrir e restaura o foco anterior ao fechar. O servidor e
	 * autoritativo; a validacao do cliente e minima (titulo nao vazio;
	 * ends_at >= starts_at).
	 *
	 * Se o evento estiver com `sync_status === "error"` e `sync_error`, mostra um
	 * aviso DEGRADADO que NAO bloqueia o formulario.
	 */
	import type { CalendarEvent, CalendarEventInput } from '$lib/types/calendar';
	import { focusTrap } from '$lib/actions/focusTrap';

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

	const isEdit = $derived(event !== null);
	const meetLink = $derived(event?.meet_link ?? '');
	const showSyncWarning = $derived(
		event?.sync_status === 'error' && !!event?.sync_error
	);
	const canGenerateMeet = $derived(
		isEdit && !meetLink && typeof onGenerateMeet === 'function'
	);

	// Ao abrir, preenche o formulario a partir do evento (ou reseta). O foco
	// inicial fica a cargo de `use:focusTrap` (#19).
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
	<!-- Fundo: clicar fora fecha. Overlay rgba(0,0,0,0.3) + fade 0.16s do original. -->
	<div
		class="cal-modal-overlay fixed inset-0 z-modal flex items-center justify-center bg-black/30 p-4"
		role="presentation"
		onclick={onClose}
		onkeydown={onKeydown}
	>
		<!-- Dialogo: para o clique de borbulhar para o fundo. Slide/scale-in do original. -->
		<div
			role="dialog"
			aria-modal="true"
			aria-labelledby="calendar-event-title"
			class="cal-modal flex max-h-[calc(100vh-2rem)] w-full max-w-[31rem] flex-col overflow-hidden rounded-[0.85rem] border border-border-subtle bg-surface shadow-lg"
			onclick={(e) => e.stopPropagation()}
			onkeydown={onKeydown}
			tabindex="-1"
			use:focusTrap
		>
			<!-- Header com borda inferior (cal-modal-header). -->
			<header
				class="flex items-center gap-3 border-b border-border-subtle px-[1.1rem] pb-3 pt-4"
			>
				<h2
					id="calendar-event-title"
					class="flex-1 font-heading text-base font-semibold text-text-primary"
				>
					{isEdit ? 'Editar evento' : 'Novo evento'}
				</h2>
				<button
					type="button"
					onclick={onClose}
					aria-label="Fechar"
					class="flex h-[1.7rem] w-[1.7rem] items-center justify-center rounded-full text-text-muted transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<svg
						width="16"
						height="16"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2.5"
						stroke-linecap="round"
						aria-hidden="true"
					>
						<line x1="18" y1="6" x2="6" y2="18" />
						<line x1="6" y1="6" x2="18" y2="18" />
					</svg>
				</button>
			</header>

			<!-- Corpo rolavel (cal-modal-body): gap 0.8rem. -->
			<div class="flex flex-col gap-[0.8rem] overflow-y-auto px-[1.1rem] py-4">
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

				<!-- Titulo: input com borda inferior estilo Google (cal-field-title). -->
				<div class="flex flex-col gap-1">
					<label for="event-title" class="sr-only">Titulo</label>
					<input
						bind:value={title}
						id="event-title"
						type="text"
						placeholder="Titulo do evento"
						required
						maxlength="200"
						autocomplete="off"
						disabled={busy}
						class="w-full border-0 border-b-2 border-border-subtle bg-transparent px-0 py-[0.3rem] text-lg font-medium text-text-primary outline-none transition-colors duration-fast placeholder:font-normal placeholder:text-text-muted focus:border-primary-500 disabled:opacity-60"
					/>
				</div>

				<!-- Inicio/Termino: linha com icone de calendario (cal-field-row). -->
				<div class="flex items-start gap-[0.6rem]">
					<div class="mt-[0.52rem] flex w-[1.2rem] flex-shrink-0 items-center justify-center text-text-muted">
						<svg
							width="15"
							height="15"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							stroke-linecap="round"
							stroke-linejoin="round"
							aria-hidden="true"
						>
							<rect x="3" y="4" width="18" height="18" rx="2" />
							<line x1="16" y1="2" x2="16" y2="6" />
							<line x1="8" y1="2" x2="8" y2="6" />
							<line x1="3" y1="10" x2="21" y2="10" />
						</svg>
					</div>
					<div class="min-w-0 flex-1">
						<!-- Dia inteiro: switch estilo Google (cal-switch). -->
						<label class="mb-[0.55rem] inline-flex cursor-pointer items-center gap-[0.45rem]">
							<span class="cal-switch relative h-[1.2rem] w-[2.1rem] flex-shrink-0">
								<input
									bind:checked={allDay}
									type="checkbox"
									disabled={busy}
									class="peer absolute h-0 w-0 opacity-0"
								/>
								<span
									class="cal-switch-track absolute inset-0 cursor-pointer rounded-full bg-border-subtle transition-colors duration-fast peer-checked:bg-primary-600 peer-disabled:opacity-60"
								></span>
							</span>
							<span class="select-none text-sm text-text-secondary">Dia inteiro</span>
						</label>

						<div class="flex flex-wrap gap-3">
							<div class="flex min-w-44 flex-1 flex-col gap-[0.2rem]">
								<span class="text-xs text-text-muted">Inicio</span>
								<label for="event-starts-at" class="sr-only">Inicio</label>
								<input
									bind:value={startsAt}
									id="event-starts-at"
									type="datetime-local"
									disabled={busy}
									class="w-full rounded-[0.38rem] border border-border-subtle bg-surface px-[0.55rem] py-[0.38rem] text-sm text-text-primary outline-none transition-[border-color,box-shadow] duration-fast focus:border-primary-500 focus:shadow-[0_0_0_3px_rgba(0,90,146,0.09)] disabled:opacity-60"
								/>
							</div>
							<div class="flex min-w-44 flex-1 flex-col gap-[0.2rem]">
								<span class="text-xs text-text-muted">Fim</span>
								<label for="event-ends-at" class="sr-only">Termino</label>
								<input
									bind:value={endsAt}
									id="event-ends-at"
									type="datetime-local"
									disabled={busy}
									class="w-full rounded-[0.38rem] border border-border-subtle bg-surface px-[0.55rem] py-[0.38rem] text-sm text-text-primary outline-none transition-[border-color,box-shadow] duration-fast focus:border-primary-500 focus:shadow-[0_0_0_3px_rgba(0,90,146,0.09)] disabled:opacity-60"
								/>
							</div>
						</div>
					</div>
				</div>

				{#if !isEdit}
					<!-- Google Meet: linha com icone de video + switch (cal-meet-row). -->
					<div class="flex items-start gap-[0.6rem]">
						<div class="mt-[0.52rem] flex w-[1.2rem] flex-shrink-0 items-center justify-center text-text-muted">
							<svg
								width="15"
								height="15"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
								aria-hidden="true"
							>
								<path d="M23 7l-7 5 7 5V7z" />
								<rect x="1" y="5" width="15" height="14" rx="2" />
							</svg>
						</div>
						<div class="min-w-0 flex-1">
							<label
								class="flex cursor-pointer items-center gap-[0.55rem] rounded-[0.48rem] border border-border-subtle px-[0.6rem] py-2 transition-colors duration-fast hover:bg-surface-muted"
							>
								<span
									class="flex h-[1.4rem] w-[1.4rem] flex-shrink-0 items-center justify-center rounded-[0.28rem] bg-[#00832d]"
								>
									<svg width="14" height="14" viewBox="0 0 24 24" fill="white" aria-hidden="true">
										<path
											d="M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4v-11l-4 4z"
										/>
									</svg>
								</span>
								<span class="flex flex-1 flex-col gap-[0.05rem]">
									<span class="text-sm text-text-primary">Google Meet</span>
									<span class="text-xs text-text-muted">Adicionar videochamada</span>
								</span>
								<span class="cal-switch relative h-[1.2rem] w-[2.1rem] flex-shrink-0">
									<input
										bind:checked={createConference}
										type="checkbox"
										disabled={busy}
										class="peer absolute h-0 w-0 opacity-0"
									/>
									<span
										class="cal-switch-track absolute inset-0 cursor-pointer rounded-full bg-border-subtle transition-colors duration-fast peer-checked:bg-primary-600 peer-disabled:opacity-60"
									></span>
								</span>
							</label>
						</div>
					</div>
				{/if}

				{#if meetLink}
					<!-- Meet existente: bloco com icone verde + link (cal-meet-existing). -->
					<div class="flex items-start gap-[0.6rem]">
						<div class="mt-[0.52rem] flex w-[1.2rem] flex-shrink-0 items-center justify-center text-text-muted">
							<svg
								width="15"
								height="15"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
								aria-hidden="true"
							>
								<path d="M23 7l-7 5 7 5V7z" />
								<rect x="1" y="5" width="15" height="14" rx="2" />
							</svg>
						</div>
						<div class="min-w-0 flex-1 overflow-hidden rounded-[0.48rem] border border-border-subtle">
							<a
								href={meetLink}
								target="_blank"
								rel="noopener noreferrer"
								class="flex items-center gap-[0.55rem] bg-surface-muted px-[0.6rem] py-2 transition-[filter] duration-fast hover:brightness-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
							>
								<span
									class="flex h-[1.4rem] w-[1.4rem] flex-shrink-0 items-center justify-center rounded-[0.28rem] bg-[#00832d]"
								>
									<svg width="14" height="14" viewBox="0 0 24 24" fill="white" aria-hidden="true">
										<path
											d="M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4v-11l-4 4z"
										/>
									</svg>
								</span>
								<span class="flex min-w-0 flex-col">
									<span class="text-sm text-text-primary">Google Meet</span>
									<span class="block truncate text-xs text-text-muted">{meetLink}</span>
								</span>
							</a>
						</div>
					</div>
				{/if}

				<!-- Local: linha com icone de pin (cal-field-row). -->
				<div class="flex items-start gap-[0.6rem]">
					<div class="mt-[0.52rem] flex w-[1.2rem] flex-shrink-0 items-center justify-center text-text-muted">
						<svg
							width="15"
							height="15"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							stroke-linecap="round"
							stroke-linejoin="round"
							aria-hidden="true"
						>
							<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
							<circle cx="12" cy="10" r="3" />
						</svg>
					</div>
					<div class="min-w-0 flex-1">
						<label for="event-location" class="sr-only">Local</label>
						<input
							bind:value={location}
							id="event-location"
							type="text"
							placeholder="Adicionar local"
							maxlength="255"
							autocomplete="off"
							disabled={busy}
							class="w-full rounded-[0.38rem] border border-border-subtle bg-surface px-[0.55rem] py-[0.38rem] text-sm text-text-primary outline-none transition-[border-color,box-shadow] duration-fast placeholder:text-text-muted focus:border-primary-500 focus:shadow-[0_0_0_3px_rgba(0,90,146,0.09)] disabled:opacity-60"
						/>
					</div>
				</div>

				<!-- Descricao: linha com icone de linhas (cal-field-row). -->
				<div class="flex items-start gap-[0.6rem]">
					<div class="mt-[0.52rem] flex w-[1.2rem] flex-shrink-0 items-center justify-center text-text-muted">
						<svg
							width="15"
							height="15"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							stroke-linecap="round"
							stroke-linejoin="round"
							aria-hidden="true"
						>
							<line x1="17" y1="10" x2="3" y2="10" />
							<line x1="21" y1="6" x2="3" y2="6" />
							<line x1="21" y1="14" x2="3" y2="14" />
							<line x1="17" y1="18" x2="3" y2="18" />
						</svg>
					</div>
					<div class="min-w-0 flex-1">
						<label for="event-description" class="sr-only">Descricao</label>
						<textarea
							bind:value={description}
							id="event-description"
							rows="3"
							placeholder="Adicionar descricao"
							disabled={busy}
							class="min-h-[3.5rem] w-full resize-y rounded-[0.38rem] border border-border-subtle bg-surface px-[0.55rem] py-[0.4rem] text-sm text-text-primary outline-none transition-[border-color,box-shadow] duration-fast placeholder:text-text-muted focus:border-primary-500 focus:shadow-[0_0_0_3px_rgba(0,90,146,0.09)] disabled:opacity-60"
						></textarea>
					</div>
				</div>

				{#if clientError}
					<p role="alert" class="text-sm text-danger">{clientError}</p>
				{:else if error}
					<p role="alert" class="text-sm text-danger">{error}</p>
				{/if}
			</div>

			<!-- Rodape com borda superior (cal-modal-footer). -->
			<footer
				class="flex items-center justify-between gap-2 border-t border-border-subtle px-[1.1rem] pb-[0.9rem] pt-[0.7rem]"
			>
				<div>
					{#if isEdit && onDelete}
						<button
							type="button"
							onclick={remove}
							disabled={busy}
							class="inline-flex items-center gap-[0.3rem] rounded-[0.38rem] px-[0.65rem] py-[0.38rem] text-sm text-danger transition-colors duration-fast hover:bg-danger/10 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
						>
							<svg
								width="13"
								height="13"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
								aria-hidden="true"
							>
								<polyline points="3 6 5 6 21 6" />
								<path d="M19 6l-1 14H6L5 6" />
								<path d="M10 11v6m4-6v6" />
								<path d="M9 6V4h6v2" />
							</svg>
							Excluir
						</button>
					{/if}
				</div>
				<div class="flex gap-[0.45rem]">
					{#if canGenerateMeet}
						<button
							type="button"
							onclick={generateMeet}
							disabled={busy}
							class="inline-flex items-center gap-[0.3rem] rounded-[0.38rem] border border-border-subtle bg-surface px-[0.85rem] py-[0.4rem] text-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							Gerar Meet
						</button>
					{/if}
					<button
						type="button"
						onclick={onClose}
						disabled={busy}
						class="rounded-[0.38rem] border border-border-subtle bg-surface px-[0.85rem] py-[0.4rem] text-sm text-text-secondary transition-colors duration-fast hover:bg-surface-muted disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						Cancelar
					</button>
					<button
						type="button"
						onclick={save}
						disabled={busy}
						class="rounded-[0.38rem] bg-primary-600 px-4 py-[0.4rem] text-sm font-medium text-white transition-colors duration-fast hover:bg-primary-700 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						{busy ? 'Salvando…' : 'Salvar'}
					</button>
				</div>
			</footer>
		</div>
	</div>
{/if}

<style>
	/* Animacao de entrada do modal — valores 1:1 do original
	   (calendar-event-modal.css): overlay fade 0.16s + dialogo slide/scale 0.16s. */
	.cal-modal-overlay {
		animation: cal-overlay-in 0.16s ease both;
	}
	.cal-modal {
		animation: cal-modal-in 0.16s ease both;
	}
	@keyframes cal-overlay-in {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}
	@keyframes cal-modal-in {
		from {
			transform: translateY(10px) scale(0.99);
		}
		to {
			transform: translateY(0) scale(1);
		}
	}

	/* Knob do switch (cal-switch-track::before) — desliza 0.16s ao marcar. */
	.cal-switch-track::before {
		content: '';
		position: absolute;
		width: 0.85rem;
		height: 0.85rem;
		border-radius: 50%;
		background: #fff;
		left: 0.175rem;
		top: 50%;
		transform: translateY(-50%);
		transition: left 0.16s;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.22);
	}
	.cal-switch input:checked + .cal-switch-track::before {
		left: calc(100% - 0.175rem - 0.85rem);
	}

	@media (prefers-reduced-motion: reduce) {
		.cal-modal-overlay,
		.cal-modal {
			animation: none;
		}
		.cal-switch-track::before {
			transition: none;
		}
	}
</style>
