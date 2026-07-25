/**
 * Store de tema (claro/escuro).
 *
 * Persiste em `localStorage('projetosrj.theme')` e reflete em
 * `<html data-theme>`. O valor inicial ja foi aplicado antes do paint pelo
 * script anti-flash de `app.html` (portado de base.html:12-32); aqui apenas
 * sincronizamos o store ao DOM e expomos `toggle`/`setTheme`.
 *
 * As vars semanticas de `app.css` trocam sozinhas com `data-theme`, sem
 * variantes `dark:`.
 */

import { writable, type Readable } from 'svelte/store';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'projetosrj.theme';

/** Le o tema atual do `<html data-theme>` (semeado pelo anti-flash). */
function readDomTheme(): Theme {
	if (typeof document === 'undefined') return 'light';
	return document.documentElement.getAttribute('data-theme') === 'dark'
		? 'dark'
		: 'light';
}

const store = writable<Theme>(readDomTheme());

/** Aplica o tema ao DOM e persiste no localStorage. */
function applyTheme(theme: Theme): void {
	if (typeof document !== 'undefined') {
		document.documentElement.setAttribute('data-theme', theme);
		const meta = document.querySelector<HTMLMetaElement>('#appThemeColorMeta');
		if (meta) meta.content = theme === 'dark' ? '#000000' : '#005A92';
	}
	try {
		window.localStorage.setItem(STORAGE_KEY, theme);
	} catch {
		// localStorage indisponivel — segue apenas com o DOM atualizado.
	}
}

export function setTheme(theme: Theme): void {
	applyTheme(theme);
	store.set(theme);
}

export function toggleTheme(): void {
	store.update((current) => {
		const next: Theme = current === 'dark' ? 'light' : 'dark';
		applyTheme(next);
		return next;
	});
}

export const theme: Readable<Theme> = { subscribe: store.subscribe };
