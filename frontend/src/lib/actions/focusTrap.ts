/**
 * Action `use:focusTrap` — prende o foco do teclado dentro de um container de
 * diálogo modal (itens #17 TaskDrawer e #19 CalendarEventModal).
 *
 * Ao montar:
 *   1. Memoriza o elemento que tinha o foco (para restaurar ao desmontar).
 *   2. Foca o primeiro elemento focável do container (ou o próprio container,
 *      que deve ter `tabindex="-1"`, se não houver nenhum).
 *
 * Enquanto montada:
 *   - Intercepta `Tab`/`Shift+Tab` no container e faz o foco "dar a volta"
 *     (do último para o primeiro e vice-versa), nunca escapando do diálogo.
 *
 * Ao desmontar:
 *   - Restaura o foco ao elemento previamente focado (se ainda existir/visível).
 *
 * NÃO trata `Escape`: o fechamento por Esc continua sendo responsabilidade do
 * componente (handler `onkeydown` existente). A action apenas usa `keydown` em
 * captura para o Tab e não chama `stopPropagation`, preservando esse handler.
 *
 * Robustez SSR/jsdom: se `document` não existir, é um no-op seguro.
 *
 * Exemplo:
 *   <div role="dialog" tabindex="-1" use:focusTrap>…</div>
 */

/** Contrato mínimo de uma Svelte action (sem parâmetros). */
interface FocusTrapReturn {
	destroy(): void;
}

/** Seletor dos elementos potencialmente focáveis dentro do diálogo. */
const FOCUSABLE_SELECTOR = [
	'a[href]',
	'button:not([disabled])',
	'input:not([disabled])',
	'select:not([disabled])',
	'textarea:not([disabled])',
	'[tabindex]:not([tabindex="-1"])'
].join(',');

/** Um elemento está visível/operável (descarta itens ocultos do ciclo de Tab). */
function isVisible(element: HTMLElement): boolean {
	if (element.hidden) return false;
	if (element.getAttribute('aria-hidden') === 'true') return false;
	// Subárvores `inert` (ex.: fundo de um diálogo de confirmação) ficam visíveis
	// mas não-focáveis — `focus()` nelas é no-op e quebraria o ciclo do trap.
	if (element.closest('[inert]')) return false;
	// `offsetParent` é `null` para elementos com `display:none` (ou ancestrais).
	return element.offsetParent !== null || element.getClientRects().length > 0;
}

/** Lista, na ordem do DOM, os elementos focáveis e visíveis do container. */
function focusableWithin(container: HTMLElement): HTMLElement[] {
	const nodes = Array.from(
		container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
	);
	return nodes.filter(isVisible);
}

/**
 * Aplica o focus trap ao nó do diálogo.
 *
 * @param node Container do diálogo (deve ter `tabindex="-1"` como fallback).
 */
export function focusTrap(node: HTMLElement): FocusTrapReturn {
	const hasDom = typeof document !== 'undefined';
	const previouslyFocused = hasDom ? (document.activeElement as HTMLElement | null) : null;

	function focusFirst(): void {
		const focusables = focusableWithin(node);
		(focusables[0] ?? node).focus();
	}

	function onKeydown(event: KeyboardEvent): void {
		if (event.key !== 'Tab') return;
		const focusables = focusableWithin(node);
		if (focusables.length === 0) {
			// Sem nada focável: mantém o foco no próprio diálogo.
			event.preventDefault();
			node.focus();
			return;
		}
		const first = focusables[0];
		const last = focusables[focusables.length - 1];
		const active = document.activeElement;

		if (event.shiftKey) {
			// Shift+Tab no primeiro (ou fora do ciclo) volta ao último.
			if (active === first || !node.contains(active)) {
				event.preventDefault();
				last.focus();
			}
			return;
		}
		// Tab no último (ou fora do ciclo) volta ao primeiro.
		if (active === last || !node.contains(active)) {
			event.preventDefault();
			first.focus();
		}
	}

	if (hasDom) {
		// `keydown` na fase de captura: garante o trap mesmo que o handler do
		// componente (Esc) consuma o evento depois, sem competir com ele.
		node.addEventListener('keydown', onKeydown, true);
		// Foca o primeiro elemento após a montagem inicial do conteúdo.
		focusFirst();
	}

	return {
		destroy(): void {
			if (!hasDom) return;
			node.removeEventListener('keydown', onKeydown, true);
			// Restaura o foco ao elemento anterior, se ainda estiver no documento.
			if (
				previouslyFocused &&
				typeof previouslyFocused.focus === 'function' &&
				document.contains(previouslyFocused)
			) {
				previouslyFocused.focus();
			}
		}
	};
}
