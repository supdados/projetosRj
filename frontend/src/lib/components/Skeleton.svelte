<script lang="ts">
	/**
	 * Barra/bloco shimmer de skeleton. Primeiro consumidor do utilitario
	 * `.skeleton-shimmer` (app.css) — tokens `--ds-color-skeleton-*` trocam no
	 * dark mode e a animacao respeita prefers-reduced-motion.
	 *
	 * O chamador dimensiona via `class` (altura/largura/raio):
	 *   <Skeleton class="h-4 w-24 rounded-md" />
	 *   <Skeleton class="h-11 w-11 rounded-full" />
	 */
	interface Props {
		class?: string;
	}

	let { class: className = '' }: Props = $props();
</script>

<span aria-hidden="true" class="skeleton-shimmer block shrink-0 {className}"></span>
