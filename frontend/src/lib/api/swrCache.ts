/**
 * Cache stale-while-revalidate em memoria de modulo. Sobrevive a remounts de
 * rota (o modulo persiste entre navegacoes da SPA), entao voltar a uma pagina
 * mostra o ultimo dado conhecido instantaneamente enquanto o fetch revalida em
 * background — sem flash de "Carregando…".
 *
 * Sem TTL de proposito: a entrada e apenas "ultimo dado bom" e TODA visita
 * revalida; o cache nunca substitui o fetch. Morre no unload da aba (nada em
 * localStorage), entao sessao expirada/logout nao vaza dado entre usuarios.
 *
 * Exemplo:
 *   const cache = createSwrCache<DashboardData>();
 *   const stale = cache.peek(scopeKey); // sincrono, para popular o 1o render
 *   cache.store(scopeKey, fresh);       // apos fetch bem-sucedido
 */
export interface SwrCache<T> {
	/** Ultimo dado bom da chave, ou null se nunca carregado. */
	peek(key: string): T | null;
	/** Grava o dado fresco da chave (chamar apenas em sucesso de fetch). */
	store(key: string, value: T): void;
}

export function createSwrCache<T>(): SwrCache<T> {
	const entries = new Map<string, T>();
	return {
		peek: (key: string): T | null => entries.get(key) ?? null,
		store: (key: string, value: T): void => {
			entries.set(key, value);
		}
	};
}
