<script lang="ts">
	/**
	 * Ícone de status/prioridade. A cor vem do `currentColor` do container — o
	 * componente nunca a define, igual ao dot que ele substitui.
	 *
	 * Uso:
	 *   <StateIcon id="prio-alta" style:color="var(--ds-color-priority-alta)" />
	 */
	import { STATE_ICONS, type StateIconId } from '$lib/icons/stateIcons';

	interface Props {
		id: StateIconId;
		size?: number;
		class?: string;
	}

	let { id, size = 16, class: klass = '' }: Props = $props();

	const shapes = $derived(STATE_ICONS[id]);
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="3"
	stroke-linecap="round"
	stroke-linejoin="round"
	class="shrink-0 {klass}"
	aria-hidden="true"
	focusable="false"
>
	{#each shapes as shape, i (i)}
		{#if shape.kind === 'circle'}
			<circle
				cx={shape.cx}
				cy={shape.cy}
				r={shape.r}
				fill={shape.fill}
				stroke={shape.stroke}
				stroke-width={shape.strokeWidth}
				stroke-dasharray={shape.strokeDasharray}
				opacity={shape.opacity}
			/>
		{:else}
			<path
				d={shape.d}
				fill={shape.fill}
				stroke={shape.stroke}
				stroke-width={shape.strokeWidth}
				opacity={shape.opacity}
			/>
		{/if}
	{/each}
</svg>
