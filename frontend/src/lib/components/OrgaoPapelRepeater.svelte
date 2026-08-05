<script lang="ts">
	/**
	 * Repeater ÁREA × PAPEL dos vínculos do usuário (S2). Cada área vinculada
	 * vira uma linha com o seu papel (Gestor/Editor/Leitor); a seleção de áreas
	 * continua no OrgaoTreeMultiSelect logo abaixo.
	 *
	 * O acesso efetivo é o MAIOR papel entre os vínculos que alcançam a área
	 * (max() em `get_user_orgao_role_map`), então vincular uma área DENTRO de
	 * outra já vinculada nunca reduz permissão — o aviso não bloqueante e a
	 * microcopy abaixo existem para essa surpresa. Autorização é server-side.
	 */
	import OrgaoTreeMultiSelect from '$lib/components/OrgaoTreeMultiSelect.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import type { AdminOrgaoOption, AdminUserOrgaoVinculo } from '$lib/types/adminUsers';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import {
		PAPEL_OPTIONS,
		mergeVinculosComSelecao,
		normalizePapel,
		setVinculoPapel
	} from '$lib/utils/orgaoPapel';
	import { buildOrgaoTree, computeCoveringAncestors } from '$lib/utils/orgaoTree';

	interface Props {
		options: AdminOrgaoOption[];
		value: AdminUserOrgaoVinculo[];
		onChange: (next: AdminUserOrgaoVinculo[]) => void;
		disabled?: boolean;
		/** Id do campo de busca da árvore (associado ao label do form). */
		id?: string;
	}

	let { options, value, onChange, disabled = false, id }: Props = $props();

	const papelOptions: SelectMenuOption[] = PAPEL_OPTIONS.map((p) => ({
		value: p.value,
		label: p.label
	}));

	const optionById = $derived(new Map(options.map((o) => [o.id, o])));
	const selectedIds = $derived(value.map((v) => v.orgao_id));

	const tree = $derived.by(() =>
		buildOrgaoTree(options.map((o) => ({ value: o.id, pai_id: o.pai_id })))
	);
	// Ancestral vinculado mais próximo de cada área: alimenta o badge da linha e
	// o aviso do max().
	const coveringById = $derived.by(() => computeCoveringAncestors(tree, new Set(selectedIds)));

	const descendentes = $derived(value.filter((v) => coveringById.get(v.orgao_id) != null));

	function siglaOf(orgaoId: number | null | undefined): string {
		if (orgaoId == null) return '';
		return optionById.get(orgaoId)?.sigla ?? `#${orgaoId}`;
	}

	const textoDescendencias = $derived.by(() =>
		descendentes
			.map((v) => `${siglaOf(v.orgao_id)} está dentro de ${siglaOf(coveringById.get(v.orgao_id))}`)
			.join('; ')
	);

	function handleSelecaoChange(nextIds: number[]): void {
		onChange(mergeVinculosComSelecao(value, nextIds));
	}

	function handlePapelChange(orgaoId: number, papel: string | null): void {
		onChange(setVinculoPapel(value, orgaoId, normalizePapel(papel)));
	}

	function removeVinculo(orgaoId: number): void {
		if (disabled) return;
		onChange(value.filter((v) => v.orgao_id !== orgaoId));
	}
</script>

{#if value.length === 0}
	<p
		class="rounded-lg border border-dashed border-border-subtle bg-surface-muted px-3 py-3 text-sm text-text-muted"
	>
		Nenhuma área vinculada. Selecione as áreas na árvore abaixo.
	</p>
{:else}
	<ul class="flex flex-col gap-1.5">
		{#each value as vinculo (vinculo.orgao_id)}
			{@const orgao = optionById.get(vinculo.orgao_id)}
			{@const coveredBy = coveringById.get(vinculo.orgao_id) ?? null}
			<li
				class="flex flex-wrap items-center gap-2 rounded-lg border border-border-subtle bg-surface-muted px-3 py-2"
			>
				<span class="flex min-w-0 flex-1 basis-48 flex-col">
					<span class="truncate">
						<span class="text-sm font-semibold text-text-primary">
							{orgao?.sigla ?? `#${vinculo.orgao_id}`}
						</span>
						{#if orgao?.nome && orgao.nome !== orgao.sigla}
							<span class="text-xs text-text-secondary"> — {orgao.nome}</span>
						{/if}
					</span>
					{#if coveredBy != null}
						<span class="text-xs font-semibold uppercase tracking-caps text-warning">
							dentro de {siglaOf(coveredBy)}
						</span>
					{/if}
				</span>

				<div class="w-32 shrink-0">
					<SelectMenu
						options={papelOptions}
						value={vinculo.papel}
						onSelect={(papel) => handlePapelChange(vinculo.orgao_id, papel)}
						{disabled}
						size="sm"
						ariaLabel={`Papel em ${siglaOf(vinculo.orgao_id)}`}
					/>
				</div>

				<button
					type="button"
					onclick={() => removeVinculo(vinculo.orgao_id)}
					{disabled}
					aria-label={`Remover vínculo com ${siglaOf(vinculo.orgao_id)}`}
					class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-wash-danger hover:text-danger focus:outline-none focus-visible:ring-2 focus-visible:ring-danger disabled:opacity-50"
				>
					<i class="fas fa-times text-xs" aria-hidden="true"></i>
				</button>
			</li>
		{/each}
	</ul>
{/if}

{#if descendentes.length > 0}
	<p
		role="status"
		class="flex items-start gap-2 rounded-lg border border-warning-soft bg-wash-warning px-3 py-2 text-xs text-text-secondary"
	>
		<i class="fas fa-circle-info mt-0.5 shrink-0 text-warning" aria-hidden="true"></i>
		<span>{textoDescendencias}. Vale o papel mais alto entre os dois.</span>
	</p>
{/if}

<p class="text-xs text-text-muted">
	O acesso a uma área é sempre o papel mais alto entre os vínculos que a alcançam: não é possível
	rebaixar o papel dentro de um sub-órgão. Para dar menos acesso em parte da estrutura, vincule as
	áreas irmãs em vez do órgão-pai.
</p>

<OrgaoTreeMultiSelect
	{options}
	value={selectedIds}
	onChange={handleSelecaoChange}
	{disabled}
	{id}
	ariaLabel="Órgãos responsáveis"
/>
