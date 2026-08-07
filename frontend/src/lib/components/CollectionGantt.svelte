<script lang="ts">
	/**
	 * Gantt do cronograma da coleção (tela 3c, seção "Cronograma das etapas").
	 *
	 * Janela FIXA de 7 meses ancorada no hoje (mês atual −2 até +4), sem toggle
	 * de escala (fica para a Fase 3). Cada projeto é uma linha de 52px; as
	 * barras são as etapas datadas (`CronogramaEtapa`), posicionadas por fração
	 * mês+dia para casarem com as gridlines de 1/7 mesmo com meses de 28–31
	 * dias. O estado da barra (`barra`) já chega decidido do backend — aqui só
	 * se pinta. Etapas fora da janela são clampadas na borda (ou omitidas se
	 * inteiramente fora); barra mínima de 6px garante etapas pontuais visíveis.
	 */
	import type { BarraEtapa, CronogramaEtapa, CronogramaProjeto } from '$lib/types/collections';

	const { projetos }: { projetos: CronogramaProjeto[] } = $props();

	const MESES_ANTES = 2;
	const COLUNAS = 7;

	const hoje = new Date();
	const inicioJanela = new Date(hoje.getFullYear(), hoje.getMonth() - MESES_ANTES, 1);

	const MES_CURTO = [
		'Jan',
		'Fev',
		'Mar',
		'Abr',
		'Mai',
		'Jun',
		'Jul',
		'Ago',
		'Set',
		'Out',
		'Nov',
		'Dez'
	];

	// Janeiro carrega o ano curto para desambiguar janelas que viram o ano.
	const colunasMes: string[] = Array.from({ length: COLUNAS }, (_, i) => {
		const mes = new Date(inicioJanela.getFullYear(), inicioJanela.getMonth() + i, 1);
		const rotulo = MES_CURTO[mes.getMonth()];
		return mes.getMonth() === 0 ? `${rotulo}/${String(mes.getFullYear()).slice(2)}` : rotulo;
	});

	const BARRA_CLASS: Record<BarraEtapa, string> = {
		concluida: 'bg-success-600 dark:bg-success-400',
		execucao: 'bg-brand',
		vencida: 'bg-fill-danger',
		prevista: 'bg-progress-track'
	};

	const BARRA_LABEL: Record<BarraEtapa, string> = {
		concluida: 'Concluída',
		execucao: 'Em execução',
		vencida: 'Vencida',
		prevista: 'Prevista'
	};

	const LEGENDA: BarraEtapa[] = ['concluida', 'execucao', 'vencida', 'prevista'];

	/** % da janela para um ISO YYYY-MM-DD; `new Date(iso)` interpretaria UTC e deslocaria o dia. */
	function pctNaJanela(iso: string, fimDoDia = false): number {
		const [ano, mes, dia] = iso.split('-').map(Number);
		const meses = (ano - inicioJanela.getFullYear()) * 12 + (mes - 1 - inicioJanela.getMonth());
		const diasNoMes = new Date(ano, mes, 0).getDate();
		return ((meses + (dia - (fimDoDia ? 0 : 1)) / diasNoMes) / COLUNAS) * 100;
	}

	const diasNoMesAtual = new Date(hoje.getFullYear(), hoje.getMonth() + 1, 0).getDate();
	const hojePct = ((MESES_ANTES + (hoje.getDate() - 1) / diasNoMesAtual) / COLUNAS) * 100;
	const hojeLeft = `calc(280px + (100% - 280px) * ${(hojePct / 100).toFixed(4)})`;

	function formatBr(iso: string): string {
		const [ano, mes, dia] = iso.split('-');
		return `${dia}/${mes}/${ano}`;
	}

	function tituloEtapa(etapa: CronogramaEtapa): string {
		const periodo =
			etapa.data_inicio && etapa.data_fim
				? `${formatBr(etapa.data_inicio)} a ${formatBr(etapa.data_fim)}`
				: formatBr((etapa.data_fim ?? etapa.data_inicio) as string);
		return `${etapa.nome} — ${periodo} (${BARRA_LABEL[etapa.barra]})`;
	}

	interface BarraRender {
		key: number;
		leftPct: number;
		widthPct: number;
		barra: BarraEtapa;
		title: string;
	}

	function barraDaEtapa(etapa: CronogramaEtapa): BarraRender | null {
		const inicioIso = etapa.data_inicio ?? etapa.data_fim;
		const fimIso = etapa.data_fim ?? etapa.data_inicio;
		if (!inicioIso || !fimIso) return null;
		const left = pctNaJanela(inicioIso);
		const right = pctNaJanela(fimIso, true);
		if (right < left) return null; // data_fim < data_inicio — etapa inconsistente, não desenha
		if (right < 0 || left > 100) return null;
		const leftClamped = Math.max(0, left);
		return {
			key: etapa.id,
			leftPct: leftClamped,
			widthPct: Math.max(Math.min(100, right) - leftClamped, 0),
			barra: etapa.barra,
			title: tituloEtapa(etapa)
		};
	}

	function barrasDoProjeto(projeto: CronogramaProjeto): BarraRender[] {
		return projeto.etapas
			.map(barraDaEtapa)
			.filter((barra): barra is BarraRender => barra !== null);
	}

	function resumoLinha(projeto: CronogramaProjeto): string {
		const datadas =
			projeto.etapas.length === 1 ? '1 etapa datada' : `${projeto.etapas.length} etapas datadas`;
		const semData = projeto.sem_data > 0 ? `, ${projeto.sem_data} sem data` : '';
		return `${projeto.nome}: ${datadas}${semData}`;
	}
