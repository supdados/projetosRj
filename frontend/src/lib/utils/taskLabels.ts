/**
 * Rótulos, tons semânticos e cor da barra de status das tarefas — fonte única
 * reusada pela lista (modo lista do hub) e pelos chips. Espelha os
 * `status_labels`/`prioridade_labels`/`tipo_labels` do hub Jinja.
 *
 * As cores usam os tokens do design system (--ds-color-*): status, tipo e
 * prioridade viram pílula `.chip` (app.css); o ponto sólido de prioridade
 * sobrevive nos dots dos menus. Tudo troca sozinho no dark mode, sem hex
 * hardcoded por tema aqui.
 */

/** Tons do `Badge` (= união aceita por `Badge.svelte`). */
export type BadgeTone = 'neutral' | 'primary' | 'success' | 'warning' | 'orange' | 'danger' | 'info';

const STATUS_LABEL: Record<string, string> = {
	nao_iniciada: 'Não iniciada',
	em_andamento: 'Em andamento',
	para_validacao: 'Para validação',
	para_ajustes: 'Para ajustes',
	finalizada: 'Finalizada'
};

/* Mapeamento status→tom arbitrado pelo design (plano-regua-de-cor §7.2):
   andamento=primary, validação=warning (bola com outro), ajustes=orange→attention
   (retrabalho, não risco), finalizada=success. Danger sai do fluxo de status. */
const STATUS_TONE: Record<string, BadgeTone> = {
	nao_iniciada: 'neutral',
	em_andamento: 'primary',
	para_validacao: 'warning',
	para_ajustes: 'orange',
	finalizada: 'success'
};

/** Classe de fundo da barra/realce vertical da linha, por status (tokens DS). */
const STATUS_BAR_CLASS: Record<string, string> = {
	nao_iniciada: 'bg-text-muted',
	em_andamento: 'bg-brand',
	para_validacao: 'bg-warning',
	para_ajustes: 'bg-attention',
	finalizada: 'bg-success'
};

const PRIORIDADE_LABEL: Record<string, string> = {
	baixa: 'Baixa',
	media: 'Média',
	alta: 'Alta',
	urgente: 'Urgente'
};

/* Ponto sólido de prioridade — hoje só nos dots dos menus (SelectMenu) e nos
   rodapés do kanban; a célula da lista usa `prioridadeChipClass`. */
const PRIORIDADE_DOT_VAR: Record<string, string> = {
	baixa: 'var(--ds-color-priority-baixa)',
	media: 'var(--ds-color-priority-media)',
	alta: 'var(--ds-color-priority-alta)',
	urgente: 'var(--ds-color-priority-urgente)'
};

const TIPO_LABEL: Record<string, string> = {
	bug: 'Bug',
	melhoria: 'Melhoria',
	duvida: 'Dúvida',
	outros: 'Outros',
	implementacao: 'Implementação'
};

export function statusLabel(value: string): string {
	return STATUS_LABEL[value] ?? value;
}

export function statusTone(value: string): BadgeTone {
	return STATUS_TONE[value] ?? 'neutral';
}

/** Classe Tailwind de fundo da barra de status (cinza neutro como fallback). */
export function statusBarClass(value: string): string {
	return STATUS_BAR_CLASS[value] ?? 'bg-text-muted';
}

export function prioridadeLabel(value: string | null): string | null {
	if (!value) return null;
	return PRIORIDADE_LABEL[value] ?? value;
}

/** Cor CSS do ponto sólido de prioridade (dot do SelectMenu e dos rodapés). */
export function priorityDotColor(value: string | null | undefined): string | undefined {
	if (!value) return undefined;
	return PRIORIDADE_DOT_VAR[value];
}

export function tipoLabel(value: string | null): string | null {
	if (!value) return null;
	return TIPO_LABEL[value] ?? value;
}

/**
 * Chip canônico de status/tipo — receita única `.chip` do app.css
 * (plano-regua-de-cor §2.1/§7.9): 22px, raio 6px, 12px/500, sem uppercase.
 * Cada tom mapeia para uma família da régua; os estados (hover/pressed/
 * desabilitado/dark) vivem na própria classe, não aqui.
 */
export const CHIP_BASE = 'chip';

const CHIP_TONE: Record<BadgeTone, string> = {
	neutral: 'chip--neutral',
	primary: 'chip--brand',
	info: 'chip--brand',
	warning: 'chip--warning',
	orange: 'chip--attention',
	success: 'chip--success',
	danger: 'chip--danger'
};

/** Classes completas do chip para um tom (base + família). */
export function chipClass(tone: BadgeTone): string {
	return `${CHIP_BASE} ${CHIP_TONE[tone]}`;
}

const TIPO_CHIP_CLASS: Record<string, string> = {
	bug: 'chip chip--tipo-bug',
	melhoria: 'chip chip--tipo-melhoria',
	duvida: 'chip chip--tipo-duvida'
};

/** Chip do tipo na cor do ícone T-A; `outros`/sem valor caem no neutro. */
export function tipoChipClass(value: string | null): string {
	if (!value) return chipClass('neutral');
	return TIPO_CHIP_CLASS[value] ?? chipClass('neutral');
}

const PRIORIDADE_CHIP_CLASS: Record<string, string> = {
	baixa: 'chip chip--prio-baixa',
	media: 'chip chip--prio-media',
	alta: 'chip chip--prio-alta',
	urgente: 'chip chip--prio-urgente'
};

/** Chip de prioridade escalado pela escada danger; sem valor cai no neutro. */
export function prioridadeChipClass(value: string | null): string {
	if (!value) return chipClass('neutral');
	return PRIORIDADE_CHIP_CLASS[value] ?? chipClass('neutral');
}
