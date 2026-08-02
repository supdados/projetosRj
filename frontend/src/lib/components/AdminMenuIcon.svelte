<script module lang="ts">
	export type AdminIconKind = 'usuarios' | 'orgaos' | 'templates' | 'csv' | 'sair';
</script>

<script lang="ts">
	interface Props {
		kind: AdminIconKind;
	}

	let { kind }: Props = $props();
</script>

<span class="relative inline-flex h-4 w-4 shrink-0 text-text-muted" aria-hidden="true">
	{#if kind === 'usuarios'}
		<svg
			viewBox="0 0 24 24"
			fill="currentColor"
			class="absolute inset-0 group-hover:opacity-0 group-focus-visible:opacity-0"
			><g opacity=".48"
				><path d="M5.4 6A2.4 2.4 0 1 1 5.4 10.8A2.4 2.4 0 1 1 5.4 6Z" /><path
					d="M1.6 18A3.8 3.8 0 0 1 9.2 18Z"
				/><path d="M18.6 6A2.4 2.4 0 1 1 18.6 10.8A2.4 2.4 0 1 1 18.6 6Z" /><path
					d="M14.8 18A3.8 3.8 0 0 1 22.4 18Z"
				/></g
			><path d="M12 6.4A3.2 3.2 0 1 1 12 12.8A3.2 3.2 0 1 1 12 6.4Z" /><path
				d="M5.4 20.6A6.6 6.6 0 0 1 18.6 20.6Z"
			/></svg
		>
		<svg
			viewBox="0 0 24 24"
			class="absolute inset-0 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100"
			><g
				fill="#8FB6CC"
				><path d="M5.4 6A2.4 2.4 0 1 1 5.4 10.8A2.4 2.4 0 1 1 5.4 6Z" /><path
					d="M1.6 18A3.8 3.8 0 0 1 9.2 18Z"
				/></g
			><g
				fill="#8FB6CC"
				><path d="M18.6 6A2.4 2.4 0 1 1 18.6 10.8A2.4 2.4 0 1 1 18.6 6Z" /><path
					d="M14.8 18A3.8 3.8 0 0 1 22.4 18Z"
				/></g
			><g
				fill="#1B6E96"
				><path d="M12 6.4A3.2 3.2 0 1 1 12 12.8A3.2 3.2 0 1 1 12 6.4Z" /><path
					d="M5.4 20.6A6.6 6.6 0 0 1 18.6 20.6Z"
				/></g
			></svg
		>
	{:else if kind === 'orgaos'}
		<svg
			viewBox="0 0 24 24"
			fill="currentColor"
			class="absolute inset-0 group-hover:opacity-0 group-focus-visible:opacity-0"
			><path d="M9.4 3H14.2L15.8 4.6V8H9.4Z" /><g opacity=".48"
				><path d="M11.8 8H12.6V11.2H11.8Z" /><path d="M4 11.2H20V12H4Z" /><path
					d="M4 12H4.8V15.2H4Z"
				/><path d="M11.8 12H12.6V15.2H11.8Z" /><path d="M19.2 12H20V15.2H19.2Z" /></g
			><path d="M2 15.2H5.2L6.4 16.4V19.6H2Z" /><path d="M9.8 15.2H13L14.2 16.4V19.6H9.8Z" /><path
				d="M17.2 15.2H20.4L21.6 16.4V19.6H17.2Z"
			/></svg
		>
		<svg
			viewBox="0 0 24 24"
			class="absolute inset-0 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100"
			><path d="M9.4 3H14.2L15.8 4.6V8H9.4Z" fill="#0B4C70" /><g fill="#A9C6D6"
				><path d="M11.8 8H12.6V11.2H11.8Z" /><path d="M4 11.2H20V12H4Z" /><path
					d="M4 12H4.8V15.2H4Z"
				/><path d="M11.8 12H12.6V15.2H11.8Z" /><path d="M19.2 12H20V15.2H19.2Z" /></g
			><g
				fill="#3585AC"
				><path d="M2 15.2H5.2L6.4 16.4V19.6H2Z" /></g
			><g
				fill="#4A9AC0"
				><path d="M9.8 15.2H13L14.2 16.4V19.6H9.8Z" /></g
			><g
				fill="#68B0CE"
				><path d="M17.2 15.2H20.4L21.6 16.4V19.6H17.2Z" /></g
			></svg
		>
	{:else if kind === 'templates'}
		<svg
			viewBox="0 0 24 24"
			fill="currentColor"
			class="absolute inset-0 group-hover:opacity-0 group-focus-visible:opacity-0"
			><path d="M2.6 2.6H14.6V14.6H2.6Z" opacity=".48" /><path d="M8 8H19.4L21.4 10V21.4H8Z" /></svg
		>
		<svg
			viewBox="0 0 24 24"
			class="absolute inset-0 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100"
			><g
				fill="#8FB6CC"
				><path d="M2.6 2.6H14.6V14.6H2.6Z" /></g
			><path d="M8 8H19.4L21.4 10V21.4H8Z" fill="#1B6E96" /></svg
		>
	{:else if kind === 'csv'}
		<svg
			viewBox="0 0 24 24"
			fill="currentColor"
			class="absolute inset-0 group-hover:opacity-0 group-focus-visible:opacity-0"
			><path
				fill-rule="evenodd"
				d="M4.6 2.6H15L19.4 7V21.4H4.6ZM7.4 10.4H16.6V11.8H7.4ZM7.4 13.4H16.6V14.8H7.4Z"
			/><path d="M15 2.6L19.4 7H15Z" opacity=".48" /></svg
		>
		<svg
			viewBox="0 0 24 24"
			class="absolute inset-0 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100"
			><path
				fill-rule="evenodd"
				d="M4.6 2.6H15L19.4 7V21.4H4.6ZM7.4 10.4H16.6V11.8H7.4ZM7.4 13.4H16.6V14.8H7.4Z"
				fill="#1B6E96"
			/><path d="M15 2.6L19.4 7H15Z" fill="#8FB6CC" /><g
				><path d="M15.1 15.4H17.3V18H19.4L16.2 21.4L13 18H15.1Z" fill="#FFFFFF" /></g
			></svg
		>
	{:else}
		<svg
			viewBox="0 0 24 24"
			fill="currentColor"
			class="absolute inset-0 group-hover:opacity-0 group-focus-visible:opacity-0"
			><path d="M3.4 3.4H11.4V5.6H5.6V18.4H11.4V20.6H3.4Z" opacity=".48" /><path
				d="M12.6 10.4H17.4V7.6L21.8 12L17.4 16.4V13.6H12.6Z"
			/></svg
		>
		<svg
			viewBox="0 0 24 24"
			class="absolute inset-0 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100"
			><path d="M3.4 3.4H11.4V5.6H5.6V18.4H11.4V20.6H3.4Z" fill="#C99A93" /><path
				d="M12.6 10.4H17.4V7.6L21.8 12L17.4 16.4V13.6H12.6Z"
				fill="#8F241B"
			/></svg
		>
	{/if}
</span>
