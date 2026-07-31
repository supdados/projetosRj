/**
 * Precondições de conclusão de etapa avaliadas no CLIENTE, com os mesmos textos
 * do backend. Evita a rajada de 422 idênticos quando o usuário clica repetidas
 * vezes no botão de concluir: sem requisição, não há erro para notificar.
 *
 * O servidor continua sendo a autoridade final — isto é UX, não garantia.
 *
 * ```ts
 * const { ok, motivo } = podeConcluirEtapa(etapa.task_count, etapa.data_inicio, etapa.data_fim);
 * if (!ok) mostrarErroNaLinha(motivo);
 * ```
 */

/** União discriminada: `ok: false` garante `motivo` preenchido no call site. */
export type EtapaPrecondicao = { ok: true; motivo: null } | { ok: false; motivo: string };

export const MOTIVO_DATAS_AUSENTES =
	'Defina as datas de início e de término da etapa antes de concluí-la.';

export const MOTIVO_RESPONSAVEL_AUSENTE =
	'Defina ao menos uma área responsável pela etapa antes de concluí-la.';

export function motivoTarefasPendentes(pendentes: number): string {
	return `Finalize as ${pendentes} tarefa(s) pendente(s) desta etapa antes de concluí-la.`;
}

/** Espelha `etapa_tem_responsavel` do backend: lista nova OU texto legado. */
export function etapaTemResponsavel(
	responsaveis: { area_id: number | null; label: string }[],
	responsavelLegado: string | null
): boolean {
	return responsaveis.length > 0 || (responsavelLegado ?? '').trim() !== '';
}

/**
 * Verifica se uma etapa iniciada pode ser concluída.
 *
 * Ordem de checagem estável (datas -> responsável -> tarefas), ESPELHADA em
 * `services/etapas_mutation.py::motivo_bloqueio_conclusao` — textos idênticos
 * para que o aviso local seja o mesmo do 422 do servidor. Etapas importadas de
 * modelo chegam sem responsável e não podem ser concluídas até ganharem um.
 */
export function podeConcluirEtapa(
	taskCount: { total: number; done: number },
	dataInicio: string | null,
	dataFim: string | null,
	temResponsavel: boolean
): EtapaPrecondicao {
	if (!dataInicio || !dataFim) return { ok: false, motivo: MOTIVO_DATAS_AUSENTES };
	if (!temResponsavel) return { ok: false, motivo: MOTIVO_RESPONSAVEL_AUSENTE };
	const pendentes = taskCount.total - taskCount.done;
	if (pendentes > 0) return { ok: false, motivo: motivoTarefasPendentes(pendentes) };
	return { ok: true, motivo: null };
}
