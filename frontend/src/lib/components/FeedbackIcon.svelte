<script lang="ts">
	import { FEEDBACK_ICONS, type FeedbackIconId } from '$lib/icons/feedbackIcons';

	interface Props {
		id: FeedbackIconId;
		size?: number;
		class?: string;
	}

	let { id, size = 20, class: klass = '' }: Props = $props();

	const shapes = $derived(FEEDBACK_ICONS[id]);
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width={1.7}
	stroke-linecap="round"
	stroke-linejoin="round"
	class="shrink-0 {klass}"
	aria-hidden="true"
	focusable="false"
>
	{#each shapes as shape, i (i)}
		{#if shape.type === 'circle'}
			<circle
				cx={shape.cx}
				cy={shape.cy}
				r={shape.r}
				fill={shape.fill ?? 'none'}
				stroke={shape.stroke ?? 'currentColor'}
				stroke-width={shape.strokeWidth ?? 1.7}
			/>
		{:else}
			<path d={shape.d} stroke-width={shape.strokeWidth ?? 1.7} />
		{/if}
	{/each}
</svg>
