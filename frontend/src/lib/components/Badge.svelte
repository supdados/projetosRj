<script lang="ts">
	/**
	 * Badge semantico (pilula). `tone` mapeia para cores da marca (vars
	 * semanticas), usado para status de tarefa/projeto e prioridades.
	 *
	 * Fidelidade ao original (.priority-badge em 00-foundation.css): pilula
	 * totalmente arredondada (radius 20px ~= rounded-full), texto semibold,
	 * MAIUSCULAS com letter-spacing "wide" (0.02em), padding 0.25rem 0.75rem,
	 * fundo suave do tom + texto colorido. Tons via vars semanticas (dark-safe).
	 *
	 * `tone` continua sendo a unica prop requerida pelos call-sites existentes.
	 */
	import type { Snippet } from 'svelte';

	type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

	interface Props {
		tone?: Tone;
		children: Snippet;
	}

	let { tone = 'neutral', children }: Props = $props();

	const toneClass: Record<Tone, string> = {
		neutral: 'bg-surface-muted text-text-secondary',
		primary: 'bg-primary-100 text-primary-700',
		success: 'bg-surface-muted text-success',
		warning: 'bg-surface-muted text-warning',
		danger: 'bg-surface-muted text-danger',
		info: 'bg-surface-muted text-info'
	};
</script>

<span
	class="inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide {toneClass[
		tone
	]}"
>
	{@render children()}
</span>
