/**
 * Store do escopo de orgao selecionado no topnav.
 *
 * Espelha a funcao do seletor de orgao em arvore do v4.5
 * (`templates/partials/app_topnav.html` + `static/js/components/orgao-tree-picker.js`),
 * que no legado vivia na querystring `?orgao=` propagada por TODAS as telas
 * (`build_orgao_nav_url` / `build_current_orgao_url`). Na SPA nao temos esse
 * roundtrip de URL server-side, entao centralizamos a escolha aqui e
 * persistimos em `localStorage` para sobreviver entre telas/refresh.
 *
 * A AUTORIZACAO por orgao continua server-side: os endpoints `/api/*`
 * sanitizam `?orgao=` para o usuario corrente (`sanitize_orgao_filter_for_current_user`).
 * Este store e cosmetico/UX — apenas escolhe qual filtro enviar. Um `?orgao=`
 * invalido e ignorado/rejeitado pelo backend.
 *
 * `selectedId === null` => "Todos os orgaos" (sem filtro).
 */

import { writable, derived, type Readable } from 'svelte/store';

const STORAGE_KEY = 'projetosrj.orgaoScope';

/** Escopo de orgao selecionado (id + sigla para exibicao no trigger). */
export interface OrgaoScope {
	/** ID do orgao selecionado, ou `null` para "Todos os orgaos". */
	selectedId: number | null;
	/** Sigla exibida no trigger (quando `selectedId` != null). */
	selectedSigla: string | null;
}

const initial: OrgaoScope = { selectedId: null, selectedSigla: null };

/** Le o escopo persistido (tolerante a payload corrompido). */
function readStored(): OrgaoScope {
	if (typeof window === 'undefined') return initial;
	try {
		const raw = window.localStorage.getItem(STORAGE_KEY);
		if (!raw) return initial;
		const parsed = JSON.parse(raw) as Partial<OrgaoScope>;
		const id =
			typeof parsed.selectedId === 'number' && Number.isFinite(parsed.selectedId)
				? parsed.selectedId
				: null;
		const sigla = typeof parsed.selectedSigla === 'string' ? parsed.selectedSigla : null;
		return id === null ? initial : { selectedId: id, selectedSigla: sigla };
	} catch {
		return initial;
	}
}

const store = writable<OrgaoScope>(readStored());

/** Persiste o escopo no `localStorage` (silencioso se indisponivel). */
function persist(scope: OrgaoScope): void {
	if (typeof window === 'undefined') return;
	try {
		window.localStorage.setItem(STORAGE_KEY, JSON.stringify(scope));
	} catch {
		// localStorage indisponivel — segue apenas em memoria.
	}
}

/** Seleciona um orgao (ou `null` para "Todos os orgaos") e persiste. */
export function selectOrgaoScope(selectedId: number | null, selectedSigla: string | null): void {
	const next: OrgaoScope = selectedId === null ? initial : { selectedId, selectedSigla };
	store.set(next);
	persist(next);
}

/** Limpa o escopo (volta para "Todos os orgaos"). */
export function clearOrgaoScope(): void {
	selectOrgaoScope(null, null);
}

export const orgaoScope: Readable<OrgaoScope> = { subscribe: store.subscribe };

/**
 * Querystring pronta para anexar a chamadas `/api/*` que aceitam `?orgao=`
 * (ex.: `/api/dashboard`, `/api/busca`, `/api/board`). Vazia quando "Todos".
 */
export const orgaoScopeQuery: Readable<string> = derived(store, ($scope) =>
	$scope.selectedId === null ? '' : `orgao=${$scope.selectedId}`
);