</script>

<div class="flex flex-wrap items-center gap-3 border-b border-border-subtle px-5 py-4">
	<h2 class="m-0 text-base font-bold text-text-primary">Cronograma das etapas</h2>
	<span class="ml-auto flex flex-wrap items-center gap-3 text-xs text-text-muted">
		{#each LEGENDA as barra (barra)}
			<span class="flex items-center gap-1.5">
				<span class="h-2 w-3.5 rounded {BARRA_CLASS[barra]}" aria-hidden="true"></span>
				{BARRA_LABEL[barra]}
			</span>
		{/each}
	</span>
</div>

{#if projetos.length === 0}
	<p class="m-0 px-5 py-6 text-center text-sm text-text-muted">
		Nenhum projeto na coleção para montar o cronograma.
	</p>
{:else}
	<div class="px-5 pb-5 pt-3">
		<div class="grid grid-cols-[280px_1fr] pb-7 text-xs font-medium text-text-secondary">
			<div>Projeto</div>
			<div class="grid grid-cols-7 text-center">
				{#each colunasMes as rotulo (rotulo)}
					<span>{rotulo}</span>
				{/each}
			</div>
		</div>
		<div class="relative border-t border-border-subtle">
			<div
				class="absolute bottom-0 top-0 z-[2] w-0.5 rounded-full bg-brand"
				style:left={hojeLeft}
				aria-hidden="true"
			></div>
			<div
				class="absolute -top-6 z-[3] inline-flex h-5 -translate-x-1/2 items-center rounded-sm bg-brand px-2 text-2xs font-semibold text-on-brand"
				style:left={hojeLeft}
			>
				HOJE
			</div>
			{#each projetos as projeto (projeto.id)}
				<div
					class="grid h-[52px] grid-cols-[280px_1fr] items-center border-b border-border-subtle last:border-b-0"
				>
					<div class="min-w-0 pr-4">
						<div class="truncate text-sm font-medium text-text-primary">{projeto.nome}</div>
						<div class="truncate text-xs text-text-muted">
							<span class="font-mono">{projeto.id}</span>
							{#if projeto.orgao_sigla}
								<span> · {projeto.orgao_sigla}</span>
							{/if}
							{#if projeto.sem_data > 0}
								<span> · +{projeto.sem_data} sem data</span>
							{/if}
						</div>
					</div>
					<div
						class="relative h-full"
						style="background: repeating-linear-gradient(to right, var(--ds-color-border-base) 0 1px, transparent 1px calc(100% / 7))"
						role="img"
						aria-label={resumoLinha(projeto)}
					>
						{#each barrasDoProjeto(projeto) as barra (barra.key)}
							<div
								class="absolute top-1/2 h-3.5 -translate-y-1/2 rounded-sm {BARRA_CLASS[barra.barra]}"
								style:left={`min(${barra.leftPct.toFixed(3)}%, calc(100% - 6px))`}
								style:width={`max(${barra.widthPct.toFixed(3)}%, 6px)`}
								title={barra.title}
							></div>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	</div>
{/if}
