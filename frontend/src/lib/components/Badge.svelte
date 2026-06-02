<script lang="ts">
	/**
	 * Badge semantico. `tone` mapeia para cores da marca (vars semanticas).
	 * Usado para status de tarefa/projeto e prioridades.
	 */
	import type { Snippet } from 'svelte';

	type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

	interface Props {
		tone?: Tone;
		children: Snippet;
	}

	let { tone = 'neutral', children }: Props = $props();

	const toneClass: Record<Tone, string> = {
		neutral: 'bg-surface-muted text-text-secondary border-border-subtle',
		primary: 'bg-primary-100 text-primary-700 border-primary-500',
		success: 'bg-surface-muted text-success border-success',
		warning: 'bg-surface-muted text-warning border-warning',
		danger: 'bg-surface-muted text-danger border-danger',
		info: 'bg-surface-muted text-info border-info'
	};
</script>

<span
	class="inline-flex items-center gap-1 rounded-sm border px-2 py-1 text-xs font-medium {toneClass[
		tone
	]}"
>
	{@render children()}
</span>
