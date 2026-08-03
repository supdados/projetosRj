<script lang="ts">
	import { PROJECT_ICONS, type ProjectIconId } from '$lib/icons/projectIcons';

	interface Props {
		id: ProjectIconId;
		size?: number;
		class?: string;
	}

	let { id, size = 16, class: klass = '' }: Props = $props();

	const paths = $derived(PROJECT_ICONS[id]);
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="currentColor"
	class="shrink-0 {klass}"
	aria-hidden="true"
>
	{#each paths as p (p.d)}
		<path d={p.d} opacity={p.opacity} fill-rule={p.fillRule} transform={p.transform} />
	{/each}
</svg>
