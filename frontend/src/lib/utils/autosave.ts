/**
 * AUTOSAVE robusto e PURO (sem Svelte/DOM) para o drawer de tarefa (Fase 5b-2).
 *
 * Espelha as garantias do JS legado (`static/js/modules/kanban/drawer-core.js`)
 * sem reimplementar DOM-as-state:
 *   - DEBOUNCE (~520ms): edições em rajada coalescem numa única chamada.
 *   - GUARDA DE RESPOSTA OBSOLETA (`saveToken`): respostas de saves antigos são
 *     DESCARTADAS — a última edição sempre vence (nunca "ressuscita" valor velho).
 *   - COALESCING (`hasPendingSave`): se o usuário editar DURANTE um save em voo,
 *     enfileira UM novo save para rodar assim que o atual terminar.
 *   - `flush()`: salva IMEDIATAMENTE o pendente (ao fechar o drawer / blur),
 *     cancelando o debounce e AGUARDANDO o save em voo assentar. NUNCA perde
 *     edição — nem a coalescida durante um save em andamento.
 *
 * `persistFn` recebe o snapshot mais recente e devolve uma Promise; o resultado
 * só é entregue ao `onSaved` se o token ainda for o corrente. A função é agnóstica
 * ao shape do snapshot (genérica em `S`) e ao retorno (`R`).
 *
 * Exemplo:
 *   const auto = createAutosave(
 *     (fields) => saveFields(taskId, fields),
 *     { onSaved: (detail) => drawer.applyDetail(detail) }
 *   );
 *   auto.schedule({ descricao: 'novo texto' });   // debounced
 *   await auto.flush();                            // ao fechar/blur
 */

/** Estado observável do autosave (para a UI exibir "Salvando…/Salvo/Erro"). */
export type AutosavePhase = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

/** Opções da factory. */
export interface AutosaveOptions<S, R> {
	/** Atraso do debounce em ms (default 520, igual ao legado). */
	debounceMs?: number;
	/** Chamado com o resultado de um save NÃO-obsoleto bem-sucedido. */
	onSaved?: (result: R, snapshot: S) => void;
	/** Chamado quando um save NÃO-obsoleto falha. */
	onError?: (error: unknown, snapshot: S) => void;
	/** Chamado a cada transição de fase (para refletir status na UI). */
	onPhaseChange?: (phase: AutosavePhase) => void;
}

/** API pública do autosave. */
export interface Autosave<S> {
	/** Agenda um save (debounced) com o snapshot mais recente. */
	schedule(snapshot: S): void;
	/** Salva o pendente; false em falha, preservando a edição sem retry automático. */
	flush(): Promise<boolean>;
	/** Tenta novamente o snapshot que falhou, uma vez por ação explícita. */
	retry(): Promise<boolean>;
	/** Cancela o debounce e descarta o pendente (sem salvar). */
	cancel(): void;
	/** Fase corrente do autosave. */
	readonly phase: AutosavePhase;
	/** Há um save em andamento? */
	readonly isSaving: boolean;
	/** Há edição não salva (agendada, coalescida ou retida após falha)? */
	readonly hasPendingSave: boolean;
}

/** Cria um controlador de autosave isolado (um por drawer aberto). */
export function createAutosave<S, R = unknown>(
	persistFn: (snapshot: S) => Promise<R>,
	options: AutosaveOptions<S, R> = {}
): Autosave<S> {
	const debounceMs = options.debounceMs ?? 520;

	let timer: ReturnType<typeof setTimeout> | null = null;
	let saveToken = 0;
	let isSaving = false;
	let hasPending = false;
	let failed = false;
	/** Snapshot mais recente agendado/pendente (a "última edição vence"). */
	let pendingSnapshot: S | null = null;
	let phase: AutosavePhase = 'idle';

	function setPhase(next: AutosavePhase): void {
		if (phase === next) return;
		phase = next;
		options.onPhaseChange?.(next);
	}

	function clearTimer(): void {
		if (timer !== null) {
			clearTimeout(timer);
			timer = null;
		}
	}

	function schedule(snapshot: S): void {
		pendingSnapshot = snapshot;
		hasPending = true;
		failed = false;
		setPhase(isSaving ? 'saving' : 'pending');
		clearTimer();
		timer = setTimeout(() => {
			timer = null;
			void runSave();
		}, debounceMs);
	}

	/** Promise do save em voo — `flush` aguarda por ela antes de decidir que não há pendente. */
	let inFlight: Promise<void> | null = null;

	/**
	 * Executa o save do snapshot pendente, se houver. Se já há um save em voo,
	 * apenas marca `hasPending` (coalescing) — o próprio `finally` re-dispara.
	 */
	function runSave(): Promise<void> {
		clearTimer();
		if (failed || !hasPending || pendingSnapshot === null) return Promise.resolve();
		if (isSaving) {
			// Edição durante save em andamento: enfileira (coalescing).
			hasPending = true;
			return inFlight ?? Promise.resolve();
		}
		inFlight = performSave(pendingSnapshot);
		return inFlight;
	}

	async function performSave(snapshot: S): Promise<void> {
		const token = ++saveToken;
		hasPending = false;
		pendingSnapshot = null;
		isSaving = true;
		setPhase('saving');

		try {
			const result = await persistFn(snapshot);
			if (token !== saveToken) return; // resposta obsoleta — descarta
			if (!hasPending) {
				options.onSaved?.(result, snapshot);
				setPhase('saved');
			}
		} catch (error) {
			if (token !== saveToken) return; // resposta obsoleta — descarta
			// Uma edição mais nova pode prosseguir. A mesma edição que falhou só
			// volta a ser enviada por retry() ou por uma nova edição (P1-03).
			if (hasPending) return;
			pendingSnapshot = snapshot;
			hasPending = true;
			failed = true;
			options.onError?.(error, snapshot);
			setPhase('error');
		} finally {
			if (token === saveToken) {
				isSaving = false;
				if (hasPending && !failed) void runSave();
			}
		}
	}

	async function flush(): Promise<boolean> {
		clearTimer();
		// Aguarda o voo assentar: retornar com save em curso deixaria o pendente
		// coalescido à mercê de um cancel() seguinte (perda silenciosa de edição).
		while (isSaving || (hasPending && !failed)) {
			await (isSaving ? inFlight : runSave());
		}
		return !hasPending;
	}

	function retry(): Promise<boolean> {
		failed = false;
		return flush();
	}

	function cancel(): void {
		clearTimer();
		// Invalida qualquer resposta em voo e descarta o pendente.
		saveToken++;
		hasPending = false;
		failed = false;
		pendingSnapshot = null;
		isSaving = false;
		setPhase('idle');
	}

	return {
		schedule,
		flush,
		retry,
		cancel,
		get phase() {
			return phase;
		},
		get isSaving() {
			return isSaving;
		},
		get hasPendingSave() {
			return hasPending;
		}
	};
}
