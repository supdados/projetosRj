<script lang="ts">
	/**
	 * Tela "Detalhe de Projeto" (FASE 5a). URL: /spa/projetos/<id>.
	 *
	 * Carrega `GET /api/projetos/<id>/detalhe` (modulo `$lib/api/projectDetail`) e
	 * compoe ProjectHeader (sticky/compacto + edicao inline de titulo/status/
	 * prioridade), edicao inline dos demais campos do projeto, StageList (CRUD de
	 * etapas + reordenacao por DnD + comentarios) e ImportModelModal.
	 *
	 * ORQUESTRACAO: esta pagina e a UNICA que chama a API; os componentes sao
	 * controlados por callback. A CASCATA DE DATAS E SERVER-SIDE — ao reordenar
	 * etapas ou editar uma data/campo de etapa, chamamos o endpoint e RE-BUSCAMOS o
	 * estado do servidor (a cascata pode mudar as etapas seguintes). O front NUNCA
	 * recalcula datas nem dias uteis.
	 *
	 * Restricoes da fase:
	 *   - Tarefas das etapas sao SOMENTE LEITURA (contagem + lista simples sob
	 *     demanda); sem mutacao (Fase 5b cobre drawer/quick-add).
	 *   - Reunioes Google ficam read-only (Fase 6); StageRow ja as trata.
	 *
	 * Acessivel: heading de nivel 1 (no ProjectHeader), estados loading/erro/vazio
	 * anunciados via aria-live/role=alert, retry focavel. Erros tratados:
	 *   - 404 `not_found`; 403 `forbidden`; 401 ja redireciona em `client.ts`.
	 * Links internos sao base-aware (`$app/paths`).
	 */
	import { onMount, setContext } from 'svelte';
	import { page } from '$app/stores';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import { ApiClientError } from '$lib/api/client';
	import TaskDrawer from '$lib/components/TaskDrawer.svelte';
	import { createTaskDrawerStore } from '$lib/stores/taskDrawer';
	import { flash } from '$lib/stores/flash';
	import {
		fetchProjectDetail,
		updateProjectInline,
		addEtapa,
		deleteEtapa,
		updateEtapaField,
		saveEtapaComentario,
		toggleEtapaIniciada,
		toggleEtapaDone,
		reorderEtapas,
		cascadeDates,
		importStageModel,
		fetchStageTemplates,
		concludeProject,
		createStageMeeting,
		updateStageMeeting,
		deleteStageMeeting
	} from '$lib/api/projectDetail';
	import type {
		ProjectDetailData,
		EtapaDetail,
		EtapaInlineField,
		StageTemplateOption,
		ProjectInlinePayload,
		MeetingPayload
	} from '$lib/types/projectDetail';
	import StageTaskQuickAdd from '$lib/components/StageTaskQuickAdd.svelte';
	import type { CalendarEvent, CalendarEventInput } from '$lib/types/calendar';
	import ProjectHeader from '$lib/components/ProjectHeader.svelte';
	import InlineEditField from '$lib/components/InlineEditField.svelte';
	import StageList from '$lib/components/StageList.svelte';
	import ImportModelModal from '$lib/components/ImportModelModal.svelte';
	import Card from '$lib/components/Card.svelte';
	import ConcludeCelebrationOverlay from '$lib/components/ConcludeCelebrationOverlay.svelte';
	import MeetingDisplay from '$lib/components/MeetingDisplay.svelte';
	import CalendarEventModal from '$lib/components/CalendarEventModal.svelte';
	import {
		primeConcludeAudioContext,
		playConcludeSuccessChime
	} from '$lib/celebration/concludeChime';
	import { triggerEpicConfetti } from '$lib/celebration/confettiEpic';
	import '$lib/celebration/confetti.css';

	type LoadState = 'loading' | 'ready' | 'error';
	type HeaderField = 'titulo' | 'status' | 'prioridade';

	interface FieldState {
		pending?: boolean;
		error?: string | null;
	}
	/** Estado de mutacao por etapa, repassado ao StageList. */
	interface RowState {
		fields?: Partial<Record<EtapaInlineField, FieldState>>;
		busy?: boolean;
		error?: string | null;
	}

	const projectId = $derived(Number($page.params.id));

	let loadState = $state<LoadState>('loading');
	let data = $state<ProjectDetailData | null>(null);
	let errorMessage = $state<string>('');
	let errorKind = $state<'forbidden' | 'not_found' | 'generic'>('generic');

	// Estados de edicao inline do cabecalho e dos campos do projeto.
	let projectFieldStates = $state<Record<string, FieldState>>({});

	// Estados de mutacao das etapas (por etapa) e da reordenacao.
	let rowStates = $state<Record<number, RowState>>({});
	let reordering = $state<boolean>(false);
	let reorderError = $state<string | null>(null);

	// Adicionar etapa (composer inline).
	let addingStage = $state<boolean>(false);
	let addStageError = $state<string | null>(null);

	// Quick-add de tarefas da etapa (modal).
	let quickAddEtapaId = $state<number | null>(null);

	// Menu de contexto de dias úteis numa célula de data (+7/+14/+21).
	interface DateContextMenuState {
		etapaId: number;
		field: 'data_inicio' | 'data_fim';
		x: number;
		y: number;
	}
	let dateMenu = $state<DateContextMenuState | null>(null);

	// Confirmação de cascata após mudar uma data_inicio.
	interface CascadeState {
		etapaId: number;
		daysDiff: number;
	}
	let cascadePrompt = $state<CascadeState | null>(null);
	let cascadeBusy = $state<boolean>(false);

	// Importar modelo de etapas.
	let importOpen = $state<boolean>(false);
	let templates = $state<StageTemplateOption[]>([]);
	let templatesLoading = $state<boolean>(false);
	let importSubmitting = $state<boolean>(false);
	let importError = $state<string | null>(null);

	// Offset do topnav fixo para o sticky do cabecalho (medido no mount).
	let topOffset = $state<number>(0);

	const canEdit = $derived(data?.permissions.can_edit ?? false);

	// Etapa-alvo do quick-add de tarefas (modal).
	const quickAddEtapa = $derived(
		quickAddEtapaId === null ? null : (data?.etapas.find((e) => e.id === quickAddEtapaId) ?? null)
	);

	/** Formata ISO em pt-BR (UTC) ou '' se vazio. */
	function isoToBr(iso: string | null): string {
		if (!iso) return '';
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '';
		return d.toLocaleDateString('pt-BR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			timeZone: 'UTC'
		});
	}

	/** Label de datas da etapa para o cabeçalho do quick-add (paridade legado). */
	function etapaDatasLabel(etapa: EtapaDetail): string {
		const ini = isoToBr(etapa.data_inicio);
		const fim = isoToBr(etapa.data_fim);
		if (ini && fim) return `${ini} — ${fim}`;
		if (ini) return `Início ${ini}`;
		if (fim) return `Fim ${fim}`;
		return 'Etapa sem datas definidas';
	}

	// --- Concluir projeto (aviso + som + confetes) ---------------------------
	let concludeInFlight = $state<boolean>(false);
	let celebrationActive = $state<boolean>(false);
	let celebrationTitle = $state<string>('Concluindo projeto...');
	let celebrationMessage = $state<string>('Aguarde um instante.');

	const reduceMotion = (): boolean =>
		typeof window !== 'undefined' &&
		!!window.matchMedia &&
		window.matchMedia('(prefers-reduced-motion: reduce)').matches;

	// O botão "Concluir Projeto" só aparece para quem pode editar, está habilitado
	// quando o projeto está Vigente e TODAS as etapas estão concluídas (paridade
	// com verificarEAtualizarBotaoConcluir do legado).
	const isVigente = $derived((data?.project.status ?? '') === 'Vigente');
	const canConclude = $derived(
		canEdit && isVigente && (data?.derived.todas_etapas_concluidas ?? false)
	);

	function wait(ms: number): Promise<void> {
		return new Promise((resolve) => window.setTimeout(resolve, ms));
	}

	/**
	 * Conclui o projeto reproduzindo FIELMENTE a UX do legado: overlay
	 * "Concluindo projeto..." + spinner, depois (em sucesso) overlay "Objetivo
	 * concluído" + chime (Web Audio) + confete épico (canvas), aguarda o delay e
	 * navega via router. Em erro: esconde overlay + toast (danger/warning).
	 */
	async function onConcludeProject(): Promise<void> {
		if (!data || concludeInFlight || !canConclude) return;
		concludeInFlight = true;
		celebrationTitle = 'Concluindo projeto...';
		celebrationMessage = 'Aguarde um instante.';
		celebrationActive = true;
		try {
			const result = await concludeProject(projectId);
			celebrationTitle = 'Objetivo concluído';
			celebrationMessage = result.message;
			playConcludeSuccessChime();
			triggerEpicConfetti();
			await wait(reduceMotion() ? 450 : 2400);
			await goto(`${base}${result.redirect_to}`);
			// Recarrega o detalhe (agora Finalizado) caso o router mantenha a tela.
			celebrationActive = false;
			await refresh();
		} catch (err) {
			celebrationActive = false;
			if (isUnauthenticated(err)) return;
			const category =
				err instanceof ApiClientError && err.code === 'forbidden' ? 'danger' : 'warning';
			flash.show(messageOf(err, 'Não foi possível concluir o projeto.'), category);
		} finally {
			concludeInFlight = false;
		}
	}

	// --- Reuniões Google (criar/editar/excluir) ------------------------------
	let meetingModalOpen = $state<boolean>(false);
	let meetingModalBusy = $state<boolean>(false);
	let meetingModalError = $state<string | null>(null);
	// `null` => criar (reunião nova do projeto); número => editar a etapa-reunião.
	let editingMeetingEtapaId = $state<number | null>(null);
	// Estado de exclusão por etapa-reunião (spinner no MeetingDisplay).
	let meetingDeleting = $state<Record<number, boolean>>({});

	/** Monta o `CalendarEvent` que pré-preenche o modal a partir da etapa. */
	function meetingEventForModal(etapaId: number | null): CalendarEvent | null {
		if (etapaId === null || !data) return null;
		const etapa = data.etapas.find((e) => e.id === etapaId);
		const m = etapa?.meeting;
		if (!m) return null;
		return {
			id: etapaId,
			title: m.title ?? '',
			description: m.description,
			location: m.location,
			starts_at: m.starts_at,
			ends_at: m.ends_at,
			starts_at_display: m.start_time_display,
			ends_at_display: m.end_time_display,
			is_all_day: m.is_all_day,
			source: 'google',
			sync_status: (m.sync_status as CalendarEvent['sync_status']) || 'pending',
			sync_error: m.sync_error || undefined,
			meet_link: m.meet_link
		};
	}

	const meetingModalEvent = $derived(meetingEventForModal(editingMeetingEtapaId));

	function openCreateMeeting(): void {
		editingMeetingEtapaId = null;
		meetingModalError = null;
		meetingModalOpen = true;
	}

	function openEditMeeting(etapaId: number): void {
		editingMeetingEtapaId = etapaId;
		meetingModalError = null;
		meetingModalOpen = true;
	}

	function closeMeetingModal(): void {
		if (meetingModalBusy) return;
		meetingModalOpen = false;
		meetingModalError = null;
	}

	/** Converte o input do CalendarEventModal para o payload da reunião. */
	function meetingPayloadOf(input: CalendarEventInput): MeetingPayload {
		return {
			title: input.title,
			description: input.description,
			location: input.location,
			starts_at: input.starts_at,
			ends_at: input.ends_at,
			is_all_day: input.is_all_day,
			create_conference: input.create_conference
		};
	}

	/** Salva (cria/edita) a reunião; em sucesso re-busca o detalhe + toasts. */
	async function onSaveMeeting(input: CalendarEventInput): Promise<void> {
		if (meetingModalBusy) return;
		meetingModalBusy = true;
		meetingModalError = null;
		const payload = meetingPayloadOf(input);
		try {
			const result =
				editingMeetingEtapaId === null
					? await createStageMeeting(projectId, payload)
					: await updateStageMeeting(editingMeetingEtapaId, payload);
			meetingModalOpen = false;
			flash.success(result.message);
			if (result.warning) flash.warning(result.warning);
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) return;
			meetingModalError = messageOf(err, 'Não foi possível salvar a reunião.');
		} finally {
			meetingModalBusy = false;
		}
	}

	/** Exclui a reunião (confirm nativo); em sucesso re-busca + toast. */
	async function onDeleteMeeting(etapaId: number): Promise<void> {
		if (typeof window !== 'undefined' && !window.confirm('Tem certeza que deseja excluir esta reunião?'))
			return;
		meetingDeleting = { ...meetingDeleting, [etapaId]: true };
		try {
			const result = await deleteStageMeeting(etapaId);
			flash.success(result.message);
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) return;
			const category =
				err instanceof ApiClientError && err.code === 'forbidden' ? 'danger' : 'warning';
			flash.show(messageOf(err, 'Não foi possível excluir a reunião.'), category);
		} finally {
			meetingDeleting = { ...meetingDeleting, [etapaId]: false };
		}
	}

	/** Mensagem amigavel para um erro de API/desconhecido. */
	function messageOf(err: unknown, fallback: string): string {
		if (err instanceof ApiClientError) return err.message;
		if (err instanceof Error) return err.message;
		return fallback;
	}

	/** Trata 401 (no-op: client.ts ja redirecionou) e devolve true se foi 401. */
	function isUnauthenticated(err: unknown): boolean {
		return err instanceof ApiClientError && err.code === 'unauthenticated';
	}

	async function load(): Promise<void> {
		loadState = 'loading';
		errorMessage = '';
		errorKind = 'generic';
		try {
			data = await fetchProjectDetail(projectId);
			loadState = 'ready';
		} catch (err) {
			if (isUnauthenticated(err)) return;
			if (err instanceof ApiClientError) {
				if (err.code === 'not_found') errorKind = 'not_found';
				else if (err.code === 'forbidden') errorKind = 'forbidden';
			}
			errorMessage = messageOf(err, 'Falha ao carregar o detalhe do projeto.');
			loadState = 'error';
		}
	}

	/** Re-busca o detalhe completo (apos mutacoes que disparam cascata). */
	async function refresh(): Promise<void> {
		try {
			data = await fetchProjectDetail(projectId);
		} catch (err) {
			if (isUnauthenticated(err)) return;
			errorMessage = messageOf(err, 'Falha ao recarregar o projeto.');
		}
	}

	// --- Drawer de tarefa (Fase 5b-2, modo drawer-only) ----------------------
	// Sem board aqui: ao fechar o drawer após mutações, recarrega o detalhe para
	// refletir contagem/estado das tarefas de etapa (sem re-fetch por keystroke).
	const drawer = createTaskDrawerStore();
	setContext('openTaskDrawer', (id: number) => void drawer.open(id, { mode: 'etapa' }));

	let drawerWasOpen = false;
	$effect(() => {
		const open = $drawer.status !== 'closed';
		if (drawerWasOpen && !open) void refresh();
		drawerWasOpen = open;
	});

	// --- Edicao inline de campos do projeto (cabecalho + demais) -------------

	function setProjectFieldState(field: string, next: FieldState): void {
		projectFieldStates = { ...projectFieldStates, [field]: next };
	}

	/**
	 * Salva um campo do projeto inline (chama /inline) e atualiza o projeto com a
	 * resposta. Usado tanto pelo cabecalho (titulo/status/prioridade) quanto pelos
	 * campos da secao "Detalhes".
	 */
	async function saveProjectField(field: string, value: string): Promise<void> {
		if (!data) return;
		setProjectFieldState(field, { pending: true, error: null });
		const payload: ProjectInlinePayload = { [field]: value === '' ? null : value };
		try {
			const result = await updateProjectInline(projectId, payload);
			data = { ...data, project: result.project };
			setProjectFieldState(field, { pending: false, error: null });
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setProjectFieldState(field, {
				pending: false,
				error: messageOf(err, 'Falha ao salvar o campo.')
			});
		}
	}

	function onHeaderEditField(field: HeaderField, value: string): void {
		void saveProjectField(field, value);
	}

	// --- Etapas: estados auxiliares ------------------------------------------

	function getRowState(etapaId: number): RowState {
		return rowStates[etapaId] ?? {};
	}

	function setRowState(etapaId: number, next: RowState): void {
		rowStates = { ...rowStates, [etapaId]: next };
	}

	function setRowBusy(etapaId: number, busy: boolean, error: string | null = null): void {
		setRowState(etapaId, { ...getRowState(etapaId), busy, error });
	}

	function setRowFieldState(etapaId: number, field: EtapaInlineField, next: FieldState): void {
		const current = getRowState(etapaId);
		setRowState(etapaId, {
			...current,
			fields: { ...current.fields, [field]: next }
		});
	}

	/** Aplica uma etapa atualizada (vinda de um endpoint que devolve 1 etapa). */
	function replaceEtapa(updated: EtapaDetail): void {
		if (!data) return;
		data = {
			...data,
			etapas: data.etapas.map((e) => (e.id === updated.id ? updated : e))
		};
	}

	// --- Etapas: edicao inline de campo (cascata server-side) ----------------

	/**
	 * Edita um campo inline da etapa (descricao/data_inicio/data_fim/responsavel).
	 * Ao mudar uma DATA, o backend pode propagar a cascata para etapas seguintes;
	 * por isso RE-BUSCAMOS o estado completo apos o sucesso. O front nao recalcula.
	 */
	async function onUpdateField(
		etapaId: number,
		field: EtapaInlineField,
		value: string
	): Promise<void> {
		setRowFieldState(etapaId, field, { pending: true, error: null });
		try {
			const result = await updateEtapaField(etapaId, field, value === '' ? null : value);
			replaceEtapa(result.etapa);
			setRowFieldState(etapaId, field, { pending: false, error: null });
			// Datas disparam cascata server-side nas etapas seguintes -> re-busca.
			if (field === 'data_inicio' || field === 'data_fim') {
				await refresh();
				// Ao mudar data_inicio com deslocamento de dias, oferece a cascata
				// (paridade com showCascadeConfirmModal de 07-stage-dnd.js).
				const diff = result.field_update?.daysDiff ?? 0;
				if (field === 'data_inicio' && diff !== 0) {
					cascadePrompt = { etapaId, daysDiff: diff };
				}
			}
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setRowFieldState(etapaId, field, {
				pending: false,
				error: messageOf(err, 'Falha ao salvar o campo da etapa.')
			});
		}
	}

	/**
	 * Ciclo de status unico (paridade com .etapa-status-cycle de 07-stage-dnd.js):
	 *   - idle/done -> toggle-iniciada (ao desmarcar iniciada, o backend tambem
	 *     limpa a conclusao, zerando o status);
	 *   - started   -> toggle (marca conclusao).
	 * Re-busca apos o sucesso (derivados do projeto e botao concluir).
	 */
	async function onCycleStatus(etapaId: number): Promise<void> {
		const etapa = data?.etapas.find((e) => e.id === etapaId);
		if (!etapa) return;
		const state = etapa.done ? 'done' : etapa.iniciada ? 'started' : 'idle';
		setRowBusy(etapaId, true);
		try {
			const result =
				state === 'started' ? await toggleEtapaDone(etapaId) : await toggleEtapaIniciada(etapaId);
			replaceEtapa(result.etapa);
			setRowBusy(etapaId, false);
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setRowBusy(etapaId, false, messageOf(err, 'Falha ao alternar o status da etapa.'));
		}
	}

	async function onSaveComentario(etapaId: number, comentario: string): Promise<void> {
		setRowBusy(etapaId, true);
		try {
			const result = await saveEtapaComentario(etapaId, comentario);
			replaceEtapa(result.etapa);
			setRowBusy(etapaId, false);
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setRowBusy(etapaId, false, messageOf(err, 'Falha ao salvar o comentario.'));
		}
	}

	async function onDeleteEtapa(etapaId: number): Promise<void> {
		if (typeof window !== 'undefined' && !window.confirm('Excluir esta etapa?')) return;
		setRowBusy(etapaId, true);
		try {
			await deleteEtapa(etapaId);
			// Exclusao reordena/recalcula derivados no backend -> re-busca.
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setRowBusy(etapaId, false, messageOf(err, 'Falha ao excluir a etapa.'));
		}
	}

	// --- Reordenacao (cascata server-side) -----------------------------------

	/**
	 * Persiste a nova ordem das etapas. O backend pode recalcular datas em cascata
	 * (dias uteis); por isso RE-BUSCAMOS o estado completo apos o sucesso.
	 */
	async function onReorder(orderedIds: number[]): Promise<void> {
		reordering = true;
		reorderError = null;
		try {
			await reorderEtapas(projectId, orderedIds);
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) {
				reordering = false;
				return;
			}
			reorderError = messageOf(err, 'Falha ao reordenar as etapas.');
		} finally {
			reordering = false;
		}
	}

	// --- Quick-add de tarefas da etapa (modal) -------------------------------

	function onOpenTasks(etapaId: number): void {
		quickAddEtapaId = etapaId;
	}
	function closeQuickAdd(): void {
		quickAddEtapaId = null;
		// O modal mutou tarefas -> re-busca para atualizar a pílula da etapa.
		void refresh();
	}
	/** Sincroniza a contagem da pílula a partir do quick-add (otimista). */
	function onTaskProgressChange(etapaId: number, done: number, total: number): void {
		if (!data) return;
		data = {
			...data,
			etapas: data.etapas.map((e) =>
				e.id === etapaId ? { ...e, task_count: { done, total } } : e
			)
		};
	}

	// --- Menu de contexto de dias uteis (+7/+14/+21) -------------------------

	function onDateContextMenu(
		etapaId: number,
		field: 'data_inicio' | 'data_fim',
		x: number,
		y: number
	): void {
		const etapa = data?.etapas.find((e) => e.id === etapaId);
		const base = field === 'data_inicio' ? etapa?.data_inicio : etapa?.data_fim;
		if (!base) {
			flash.warning('Defina uma data inicial antes de adicionar dias.');
			return;
		}
		dateMenu = { etapaId, field, x, y };
	}
	function closeDateMenu(): void {
		dateMenu = null;
	}

	/** Soma `businessDays` dias uteis a uma data ISO (UTC) — paridade do legado. */
	function addBusinessDays(iso: string, businessDays: number): string {
		const parts = iso.split('-').map(Number);
		if (parts.length !== 3 || parts.some(Number.isNaN)) return '';
		const d = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
		let remaining = Math.abs(Math.trunc(businessDays));
		const step = businessDays >= 0 ? 1 : -1;
		while (remaining > 0) {
			d.setUTCDate(d.getUTCDate() + step);
			const wd = d.getUTCDay();
			if (wd !== 0 && wd !== 6) remaining -= 1;
		}
		const y = d.getUTCFullYear();
		const m = String(d.getUTCMonth() + 1).padStart(2, '0');
		const day = String(d.getUTCDate()).padStart(2, '0');
		return `${y}-${m}-${day}`;
	}

	async function applyDateDays(days: number): Promise<void> {
		if (!dateMenu) return;
		const { etapaId, field } = dateMenu;
		const etapa = data?.etapas.find((e) => e.id === etapaId);
		const base = field === 'data_inicio' ? etapa?.data_inicio : etapa?.data_fim;
		closeDateMenu();
		if (!base) return;
		const newValue = addBusinessDays(base, days);
		if (!newValue) {
			flash.danger('Não foi possível calcular a nova data útil.');
			return;
		}
		await onUpdateField(etapaId, field, newValue);
		flash.success(`Data atualizada: +${days} dia(s) útil(eis)`);
	}

	// --- Cascata de datas (server-side) --------------------------------------

	async function confirmCascade(): Promise<void> {
		if (!cascadePrompt || cascadeBusy) return;
		cascadeBusy = true;
		const { etapaId, daysDiff } = cascadePrompt;
		try {
			await cascadeDates(projectId, { etapa_id: etapaId, days_diff: daysDiff });
			cascadePrompt = null;
			await refresh();
			flash.success('Datas subsequentes atualizadas.');
		} catch (err) {
			if (isUnauthenticated(err)) return;
			flash.danger(messageOf(err, 'Falha na atualização em cascata.'));
		} finally {
			cascadeBusy = false;
		}
	}
	function dismissCascade(): void {
		cascadePrompt = null;
	}

	// --- Adicionar etapa (composer inline) -----------------------------------

	interface NewStageDraft {
		descricao: string;
		data_inicio: string;
		data_fim: string;
		responsavel: string;
		iniciada: boolean;
		done: boolean;
	}

	async function onAddStage(draft: NewStageDraft): Promise<void> {
		if (!draft.descricao.trim() || addingStage) return;
		// Projeto Finalizado: adicionar etapa o reativa (Vigente). Confirma antes
		// (paridade com o reactivate-project-confirm-modal de 05-stage-composer.js).
		const willReactivate = (data?.project.status ?? '') === 'Finalizado';
		if (
			willReactivate &&
			typeof window !== 'undefined' &&
			!window.confirm(
				'Este projeto está finalizado. Ao adicionar uma nova etapa, ele voltará para o status Vigente. Deseja continuar?'
			)
		) {
			return;
		}
		addingStage = true;
		addStageError = null;
		try {
			await addEtapa(projectId, {
				descricao: draft.descricao.trim(),
				data_inicio: draft.data_inicio || null,
				data_fim: draft.data_fim || null,
				responsavel: draft.responsavel || null,
				iniciada: draft.iniciada,
				done: draft.done,
				reactivate: willReactivate || undefined
			});
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) {
				addingStage = false;
				return;
			}
			addStageError = messageOf(err, 'Falha ao adicionar a etapa.');
		} finally {
			addingStage = false;
		}
	}

	// --- Importar modelo ------------------------------------------------------

	async function openImport(): Promise<void> {
		importOpen = true;
		importError = null;
		if (templates.length > 0 || templatesLoading) return;
		templatesLoading = true;
		try {
			templates = await fetchStageTemplates();
		} catch (err) {
			if (isUnauthenticated(err)) return;
			importError = messageOf(err, 'Falha ao carregar os modelos de etapas.');
		} finally {
			templatesLoading = false;
		}
	}

	function closeImport(): void {
		if (importSubmitting) return;
		importOpen = false;
		importError = null;
	}

	async function onConfirmImport(payload: {
		template_id: number;
		start_date: string;
	}): Promise<void> {
		importSubmitting = true;
		importError = null;
		try {
			await importStageModel(projectId, payload);
			importOpen = false;
			await refresh();
		} catch (err) {
			if (isUnauthenticated(err)) {
				importSubmitting = false;
				return;
			}
			importError = messageOf(err, 'Falha ao importar o modelo de etapas.');
		} finally {
			importSubmitting = false;
		}
	}

	onMount(() => {
		// Mede o topnav fixo (sticky) para descontar no offset do cabecalho.
		const topnav = document.querySelector('header.sticky');
		if (topnav) topOffset = Math.round(topnav.getBoundingClientRect().height);
		void load();
	});
