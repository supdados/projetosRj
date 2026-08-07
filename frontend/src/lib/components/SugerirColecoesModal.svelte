<script lang="ts">
	/**
	 * Modal "Sugerir coleções com IA" (`docs/plano-ia-fase2-cache-sugestoes.md`
	 * §4): abrir dispara `GET /api/colecoes/sugestoes`, que é INSTANTÂNEO e
	 * nunca chama o modelo. Três estados de entrada:
	 *   - lote em cache → lista direto, com chip "gerado há X";
	 *   - lote em cache + `desatualizado` → mesma lista mais um aviso
	 *     não-bloqueante; as sugestões antigas continuam aceitáveis;
	 *   - sem lote → CTA "Gerar sugestões", único caminho para o POST de ~1min.
	 *
	 * Nada é gravado como coleção aqui: "Criar coleção" devolve a sugestão ao
	 * chamador, que abre o `NovaColecaoModal` pré-preenchido e confirma pelo
	 * fluxo normal (levando o `sugestao_id`). "Descartar" persiste — o
	 * agrupamento não volta em gerações futuras — e some com o cartão na hora;
	 * 404 significa que outra aba já regenerou, o que é sucesso.
	 *
	 * Os títulos dos chips vêm na própria resposta (`projetos`: todos os
	 * analisados — id ausente vira "Projeto #id"). Chrome (backdrop/Esc/
	 * focus-trap) é o `Modal` base; 503 fecha o modal e avisa o chamador para
	 * esconder a entrada da feature.
	 */
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import { ApiClientError } from '$lib/api/client';
	import {
		descartarSugestao,
		getSugestoes,
		isSugestoesIndisponivel,
		sugerirColecoes
	} from '$lib/api/collections';
	import type { ColecaoSugerida, SugestoesResponse } from '$lib/types/collections';

	interface Props {
		/** Modal aberto? (controlado pela página; abrir só lê o cache). */
		open: boolean;
		/** Fecha o modal (✕, Esc, backdrop, "Fechar") e aborta a chamada em voo. */
		onClose: () => void;
		/** Sugestão aceita: a página abre o modal de criação pré-preenchido. */
		onCriar: (sugestao: ColecaoSugerida) => void;
		/** Feature desligada no servidor (503) — a página esconde o botão. */
		onIndisponivel: () => void;
	}

	let { open, onClose, onCriar, onIndisponivel }: Props = $props();

	type Estado = 'carregando' | 'vazio' | 'pronto' | 'gerando' | 'erro';

	/** Cartão na tela: a sugestão + uma chave estável para o `{#each}` (descarte). */
	interface SugestaoCartao {
		chave: string;
		sugestao: ColecaoSugerida;
	}

	let estado = $state<Estado>('carregando');
	let cartoes = $state<SugestaoCartao[]>([]);
	let titulos = $state<Map<number, string>>(new Map());
	let projetosAbertos = $state<Set<string>>(new Set());
	let geradoEm = $state<string | null>(null);
	let desatualizado = $state(false);
	let erro = $state('');
	let erroDescarte = $state('');
	/** Qual chamada falhou — "Tentar novamente" repete a mesma, não a outra. */
	let acaoFalha = $state<'carregar' | 'gerar'>('carregar');
	let inFlight: AbortController | null = null;

	const textoGerando = 'Analisando todos os seus projetos… isso pode levar até 2 minutos';

	function tituloDe(projectId: number): string {
		return titulos.get(projectId) ?? `Projeto #${projectId}`;
	}

	/** Tempo relativo em pt-BR ("há 2 dias") — o front não tem helper próprio. */
	function tempoRelativo(iso: string): string {
		const minutos = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
		if (minutos < 1) return 'agora mesmo';
		if (minutos < 60) return `há ${minutos} ${minutos === 1 ? 'minuto' : 'minutos'}`;
		const horas = Math.floor(minutos / 60);
		if (horas < 24) return `há ${horas} ${horas === 1 ? 'hora' : 'horas'}`;
		const dias = Math.floor(horas / 24);
		return `há ${dias} ${dias === 1 ? 'dia' : 'dias'}`;
	}

	function aplicar(data: SugestoesResponse): void {
		titulos = new Map(data.projetos.map((p) => [p.id, p.titulo]));
		cartoes = data.sugestoes.map((sugestao) => ({ chave: String(sugestao.id), sugestao }));
		projetosAbertos = new Set();
		geradoEm = data.gerado_em;
		desatualizado = data.desatualizado;
		erroDescarte = '';
		estado = data.gerado_em === null && data.sugestoes.length === 0 ? 'vazio' : 'pronto';
	}

	function tratarFalha(err: unknown): void {
		if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
		if (isSugestoesIndisponivel(err)) {
			onIndisponivel();
			onClose();
			return;
		}
		erro = err instanceof Error ? err.message : 'Falha ao falar com o modelo.';
		estado = 'erro';
	}

	function novaChamada(): AbortController {
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		return controller;
	}

	/** Lê o lote em cache: barato, sem modelo — é o que a abertura dispara. */
	async function carregar(): Promise<void> {
		const controller = novaChamada();
		estado = 'carregando';
		erro = '';
		try {
			aplicar(await getSugestoes(controller.signal));
		} catch (err) {
			if (controller.signal.aborted) return;
			acaoFalha = 'carregar';
			tratarFalha(err);
		}
	}

	/** Chamada cara ao modelo — só em clique explícito do usuário. */
	async function gerar(): Promise<void> {
		const controller = novaChamada();
		estado = 'gerando';
		erro = '';
		try {
			aplicar(await sugerirColecoes(controller.signal));
		} catch (err) {
			if (controller.signal.aborted) return;
			acaoFalha = 'gerar';
			tratarFalha(err);
		}
	}

	function tentarNovamente(): void {
		if (acaoFalha === 'gerar') {
			void gerar();
			return;
		}
		void carregar();
	}

	async function descartar(cartao: SugestaoCartao): Promise<void> {
		const indice = cartoes.indexOf(cartao);
		cartoes = cartoes.filter((c) => c.chave !== cartao.chave);
		erroDescarte = '';
		try {
			await descartarSugestao(cartao.sugestao.id);
		} catch (err) {
			// 404 = outra aba já regenerou o lote: o cartão sumir é o resultado certo.
			if (err instanceof ApiClientError && err.status === 404) return;
			cartoes = [...cartoes.slice(0, indice), cartao, ...cartoes.slice(indice)];
			erroDescarte = `Não foi possível descartar "${cartao.sugestao.nome}".`;
		}
	}

	function alternarProjetos(chave: string): void {
		const proximo = new Set(projetosAbertos);
		if (!proximo.delete(chave)) proximo.add(chave);
		projetosAbertos = proximo;
	}

	function fechar(): void {
		inFlight?.abort();
		onClose();
	}

	let prevOpen = false;
	$effect(() => {
		if (open && !prevOpen) void carregar();
		prevOpen = open;
	});
