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
	import { goto, replaceState } from '$app/navigation';
	import { ApiClientError } from '$lib/api/client';
	import TaskDrawer from '$lib/components/TaskDrawer.svelte';
	import { createTaskDrawerStore } from '$lib/stores/taskDrawer';
	import { flash } from '$lib/stores/flash';
	import {
		fetchProjectDetail,
		updateProjectInline,
		saveProjectGoals,
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
		ProjectGoalsSelection,
		MeetingPayload
	} from '$lib/types/projectDetail';
	import StageTaskQuickAdd from '$lib/components/StageTaskQuickAdd.svelte';
	import ProjectHistoryDrawer from '$lib/components/ProjectHistoryDrawer.svelte';
	import type { CalendarEvent, CalendarEventInput } from '$lib/types/calendar';
	import ProjectHeader from '$lib/components/ProjectHeader.svelte';
	import InlineEditField from '$lib/components/InlineEditField.svelte';
	import InlineCombobox from '$lib/components/InlineCombobox.svelte';
	import SeiProcessField from '$lib/components/SeiProcessField.svelte';
	import EeggInlineEditor from '$lib/components/EeggInlineEditor.svelte';
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
	type HeaderField =
		| 'titulo'
		| 'short_description'
		| 'status'
		| 'prioridade'
		| 'delivery_type'
		| 'special_project';

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

	// Quick-add de tarefas da etapa (drawer lateral).
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

	// Etapa-alvo do quick-add de tarefas (drawer lateral).
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

	// --- Drawer de histórico (substitui a página /projetos/<id>/historico) ---
	// A URL antiga segue viva: ela redireciona para cá com ?historico=1.
	let historyOpen = $state(false);

	function closeHistory(): void {
		historyOpen = false;
		// Limpa o deep-link para o drawer não reabrir num refresh pós-fechamento.
		const url = new URL(window.location.href);
		if (url.searchParams.has('historico')) {
			url.searchParams.delete('historico');
			replaceState(url, {});
		}
	}

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

	// --- Edicao inline da secao "Detalhes do Projeto" ------------------------

	interface InlineComboOption {
		value: string;
		label: string;
		sublabel?: string;
	}

	/** Orgaos escopados (options.orgaos) -> opcoes do combobox da Area Responsavel. */
	const orgaoOptions = $derived<InlineComboOption[]>(
		(data?.options.orgaos ?? []).map((o) => ({
			value: String(o.id),
			label: o.sigla,
			sublabel: o.nome
		}))
	);

	/**
	 * Indicador ABEP é LEGADO (jun/2026): o campo sai da UI mas o código fica
	 * intacto para reativação futura — basta alternar SHOW_ABEP para `true`.
	 */
	const SHOW_ABEP = false;

	/** Catalogo ABEP (options.abep_indicator) -> opcoes do combobox. Filtra por value/label. */
	const abepOptions = $derived<InlineComboOption[]>(
		(data?.options.abep_indicator ?? []).map((o) => ({
			value: o.value,
			label: o.label,
			sublabel: o.title && o.title !== o.label ? o.title : undefined
		}))
	);

	/**
	 * Salva a Area Responsavel (orgao_id) via /inline. Otimismo/erro reusam
	 * `projectFieldStates`; 403 (fora de escopo) aparece inline e o valor reverte
	 * naturalmente porque o projeto so e substituido em caso de sucesso.
	 */
	async function saveOrgao(value: string): Promise<void> {
		if (!data) return;
		setProjectFieldState('orgao_id', { pending: true, error: null });
		try {
			const result = await updateProjectInline(projectId, { orgao_id: Number(value) });
			data = { ...data, project: result.project };
			setProjectFieldState('orgao_id', { pending: false, error: null });
		} catch (err) {
			if (isUnauthenticated(err)) return;
			const forbidden = err instanceof ApiClientError && err.code === 'forbidden';
			setProjectFieldState('orgao_id', {
				pending: false,
				error: messageOf(
					err,
					forbidden
						? 'Você não tem permissão para atribuir este órgão.'
						: 'Falha ao salvar a área responsável.'
				)
			});
		}
	}

	/**
	 * Rótulo de fallback do ABEP no estado fechado: se o valor salvo (possivelmente
	 * legado/pré-normalização) não casar com nenhuma option do catálogo atual, exibe
	 * o próprio valor cru em vez de "Não informado". Quando há match, devolve null
	 * para o combobox usar o label da option (matchedLabel). Espelha o uso de
	 * `orgao_sigla` na Área Responsável.
	 */
	const abepDisplayLabel = $derived.by<string | null>(() => {
		const value = data?.project.abep_indicator ?? null;
		if (value === null || value === '') return null;
		const matched = abepOptions.some((o) => o.value === value);
		return matched ? null : value;
	});

	/** Salva o Indicador ABEP (value canonico; backend normaliza). */
	function saveAbepIndicator(value: string): void {
		void saveProjectField('abep_indicator', value);
	}

	/**
	 * Salva a lista COMPLETA de processos SEI (substituicao) via /inline.
	 * Handler dedicado porque `saveProjectField` tipa o valor como string.
	 */
	async function saveSeiProcesses(list: string[]): Promise<void> {
		if (!data) return;
		setProjectFieldState('sei_processes', { pending: true, error: null });
		try {
			const result = await updateProjectInline(projectId, { sei_processes: list });
			data = { ...data, project: result.project };
			setProjectFieldState('sei_processes', { pending: false, error: null });
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setProjectFieldState('sei_processes', {
				pending: false,
				error: messageOf(err, 'Falha ao salvar os processos SEI.')
			});
		}
	}

	/**
	 * Salva a cascata EEGG (objetivo/resultado/indicadores) num unico request.
	 * Reusa o estado otimista por campo (`projectFieldStates.eegg`) e re-renderiza
	 * o projeto com a resposta (descricoes EEGG atualizadas).
	 */
	async function saveEegg(selection: ProjectGoalsSelection): Promise<void> {
		if (!data) return;
		setProjectFieldState('eegg', { pending: true, error: null });
		try {
			const result = await saveProjectGoals(projectId, selection);
			data = { ...data, project: result.project };
			setProjectFieldState('eegg', { pending: false, error: null });
		} catch (err) {
			if (isUnauthenticated(err)) return;
			setProjectFieldState('eegg', {
				pending: false,
				error: messageOf(err, 'Falha ao salvar o objetivo/resultado/indicadores.')
			});
		}
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

	// --- Quick-add de tarefas da etapa (drawer lateral) ----------------------

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
	// Fecha o modal de cascata via teclado (Escape), espelhando o clique no backdrop.
	function onCascadeKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') dismissCascade();
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

	/** Cria a etapa; devolve `true` no sucesso (o composer fecha com essa confirmação). */
	async function onAddStage(draft: NewStageDraft): Promise<boolean> {
		if (!draft.descricao.trim() || addingStage) return false;
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
			return false;
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
			return true;
		} catch (err) {
			if (!isUnauthenticated(err)) {
				addStageError = messageOf(err, 'Falha ao adicionar a etapa.');
			}
			return false;
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
		// Deep-link do histórico (redirect da antiga página /historico).
		if ($page.url.searchParams.has('historico')) historyOpen = true;
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
				short_description: projectFieldStates.short_description,
				status: projectFieldStates.status,
				prioridade: projectFieldStates.prioridade,
				delivery_type: projectFieldStates.delivery_type,
				special_project: projectFieldStates.special_project
			}}
			onEditField={onHeaderEditField}
		/>

		<!-- Detalhes editaveis do projeto (campos fora do cabecalho) -->
		<Card labelId="project-details-title">
			{#snippet header()}
				<h2
					id="project-details-title"
					class="flex items-center gap-2 font-heading text-lg font-semibold text-text-primary"
				>
					<i class="fas fa-circle-info text-primary-600" aria-hidden="true"></i>Detalhes do Projeto
				</h2>
			{/snippet}

			<!-- Ações no RODAPÉ do card (Ver Histórico + Concluir), à direita (ref. tela antiga). -->
			{#snippet footer()}
				<button
					type="button"
					onclick={() => (historyOpen = true)}
					class="inline-flex items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-medium text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<i class="fas fa-history" aria-hidden="true"></i>Ver Histórico
				</button>

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
						class="inline-flex items-center gap-1.5 rounded-md border border-success bg-success px-3 py-1.5 text-xs font-medium text-white transition-colors duration-fast hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-success"
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
			{/snippet}

			<!-- Identidade + EEGG (editaveis inline, clicando direto no valor) —
			     cada campo em um cartão com borda/sombra, hierarquia e folga. -->
			<div class="flex flex-col gap-6">
				<div class="grid gap-4 sm:grid-cols-2 {SHOW_ABEP ? 'lg:grid-cols-4' : 'lg:grid-cols-3'}">
					<!-- Área Responsável: combobox pesquisável de órgãos (orgao_id). -->
					<div class="flex flex-col gap-0.5 rounded-md border border-border-subtle bg-surface px-4 py-1 text-sm shadow-sm">
						<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">Área Responsável</span>
						<InlineCombobox
							fieldId="project-orgao-id"
							label="Área Responsável, editar"
							value={data.project.orgao_id !== null && data.project.orgao_id !== undefined
								? String(data.project.orgao_id)
								: null}
							displayLabel={data.project.orgao_sigla}
							options={orgaoOptions}
							emptyLabel="Não informado"
							readonly={!canEdit}
							pending={projectFieldStates.orgao_id?.pending}
							error={projectFieldStates.orgao_id?.error}
							onSelect={saveOrgao}
						/>
					</div>
					<!-- Órgão: texto livre legado (orgao). -->
					<div class="flex flex-col gap-0.5 rounded-md border border-border-subtle bg-surface px-4 py-1 text-sm shadow-sm">
						<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">Órgão</span>
						<InlineEditField
							fieldId="project-orgao"
							label="Órgão"
							value={data.project.orgao}
							kind="text"
							variant="cell"
							emptyLabel="Não informado"
							readonly={!canEdit}
							pending={projectFieldStates.orgao?.pending}
							error={projectFieldStates.orgao?.error}
							onSave={(v) => saveProjectField('orgao', v)}
						/>
					</div>
					<!-- Processo SEI mora na primeira linha (posição da tela antiga). -->
					<div class="flex flex-col gap-0.5 rounded-md border border-border-subtle bg-surface px-4 py-1 text-sm shadow-sm">
						<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">Processo SEI</span>
						<SeiProcessField
							fieldId="project-sei"
							processes={data.project.sei_processes}
							readonly={!canEdit}
							pending={projectFieldStates.sei_processes?.pending}
							error={projectFieldStates.sei_processes?.error}
							onSave={saveSeiProcesses}
						/>
					</div>
					{#if SHOW_ABEP}
					<!-- Indicador ABEP: combobox pesquisável do catálogo (abep_indicator). -->
					<div class="flex flex-col gap-0.5 rounded-md border border-border-subtle bg-surface px-4 py-1 text-sm shadow-sm">
						<span class="text-xs font-semibold uppercase tracking-wide text-text-muted">Indicador ABEP</span>
						<InlineCombobox
							fieldId="project-abep"
							label="Indicador ABEP, editar"
							value={data.project.abep_indicator}
							displayLabel={abepDisplayLabel}
							options={abepOptions}
							emptyLabel="Não informado"
							readonly={!canEdit}
							pending={projectFieldStates.abep_indicator?.pending}
							error={projectFieldStates.abep_indicator?.error}
							onSelect={saveAbepIndicator}
						/>
					</div>
					{/if}
				</div>

				<!-- EEGG: cascata objetivo/resultado/indicadores editável inline. -->
				<div class="flex flex-col gap-3">
					<h3 class="flex items-center gap-2 font-heading text-sm font-semibold text-text-primary">
						<i class="fas fa-sitemap text-primary-600" aria-hidden="true"></i>EEGD - Estratégia
						Estadual de Governo Digital
					</h3>
					<EeggInlineEditor
						fieldId="project-eegg"
						objetivoId={data.project.objetivo_id}
						resultadoId={data.project.resultado_esperado_id}
						indicadoresIds={data.project.indicadores_ids}
						objetivoDescricao={data.project.objetivo_descricao}
						resultadoDescricao={data.project.resultado_esperado_descricao}
						indicadoresDescricoes={data.project.indicadores_descricoes}
						readonly={!canEdit}
						pending={projectFieldStates.eegg?.pending}
						error={projectFieldStates.eegg?.error}
						onSave={saveEegg}
					/>
				</div>
			</div>

			<!-- Informações adicionais (editáveis) — agrupadas em um bloco com borda,
			     espelhando a seção da tela antiga. -->
			<div class="mt-6 flex flex-col gap-3">
				<h3 class="flex items-center gap-2 font-heading text-sm font-semibold text-text-primary">
					<i class="fas fa-circle-info text-primary-600" aria-hidden="true"></i>Informações Adicionais
				</h3>
				<div class="rounded-md border border-border-subtle bg-surface p-5 shadow-sm">
					<!-- Links compactos: ícone + rótulo + valor na MESMA linha (ref. tela antiga).
					     Rótulos com largura FIXA (w-32) para os campos começarem alinhados
					     na mesma coluna, independente do tamanho do nome. -->
					<div class="flex flex-col gap-2.5">
						<div class="flex items-center gap-2 text-sm">
							<i class="fab fa-github w-4 shrink-0 text-center text-primary-600" aria-hidden="true"></i>
							<span class="w-32 shrink-0 font-semibold text-text-primary">Github:</span>
							<div class="min-w-0 flex-1">
								<InlineEditField
									fieldId="project-github"
									label="Link do GitHub"
									value={data.project.github_link}
									kind="text"
									variant="cell"
									emptyLabel="Não informado"
									readonly={!canEdit}
									pending={projectFieldStates.github_link?.pending}
									error={projectFieldStates.github_link?.error}
									onSave={(v) => saveProjectField('github_link', v)}
								/>
							</div>
						</div>
						<div class="flex items-center gap-2 text-sm">
							<i class="fas fa-book w-4 shrink-0 text-center text-primary-600" aria-hidden="true"></i>
							<span class="w-32 shrink-0 font-semibold text-text-primary">Documentação:</span>
							<div class="min-w-0 flex-1">
								<InlineEditField
									fieldId="project-doc"
									label="Link da documentação"
									value={data.project.documentation_link}
									kind="text"
									variant="cell"
									emptyLabel="Não informado"
									readonly={!canEdit}
									pending={projectFieldStates.documentation_link?.pending}
									error={projectFieldStates.documentation_link?.error}
									onSave={(v) => saveProjectField('documentation_link', v)}
								/>
							</div>
						</div>
						<div class="flex items-center gap-2 text-sm">
							<i class="fas fa-box w-4 shrink-0 text-center text-primary-600" aria-hidden="true"></i>
							<span class="w-32 shrink-0 font-semibold text-text-primary">Produto:</span>
							<div class="min-w-0 flex-1">
								<InlineEditField
									fieldId="project-product"
									label="Link do produto"
									value={data.project.product_link}
									kind="text"
									variant="cell"
									emptyLabel="Não informado"
									readonly={!canEdit}
									pending={projectFieldStates.product_link?.pending}
									error={projectFieldStates.product_link?.error}
									onSave={(v) => saveProjectField('product_link', v)}
								/>
							</div>
						</div>
					</div>

					<div class="my-4 border-t border-border-subtle"></div>

					<!-- Observação à esquerda; "Adicionar Tarefas" à direita (ref. tela antiga). -->
					<div class="flex items-start justify-between gap-4">
						<div class="flex min-w-0 flex-1 flex-col gap-1.5 text-sm">
							<span class="flex items-center gap-2 text-sm font-semibold text-text-primary">
								<i class="fas fa-note-sticky w-4 text-center text-primary-600" aria-hidden="true"></i
								>Observação:
							</span>
							<InlineEditField
								fieldId="project-observacao"
								label="Observação"
								value={data.project.observacao}
								kind="textarea"
								variant="cell"
								emptyLabel="Nenhuma observação registrada."
								readonly={!canEdit}
								pending={projectFieldStates.observacao?.pending}
								error={projectFieldStates.observacao?.error}
								onSave={(v) => saveProjectField('observacao', v)}
							/>
						</div>
						<!-- Navega para o hub de tarefas filtrado por este projeto. A SPA NAO
						     tem rota /projeto/<id>/tarefas: a pagina /tarefas le ?project= no
						     mount (mesmo destino do 302 do KEEP-ENDPOINT main.project_tasks). -->
						<a
							href={`/tarefas?project=${data.project.id}`}
							class="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-semibold text-primary-700 no-underline shadow-sm transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
						>
							<i class="fas fa-plus-circle" aria-hidden="true"></i>Adicionar tarefa
						</a>
					</div>
				</div>
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

		<!-- Quick-add de tarefas da etapa (drawer lateral; abre o TaskDrawer por cima) -->
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
			tabindex={-1}
			onclick={(e) => e.stopPropagation()}
			onkeydown={onCascadeKeydown}
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

{#if historyOpen && data}
	<ProjectHistoryDrawer
		projectId={data.project.id}
		projectTitulo={data.project.titulo}
		onClose={closeHistory}
	/>
{/if}

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
		background: var(--color-border);
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
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
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
		color: var(--color-text-secondary);
		font-size: 0.875rem;
		text-align: left;
		cursor: pointer;
		transition:
			background-color 0.14s ease,
			color 0.14s ease;
	}
	.date-context-menu button:hover,
	.date-context-menu button:focus-visible {
		background-color: var(--color-surface-muted);
		color: var(--color-text-primary);
		outline: none;
	}
	.date-context-menu .text-success {
		color: var(--ds-color-success-600);
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
		background: var(--color-surface);
		padding: 2rem;
		border-radius: 16px;
		box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
		max-width: 400px;
		text-align: center;
		color: var(--color-text-secondary);
	}
	.cascade-modal h5 {
		margin: 0 0 0.75rem;
		font-weight: 700;
		color: var(--color-text-primary);
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
		background: var(--color-surface-muted);
		border-color: var(--color-border);
		color: var(--color-text-secondary);
	}
	.cascade-btn-primary {
		background: var(--ds-color-primary-600);
		color: #fff;
	}
	.cascade-btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
</style>
