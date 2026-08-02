<script lang="ts">
	import { APP_ICONS, type AppIconId } from '$lib/icons/appIcons';

	interface Props {
		id: AppIconId;
		size?: number;
		class?: string;
	}

	let { id, size = 16, class: klass = '' }: Props = $props();

	const paths = $derived(APP_ICONS[id]);
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
		<path d={p.d} opacity={p.opacity} fill-rule={p.fillRule} />
	{/each}
</svg>