</script>

{#if open}
	<Modal labelId="sugerir-colecoes-title" maxWidth="max-w-[640px]" onBackdrop={fechar}>
		<div class="flex max-h-[80vh] flex-col gap-4">
			<div class="flex items-center gap-3">
				<h2 id="sugerir-colecoes-title" class="font-heading text-xl font-bold text-text-primary">
					Sugestões de coleções
				</h2>
				<span
					class="rounded-sm bg-wash-brand px-2 py-0.5 text-2xs font-semibold uppercase tracking-caps text-brand"
				>
					Gerado por IA
				</span>
				{#if geradoEm && estado === 'pronto'}
					<span class="truncate text-2xs text-text-muted">{tempoRelativo(geradoEm)}</span>
				{/if}
				<button
					type="button"
					onclick={fechar}
					aria-label="Fechar"
					class="ml-auto grid h-8 w-8 place-items-center rounded-md text-icon-faint transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<svg
						viewBox="0 0 20 20"
						class="h-4 w-4"
						fill="none"
						stroke="currentColor"
						stroke-width="1.6"
						aria-hidden="true"
					>
						<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
					</svg>
				</button>
			</div>

			<p class="text-sm text-text-secondary">
				Rascunhos a partir dos seus projetos — nada é criado sem a sua confirmação.
			</p>

			{#if estado === 'carregando' || estado === 'gerando'}
				<div class="flex flex-col items-center gap-3 py-10" role="status" aria-live="polite">
					<span
						class="h-6 w-6 animate-spin rounded-full border-2 border-border-subtle border-t-primary-600"
						aria-hidden="true"
					></span>
					<p class="text-sm text-text-secondary">
						{estado === 'gerando' ? textoGerando : 'Carregando sugestões…'}
					</p>
				</div>
			{:else if estado === 'erro'}
				<div class="flex flex-col gap-3">
					<StateBanner
						tone="danger"
						title="Não foi possível gerar as sugestões."
						description={erro}
					/>
					<div class="flex justify-center">
						<Button variant="secondary" size="sm" onclick={tentarNovamente}>
							Tentar novamente
						</Button>
					</div>
				</div>
			{:else if estado === 'vazio'}
				<div class="flex flex-col items-center gap-3 py-10 text-center">
					<p class="max-w-[26rem] text-sm text-text-muted">
						A IA ainda não analisou os seus projetos. A análise leva até 2 minutos e o resultado
						fica guardado para as próximas visitas.
					</p>
					<Button onclick={() => void gerar()}>Gerar sugestões</Button>
				</div>
			{:else}
				{#if desatualizado}
					<StateBanner
						tone="warning"
						title="Seus projetos mudaram desde esta análise"
						description="As sugestões abaixo continuam válidas — aceite as que servirem ou peça uma análise nova."
						actionLabel="Gerar novamente"
						onAction={() => void gerar()}
					/>
				{/if}

				{#if erroDescarte}
					<StateBanner tone="danger" title={erroDescarte} />
				{/if}

				{#if cartoes.length === 0}
					<p class="py-10 text-center text-sm text-text-muted">
						Nenhuma sugestão para revisar agora.
					</p>
				{:else}
					<ul class="thin-scroll flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
						{#each cartoes as cartao (cartao.chave)}
							<li class="flex flex-col gap-2.5 rounded-control border border-border-subtle p-3.5">
								<div class="flex min-w-0 flex-col">
									<h3 class="truncate text-md font-semibold text-text-primary">
										{cartao.sugestao.nome}
									</h3>
									{#if cartao.sugestao.descricao}
										<p class="truncate text-sm text-text-secondary">{cartao.sugestao.descricao}</p>
									{/if}
								</div>

								<p class="rounded-control bg-wash-brand px-3 py-2 text-sm text-text-secondary">
									{cartao.sugestao.justificativa}
								</p>

								<button
									type="button"
									onclick={() => alternarProjetos(cartao.chave)}
									aria-expanded={projetosAbertos.has(cartao.chave)}
									class="flex w-fit items-center gap-1.5 rounded-sm text-xs font-medium text-text-secondary transition-colors duration-fast hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
								>
									<svg
										viewBox="0 0 20 20"
										class="h-3.5 w-3.5"
										fill="none"
										stroke="currentColor"
										stroke-width="1.6"
										aria-hidden="true"
									>
										<circle cx="10" cy="10" r="7.5" />
										<path d="M10 9v4.5M10 6.6v.1" stroke-linecap="round" />
									</svg>
									{cartao.sugestao.project_ids.length} projetos
									<span class="text-2xs text-text-muted">
										{projetosAbertos.has(cartao.chave) ? 'ocultar' : 'ver quais'}
									</span>
								</button>

								{#if projetosAbertos.has(cartao.chave)}
									<ul
										class="thin-scroll max-h-40 overflow-y-auto rounded-control border border-border-subtle bg-surface-muted px-3 py-2"
										aria-label="Projetos da sugestão"
									>
										{#each cartao.sugestao.project_ids as projectId (projectId)}
											<li class="truncate py-0.5 text-xs text-text-secondary">
												{tituloDe(projectId)}
											</li>
										{/each}
									</ul>
								{/if}

								<div class="flex justify-end gap-2">
									<Button variant="secondary" size="sm" onclick={() => void descartar(cartao)}>
										Descartar
									</Button>
									<Button size="sm" onclick={() => onCriar(cartao.sugestao)}>Criar coleção</Button>
								</div>
							</li>
						{/each}
					</ul>
				{/if}
			{/if}

			<footer class="flex items-center justify-end gap-2 border-t border-border-hairline pt-4">
				{#if estado === 'pronto' && !desatualizado}
					<!-- Análise fresca: regerar é possível, mas discreto (custa ~1min de modelo). -->
					<div class="mr-auto">
						<Button variant="ghost" size="sm" onclick={() => void gerar()}>Gerar novamente</Button>
					</div>
				{/if}
				<Button variant="secondary" onclick={fechar}>Fechar</Button>
			</footer>
		</div>
	</Modal>
{/if}
