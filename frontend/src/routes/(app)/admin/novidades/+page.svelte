<script lang="ts">
	/**
	 * Admin › Novidades: os onboardings do produto, um por linha — alcance
	 * ("N de M pessoas viram · K até o fim"), liga/desliga, pré-visualizar (sem
	 * contar como vista) e "Mostrar de novo" (apaga as vistas: volta a abrir
	 * sozinho para todos).
	 *
	 * Criar novidade não é daqui: o conteúdo é código (`lib/novidades/conteudo.ts`)
	 * e a linha nasce numa migração. Linha sem conteúdo nesta versão do front
	 * aparece marcada e sem pré-visualização.
	 */
	import { onMount } from 'svelte';
	import { ApiClientError } from '$lib/api/client';
	import {
		definirNovidadeAtiva,
		fetchNovidadesAdmin,
		mostrarNovidadeDeNovo
	} from '$lib/api/novidades';
	import Button from '$lib/components/Button.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import { temConteudoNovidade } from '$lib/novidades/conteudo';
	import { confirmAction } from '$lib/stores/confirm';
	import { flash } from '$lib/stores/flash';
	import { novidades as novidadesSessao } from '$lib/stores/novidades';
	import type { NovidadeAdmin, NovidadesAdminData } from '$lib/types/novidades';
	import { accessErrorKind, type AccessErrorKind } from '$lib/utils/accessErrorMessages';

	let dados = $state<NovidadesAdminData | null>(null);
	let estado = $state<'loading' | 'ready' | 'error'>('loading');
	let erro = $state('');
	let erroKind = $state<AccessErrorKind>('generic');
	let ocupado = $state<string | null>(null);

	const DATA = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'medium' });

	async function carregar(): Promise<void> {
		estado = dados ? estado : 'loading';
		try {
			dados = await fetchNovidadesAdmin();
			estado = 'ready';
		} catch (err) {
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			erroKind = accessErrorKind(err);
			erro =
				erroKind === 'forbidden'
					? 'Só administradores gerenciam as novidades.'
					: err instanceof Error
						? err.message
						: 'Não foi possível carregar as novidades.';
			estado = 'error';
		}
	}

	onMount(() => {
		void carregar();
	});

	function alcance(item: NovidadeAdmin, total: number): string {
		const pessoas = total === 1 ? 'pessoa' : 'pessoas';
		return `${item.vistas} de ${total} ${pessoas} viram · ${item.concluidas} até o fim`;
	}

	function percentual(item: NovidadeAdmin, total: number): number {
		return total > 0 ? Math.min(100, Math.round((item.vistas / total) * 100)) : 0;
	}

	async function alternar(item: NovidadeAdmin): Promise<void> {
		ocupado = item.slug;
		try {
			await definirNovidadeAtiva(item.slug, !item.ativa);
			flash.success(item.ativa ? `"${item.titulo}" desligada.` : `"${item.titulo}" ligada.`);
			await Promise.all([carregar(), novidadesSessao.carregar()]);
		} catch (err) {
			flash.danger(err instanceof Error ? err.message : 'Não foi possível alterar a novidade.');
		} finally {
			ocupado = null;
		}
	}

	async function mostrarDeNovo(item: NovidadeAdmin): Promise<void> {
		const confirmado = await confirmAction({
			title: `Mostrar "${item.titulo}" de novo?`,
			description: `Ela volta a abrir sozinha para as ${item.vistas} pessoas que já viram, na próxima vez que entrarem.`,
			confirmLabel: 'Mostrar de novo',
			tone: 'warning'
		});
		if (!confirmado) return;
		ocupado = item.slug;
		try {
			const removidas = await mostrarNovidadeDeNovo(item.slug);
			flash.success(`"${item.titulo}" vai aparecer de novo para ${removidas} pessoas.`);
			await Promise.all([carregar(), novidadesSessao.carregar()]);
		} catch (err) {
			flash.danger(err instanceof Error ? err.message : 'Não foi possível reiniciar a novidade.');
		} finally {
			ocupado = null;
		}
	}
</script>

<svelte:head>
	<title>ProjetosRJ — Novidades</title>
</svelte:head>

