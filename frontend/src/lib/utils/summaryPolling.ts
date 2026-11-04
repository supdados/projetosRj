/**
 * Polling leve com pausa em aba oculta — hoje o do resumo do sino
 * (`GET /api/notificacoes/resumo`, ~60 s).
 *
 * Regras:
 *   - consulta na hora ao iniciar e depois a cada `intervaloMs`;
 *   - aba oculta (`documentoOculto()`) pula o tique — quem chama refaz ao
 *     voltar (`visibilitychange` → `atualizarAgora`);
 *   - uma consulta nova aborta a anterior (resposta velha nunca vence);
 *   - erro comum é silencioso (o último valor bom fica); erro que
 *     `deveParar` reconhece (sessão expirada) encerra o polling.
 *
 * Timers e relógio vêm por injeção para o teste rodar com timers falsos.
 *
 * Exemplo:
 *   const polling = iniciarPolling({
 *     carregar: (signal) => fetchNotificacoesResumo(signal),
 *     aoReceber: (resumo) => notificationSummary.definir(resumo),
 *     documentoOculto: () => document.hidden,
 *     intervaloMs: 60_000
 *   });
 *   // ...
 *   polling.parar();
 */

export interface PollingOptions<T> {
	carregar: (signal: AbortSignal) => Promise<T>;
	aoReceber: (valor: T) => void;
	documentoOculto: () => boolean;
	intervaloMs: number;
	/** Erro que encerra o polling de vez (ex.: 401); ausente = nunca para sozinho. */
	deveParar?: (erro: unknown) => boolean;
}

export interface PollingHandle {
	/** Consulta já (aborta a que estiver no ar); no-op depois de `parar`. */
	atualizarAgora(): void;
	parar(): void;
	/** `true` depois de `parar` (manual ou por `deveParar`). */
	readonly parado: boolean;
}

/** Inicia o polling e devolve o controle (consultar já, parar). */
export function iniciarPolling<T>(options: PollingOptions<T>): PollingHandle {
	let parado = false;
	let emVoo: AbortController | null = null;

	function atualizarAgora(): void {
		if (parado) return;
		emVoo?.abort();
		const controller = new AbortController();
		emVoo = controller;
		options
			.carregar(controller.signal)
			.then((valor) => {
				if (controller.signal.aborted || parado) return;
				options.aoReceber(valor);
			})
			.catch((erro: unknown) => {
				if (controller.signal.aborted) return;
				if (options.deveParar?.(erro)) parar();
			})
			.finally(() => {
				if (emVoo === controller) emVoo = null;
			});
	}

	const timer = setInterval(() => {
		if (options.documentoOculto()) return;
		atualizarAgora();
	}, options.intervaloMs);

	function parar(): void {
		if (parado) return;
		parado = true;
		clearInterval(timer);
		emVoo?.abort();
		emVoo = null;
	}

	atualizarAgora();
	return {
		atualizarAgora,
		parar,
		get parado() {
			return parado;
		}
	};
}
