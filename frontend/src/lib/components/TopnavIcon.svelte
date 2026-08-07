<script module lang="ts">
	export type NavIconKind =
		| 'inicio'
		| 'projetos'
		| 'colecoes'
		| 'pendentes'
		| 'tarefas'
		| 'calendario';
</script>

<script lang="ts">
	import {
		APP_ICONS,
		PROJETOS_ABA_D,
		PROJETOS_FOLHA_D,
		PROJETOS_PASTA_D
	} from '$lib/icons/appIcons';

	interface Props {
		kind: NavIconKind;
		active: boolean;
	}

	let { kind, active }: Props = $props();
</script>

{#if kind === 'inicio'}
	<svg
		width="20"
		height="20"
		viewBox="0 0 24 24"
		fill="currentColor"
		class="shrink-0 overflow-visible"
		aria-hidden="true"
	>
		<g class="nav-fade" opacity={active ? 1 : 0}
			><g opacity=".48"
				><circle cx="17.5" cy="2.15" r="1.25" /><circle cx="19.35" cy="1.5" r="0.95" /><circle
					cx="20.85"
					cy="0.85"
					r="0.6"
				/><circle cx="21.95" cy="0.5" r="0.4" /></g
			></g
		>
		<path d="M16.6 3.4H19.2V8.6H16.6Z" />
		<path d="M12 2.2L23 10.6H1Z" opacity=".48" />
		<path fill-rule="evenodd" d="M4.4 10.6H19.6V21.4H4.4ZM10.2 14.4H13.8V21.4H10.2Z" />
		<path d="M3.4 21.4H20.6V22.6H3.4Z" opacity=".48" />
	</svg>
{:else if kind === 'projetos'}
	<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" class="shrink-0" aria-hidden="true">
		<g opacity=".48">
			<path d={PROJETOS_ABA_D} />
			<g class="nav-fade" opacity={active ? 0 : 1}><path d={PROJETOS_FOLHA_D} /></g>
			<g class="nav-fade" opacity={active ? 1 : 0}
				><path
					fill-rule="evenodd"
					d="M10.4 2.8H18.6V9.2H10.4ZM11.8 4.4H17.2V5.2H11.8ZM11.8 6.2H15.6V7H11.8Z"
				/></g
			>
		</g>
		<path d={PROJETOS_PASTA_D} />
	</svg>
{:else if kind === 'colecoes'}
	<svg
		width="20"
		height="20"
		viewBox="0 0 24 24"
		fill="currentColor"
		class="shrink-0 overflow-visible"
		aria-hidden="true"
	>
		<!-- Ativo: a tampa (losango) sobe, como caixa aberta puxada pelo topo. -->
		<g class="nav-lift" style:transform={active ? 'translateY(-2.6px)' : 'translateY(0)'}>
			<path d="M12 4L20.5 8.25L12 12.5L3.5 8.25Z" />
		</g>
		<g opacity=".48">
			<path d="M3.5 12.4L12 16.6L20.5 12.4L20.5 14.4L12 18.6L3.5 14.4Z" />
			<path d="M3.5 16.4L12 20.6L20.5 16.4L20.5 18.4L12 22.6L3.5 18.4Z" />
		</g>
	</svg>
{:else if kind === 'pendentes'}
	<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" class="shrink-0" aria-hidden="true">
		<path
			fill-rule="evenodd"
			d="M12 2.6L22.2 19.9H1.8ZM10.9 8.6H13.1V14.4H10.9ZM10.9 15.9H13.1V18.1H10.9Z"
		/>
	</svg>
{:else if kind === 'tarefas'}
	<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" class="shrink-0" aria-hidden="true">
		<g class="nav-fade" opacity={active ? 0 : 1}
			><path fill-rule="evenodd" d={APP_ICONS.tarefas[0].d} /></g
		>
		<g class="nav-fade" opacity={active ? 1 : 0}
			><path
				fill-rule="evenodd"
				d="M4.6 4.2H16.7L19.4 6.9V21.2H4.6ZM7.6 10.4H16.4V12.3H7.6ZM7.6 14.6H12V16.5H7.6ZM15 19L12.4 16.4L13.5 15.3L15 16.8L17.6 14.2L18.7 15.3Z"
			/></g
		>
		<path d={APP_ICONS.tarefas[1].d} opacity=".48" />
	</svg>
{:else}
	<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" class="shrink-0" aria-hidden="true">
		<g class="nav-fade" opacity={active ? 0 : 1}
			><path fill-rule="evenodd" d={APP_ICONS.calendario[0].d} /></g
		>
		<g class="nav-fade" opacity={active ? 1 : 0}
			><path
				fill-rule="evenodd"
				d="M2.6 5H19L21.4 7.4V21H2.6ZM4.7 9.4H19.3V10.4H4.7ZM6.2 12.6H8.3V14.7H6.2ZM15.6 12.6H17.7V14.7H15.6ZM10.9 12.6H13V14.7H10.9ZM6.2 16.4H8.3V18.5H6.2ZM9.8 15.3H14.1V19.6H9.8ZM10.8 16.3H13.1V18.6H10.8Z"
			/></g
		>
	</svg>
{/if}

<style>
	.nav-fade {
		transition: opacity 0.22s;
	}
	.nav-lift {
		transition: transform 0.22s cubic-bezier(0.34, 1.15, 0.64, 1);
	}
	@media (prefers-reduced-motion: reduce) {
		.nav-fade {
			transition: none;
		}
		.nav-lift {
			transition: none;
		}
	}
</style>