</script>

<svelte:head>
	<title>Detalhe do projeto — ProjetosRJ</title>
</svelte:head>

<section aria-labelledby="project-detail-title" class="flex flex-col gap-6">
	{#if loadState === 'loading'}
		<p role="status" aria-live="polite" class="text-text-secondary">Carregando projeto…</p>
	{:else if loadState === 'error'}
		<div
			role="alert"
			class="flex flex-col items-start gap-3 rounded-lg border border-danger bg-surface px-5 py-4"
		>
			{#if errorKind === 'not_found'}
				<p class="text-text-primary">Projeto não encontrado.</p>
				<a
					href={`${base}/projetos`}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Voltar aos projetos
				</a>
			{:else if errorKind === 'forbidden'}
				<p class="text-text-primary">Você não tem permissão para visualizar este projeto.</p>
				<a
					href={`${base}/projetos`}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Voltar aos projetos
				</a>
			{:else}
				<p class="text-text-primary">{errorMessage}</p>
				<button
					type="button"
					onclick={load}
					class="rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					Tentar novamente
				</button>
			{/if}
		</div>
	{:else if data}
		<ProjectHeader
			project={data.project}
			options={data.options}
			permissions={data.permissions}
			derivedData={data.derived}
			{topOffset}
			fieldStates={{
				titulo: projectFieldStates.titulo,
				status: projectFieldStates.status,
				prioridade: projectFieldStates.prioridade
			}}
			onEditField={onHeaderEditField}
		/>

		<div class="flex flex-wrap items-center gap-3">
			<a
				href={`${base}/projetos/${data.project.id}/historico`}
				class="inline-flex w-fit items-center rounded-md border border-border-subtle bg-surface px-4 py-2 text-sm font-medium text-text-primary no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
			>
				Histórico do projeto
			</a>

			{#if canEdit && isVigente}
				<button
					type="button"
					id="btn-concluir-projeto"
					onpointerdown={() => void primeConcludeAudioContext()}
					onclick={onConcludeProject}
					disabled={!canConclude || concludeInFlight}
					title={canConclude
						? 'Concluir o projeto'
						: 'Todas as etapas devem estar iniciadas e concluídas'}
					class="ml-auto inline-flex w-fit items-center gap-1 rounded-md border border-success bg-success px-4 py-2 text-sm font-medium text-white transition-colors duration-fast hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-success"
				>
					{#if concludeInFlight}
						<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>
						Concluindo...
					{:else}
						<i class="fas fa-check-circle" aria-hidden="true"></i>
						Concluir Projeto
					{/if}
				</button>
			{/if}
		</div>

		<!-- Detalhes editaveis do projeto (campos fora do cabecalho) -->
		<Card labelId="project-details-title">
			{#snippet header()}
				<h2 id="project-details-title" class="font-heading text-lg font-semibold text-text-primary">
					Detalhes
				</h2>
			{/snippet}

			<div class="grid gap-4 sm:grid-cols-2">
				<InlineEditField
					fieldId="project-observacao"
					label="Observação"
					value={data.project.observacao}
					kind="textarea"
					readonly={!canEdit}
					pending={projectFieldStates.observacao?.pending}
					error={projectFieldStates.observacao?.error}
					onSave={(v) => saveProjectField('observacao', v)}
				/>
				<InlineEditField
					fieldId="project-sei"
					label="Processo SEI"
					value={data.project.sei_process}
					kind="text"
					readonly={!canEdit}
					pending={projectFieldStates.sei_process?.pending}
					error={projectFieldStates.sei_process?.error}
					onSave={(v) => saveProjectField('sei_process', v)}
				/>
				<InlineEditField
					fieldId="project-github"
					label="Link do GitHub"
					value={data.project.github_link}
					kind="text"
					readonly={!canEdit}
					pending={projectFieldStates.github_link?.pending}
					error={projectFieldStates.github_link?.error}
					onSave={(v) => saveProjectField('github_link', v)}
				/>
				<InlineEditField
					fieldId="project-doc"
					label="Link da documentação"
					value={data.project.documentation_link}
					kind="text"
					readonly={!canEdit}
					pending={projectFieldStates.documentation_link?.pending}
					error={projectFieldStates.documentation_link?.error}
					onSave={(v) => saveProjectField('documentation_link', v)}
				/>
				<InlineEditField
					fieldId="project-product"
					label="Link do produto"
					value={data.project.product_link}
					kind="text"
					readonly={!canEdit}
					pending={projectFieldStates.product_link?.pending}
					error={projectFieldStates.product_link?.error}
					onSave={(v) => saveProjectField('product_link', v)}
				/>
			</div>
		</Card>

		<!-- Secao de Etapas (divisor + acoes + tabela), paridade com v4.5 -->
		<div class="section-divider">
			<h2 id="project-stages-title" class="font-heading text-lg font-bold text-text-primary">
				Etapas do Projeto
			</h2>
		</div>

		{#if canEdit}
			<div class="flex flex-wrap items-center justify-end gap-2">
				<button
					type="button"
					onclick={openImport}
					class="inline-flex items-center gap-1 rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<i class="fas fa-file-import" aria-hidden="true"></i>
					Importar Modelo
				</button>
				<button
					type="button"
					onclick={openCreateMeeting}
					class="inline-flex items-center gap-1 rounded-md border border-border-subtle bg-surface px-3 py-2 text-sm font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<i class="fab fa-google" aria-hidden="true"></i>
					Adicionar reunião
				</button>
			</div>
		{/if}

		<StageList
			etapas={data.etapas}
			{projectId}
			readonly={!canEdit}
			{reordering}
			{reorderError}
			{addingStage}
			{addStageError}
			{rowStates}
			{onReorder}
			{onUpdateField}
			{onCycleStatus}
			{onSaveComentario}
			onDelete={onDeleteEtapa}
			{onOpenTasks}
			{onAddStage}
			{onDateContextMenu}
		>
			{#snippet meetingSlot(etapa)}
				{#if etapa.meeting}
					<MeetingDisplay
						meeting={etapa.meeting}
						busy={meetingDeleting[etapa.id] ?? false}
						onEdit={() => openEditMeeting(etapa.id)}
						onDelete={() => void onDeleteMeeting(etapa.id)}
					/>
				{/if}
			{/snippet}
		</StageList>

		<ImportModelModal
			open={importOpen}
			{templates}
			loading={templatesLoading}
			submitting={importSubmitting}
			error={importError}
			onConfirm={onConfirmImport}
			onClose={closeImport}
		/>

		<!-- Reunião Google: criar/editar (reusa CalendarEventModal). -->
		<CalendarEventModal
			open={meetingModalOpen}
			event={meetingModalEvent}
			busy={meetingModalBusy}
			error={meetingModalError}
			onSave={onSaveMeeting}
			onClose={closeMeetingModal}
		/>

		<!-- Quick-add de tarefas da etapa (modal), paridade com 11-stage-task-quick-add.js -->
		{#if quickAddEtapa}
			<StageTaskQuickAdd
				{projectId}
				projectTitulo={data.project.titulo}
				etapaId={quickAddEtapa.id}
				etapaDescricao={quickAddEtapa.descricao ?? ''}
				etapaDatas={etapaDatasLabel(quickAddEtapa)}
				stageDone={quickAddEtapa.done}
				{drawer}
				onClose={closeQuickAdd}
				onProgressChange={onTaskProgressChange}
			/>
		{/if}
	{/if}
</section>

<!-- Menu de contexto de dias úteis (+7/+14/+21), paridade com 07-stage-dnd.js -->
{#if dateMenu}
	<button
		type="button"
		class="date-menu-backdrop"
		aria-label="Fechar menu"
		onclick={closeDateMenu}
		oncontextmenu={(e) => {
			e.preventDefault();
			closeDateMenu();
		}}
	></button>
	<ul
		class="date-context-menu"
		style={`left:${dateMenu.x}px; top:${dateMenu.y}px`}
		role="menu"
	>
		{#each [7, 14, 21] as days (days)}
			<li role="none">
				<button type="button" role="menuitem" onclick={() => void applyDateDays(days)}>
					<i class="fas fa-plus-circle text-success" aria-hidden="true"></i>+ {days} dias
				</button>
			</li>
		{/each}
	</ul>
{/if}

<!-- Modal de confirmação de cascata de datas -->
{#if cascadePrompt}
	<div class="cascade-overlay" role="presentation" onclick={dismissCascade}>
		<div
			class="cascade-modal"
			role="dialog"
			aria-modal="true"
			aria-labelledby="cascade-title"
			onclick={(e) => e.stopPropagation()}
		>
			<h5 id="cascade-title">Atualizar Datas Subsequentes?</h5>
			<p>
				Deseja aplicar a mesma alteração de dias para as datas de início e fim de todas as etapas
				posteriores?
			</p>
			<div class="cascade-buttons">
				<button type="button" class="cascade-btn cascade-btn-secondary" onclick={dismissCascade}>
					Não
				</button>
				<button
					type="button"
					class="cascade-btn cascade-btn-primary"
					disabled={cascadeBusy}
					onclick={confirmCascade}
				>
					{cascadeBusy ? 'Atualizando…' : 'Sim, atualizar'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Aviso de conclusão (overlay) — o chime + confete são disparados na ação. -->
<ConcludeCelebrationOverlay
	active={celebrationActive}
	title={celebrationTitle}
	message={celebrationMessage}
/>

<TaskDrawer store={drawer} />

<style>
	/* Divisor de seção "Etapas do Projeto" */
	.section-divider {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-top: 0.5rem;
	}
	.section-divider::after {
		content: '';
		flex: 1;
		height: 1px;
		background: var(--app-color-border, #dfe7f1);
	}

	/* Menu de contexto de dias úteis (paridade .custom-context-menu) */
	.date-menu-backdrop {
		position: fixed;
		inset: 0;
		z-index: 1049;
		background: transparent;
		border: 0;
		cursor: default;
	}
	.date-context-menu {
		position: fixed;
		z-index: 1050;
		list-style: none;
		margin: 0;
		padding: 0.4rem;
		min-width: 170px;
		background: var(--app-color-surface, rgba(255, 255, 255, 0.98));
		border: 1px solid var(--app-color-border, #d6e2ee);
		border-radius: 11px;
		box-shadow: 0 12px 28px rgba(24, 53, 86, 0.16);
		transform-origin: top left;
		animation: dateMenuIn 0.14s ease;
	}
	.date-context-menu button {
		display: flex;
		align-items: center;
		gap: 0.52rem;
		width: 100%;
		padding: 0.45rem 0.62rem;
		border: 0;
		border-radius: 8px;
		background: none;
		color: var(--app-color-text, #365172);
		font-size: 0.875rem;
		text-align: left;
		cursor: pointer;
		transition:
			background-color 0.14s ease,
			color 0.14s ease;
	}
	.date-context-menu button:hover,
	.date-context-menu button:focus-visible {
		background-color: var(--app-color-surface-muted, #edf4fc);
		color: var(--app-color-heading, #24476f);
		outline: none;
	}
	.date-context-menu .text-success {
		color: var(--app-color-success, #167a44);
	}
	@keyframes dateMenuIn {
		from {
			opacity: 0;
			transform: translateY(-3px) scale(0.98);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}

	/* Modal de cascata (paridade .confirm-modal-overlay/.confirm-modal) */
	.cascade-overlay {
		position: fixed;
		inset: 0;
		z-index: 1060;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(0, 0, 0, 0.4);
	}
	.cascade-modal {
		background: var(--app-color-surface, #fff);
		padding: 2rem;
		border-radius: 8px;
		box-shadow: 0 5px 20px rgba(0, 0, 0, 0.2);
		max-width: 400px;
		text-align: center;
		color: var(--app-color-text, #304a66);
	}
	.cascade-modal h5 {
		margin: 0 0 0.75rem;
		font-weight: 700;
		color: var(--app-color-heading, #0f172a);
	}
	.cascade-buttons {
		margin-top: 1.5rem;
		display: flex;
		justify-content: center;
		gap: 1rem;
	}
	.cascade-btn {
		padding: 0.5rem 1.1rem;
		border-radius: 8px;
		font-size: 0.875rem;
		font-weight: 600;
		cursor: pointer;
		border: 1px solid transparent;
	}
	.cascade-btn-secondary {
		background: var(--app-color-surface-muted, #f1f5f9);
		border-color: var(--app-color-border, #dfe7f1);
		color: var(--app-color-text, #475569);
	}
	.cascade-btn-primary {
		background: #005a92;
		color: #fff;
	}
	.cascade-btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
</style>
