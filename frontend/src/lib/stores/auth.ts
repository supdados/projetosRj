/**
 * Store de autenticacao da SPA.
 *
 * Carrega `GET /api/me` no boot do layout autenticado. Em 401, `client.ts` ja
 * dispara a navegacao top-level para `/login`; aqui apenas marcamos o estado
 * como `unauthenticated` para o guard nao renderizar conteudo protegido.
 *
 * A autorizacao por orgao e e continua server-side; `user.orgaos` aqui e
 * cosmetico (renderizacao), nunca fonte de verdade de escopo.
 */

import { derived, writable, type Readable } from 'svelte/store';
import { get } from '$lib/api/client';
import { ApiClientError } from '$lib/api/client';
import type { User } from '$lib/types/entities';
import { canGrantAdmin } from '$lib/utils/adminGrant';

export type AuthStatus = 'idle' | 'loading' | 'authenticated' | 'unauthenticated';

export interface AuthState {
	status: AuthStatus;
	user: User | null;
	error: string | null;
}

const initial: AuthState = { status: 'idle', user: null, error: null };

const store = writable<AuthState>(initial);

/** Garante que o boot de `/api/me` rode no maximo uma vez por sessao de pagina. */
let bootPromise: Promise<void> | null = null;

/**
 * Carrega o usuario autenticado uma unica vez (idempotente).
 *
 * Em sucesso: `status = 'authenticated'`. Em 401 (`unauthenticated`):
 * `status = 'unauthenticated'` (o redirect para /login ja partiu do client).
 */
export function loadCurrentUser(): Promise<void> {
	if (bootPromise) return bootPromise;

	store.set({ status: 'loading', user: null, error: null });

	bootPromise = get<User>('/api/me')
		.then((user) => {
			store.set({ status: 'authenticated', user, error: null });
		})
		.catch((err: unknown) => {
			const isAuthError =
				err instanceof ApiClientError && err.code === 'unauthenticated';
			store.set({
				status: 'unauthenticated',
				user: null,
				error: isAuthError ? null : 'Falha ao carregar o usuario.'
			});
		});

	return bootPromise;
}

export const auth: Readable<AuthState> = { subscribe: store.subscribe };

/**
 * True somente para o administrador principal (unico que altera `is_admin`).
 * Fail-closed enquanto a sessao nao carrega; o backend segue sendo a fonte da
 * verdade — isto so controla a renderizacao dos controles.
 */
export const podeConcederAdmin: Readable<boolean> = derived(auth, ($auth) =>
	canGrantAdmin($auth.user)
);