<section aria-labelledby="novidades-admin-title" class="flex flex-col gap-4">
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
		<PageHeader compact embedded class="min-h-[3.5rem]" labelId="novidades-admin-title">
			{#snippet titleContent()}
				<span>Novidades</span>
				{#if dados}
					<CountBadge class="ml-2">
						{dados.novidades.length}
						{dados.novidades.length === 1 ? 'novidade' : 'novidades'}
					</CountBadge>
				{/if}
			{/snippet}
		</PageHeader>
		<p
			class="m-0 flex min-h-[calc(var(--control-h-md)+1.25rem)] items-center border-t border-border-subtle px-4 py-2.5 text-sm text-text-secondary"
		>
			Cada novidade abre sozinha uma vez para cada pessoa, na primeira tela depois do login.
		</p>
	</div>

	{#if estado === 'loading'}
		<div class="flex flex-col gap-3" aria-busy="true">
			{#each [0, 1] as i (i)}
				<Skeleton class="h-[92px] w-full rounded-xl" />
			{/each}
		</div>
	{:else if estado === 'error'}
		<LoadErrorState message={erro} kind={erroKind} onRetry={() => void carregar()} />
	{:else if dados && dados.novidades.length === 0}
		<p class="m-0 rounded-xl border border-border-subtle bg-surface px-6 py-10 text-center text-text-secondary">
			Nenhuma novidade cadastrada.
		</p>
	{:else if dados}
		<ul class="m-0 flex list-none flex-col gap-3 p-0">
			{#each dados.novidades as item (item.slug)}
				{@const comConteudo = temConteudoNovidade(item.slug)}
				<li
					class="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border border-border-subtle bg-surface px-5 py-4 shadow-sm"
				>
					<div class="flex min-w-[14rem] flex-1 flex-col gap-1">
						<div class="flex flex-wrap items-center gap-2">
							<span class="text-md font-bold text-text-primary">{item.titulo}</span>
							{#if !comConteudo}
								<span class="rounded-md bg-warning-100 px-2 py-0.5 text-2xs font-bold text-warning-700">
									Sem conteúdo nesta versão
								</span>
							{/if}
						</div>
						<span class="font-mono text-2xs text-text-muted">
							{item.slug} · publicada em {DATA.format(new Date(item.publicada_em))}
						</span>
					</div>

					<div class="flex min-w-[14rem] flex-1 flex-col gap-1.5">
						<span class="text-sm text-text-secondary">{alcance(item, dados.usuarios_ativos)}</span>
						<div class="h-1.5 overflow-hidden rounded-full bg-progress-track" aria-hidden="true">
							<div
								class="h-full rounded-full bg-primary-600"
								style:width="{percentual(item, dados.usuarios_ativos)}%"
							></div>
						</div>
					</div>

					<div class="flex flex-wrap items-center gap-2">
						<button
							type="button"
							role="switch"
							aria-checked={item.ativa}
							aria-label={`${item.titulo}: ${item.ativa ? 'ligada' : 'desligada'}`}
							disabled={ocupado === item.slug}
							onclick={() => void alternar(item)}
							class="inline-flex h-[var(--control-h-md)] items-center gap-2.5 rounded-control border border-border-subtle px-3 text-sm font-semibold text-text-primary transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
						>
							<span
								class="relative h-5 w-9 rounded-full transition-colors duration-fast {item.ativa
									? 'bg-primary-600'
									: 'bg-neutral-300'}"
								aria-hidden="true"
							>
								<span
									class="absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-[left] duration-fast {item.ativa
										? 'left-[18px]'
										: 'left-0.5'}"
								></span>
							</span>
							{item.ativa ? 'Ligada' : 'Desligada'}
						</button>
						{#if comConteudo}
							<Button variant="secondary" size="sm" onclick={() => novidadesSessao.abrir(item.slug, true)}>
								Pré-visualizar
							</Button>
						{/if}
						<Button
							variant="ghost"
							size="sm"
							disabled={ocupado === item.slug || item.vistas === 0}
							onclick={() => void mostrarDeNovo(item)}
						>
							Mostrar de novo
						</Button>
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</section>
