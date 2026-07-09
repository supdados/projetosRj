/**
 * Rótulos, tons semânticos e cor da barra de status das tarefas — fonte única
 * reusada pela lista (modo lista do hub) e pelos chips. Espelha os
 * `status_labels`/`prioridade_labels`/`tipo_labels` do hub Jinja.
 *
 * As cores usam os tokens do design system (--ds-color-*), via classes Tailwind
 * (`success`/`warning`/`danger`/`info`/`primary`), então trocam sozinhas no dark
 * mode — não há hex hardcoded por tema aqui.
 */

/** Tons do `Badge` (= união aceita por `Badge.svelte`). */
export type BadgeTone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

const STATUS_LABEL: Record<string, string> = {
	nao_iniciada: 'Não iniciada',
	em_andamento: 'Em andamento',
	para_validacao: 'Para validação',
	para_ajustes: 'Para ajustes',
	finalizada: 'Finalizada'
};

const STATUS_TONE: Record<string, BadgeTone> = {
	nao_iniciada: 'neutral',
	em_andamento: 'info',
	para_validacao: 'primary',
	para_ajustes: 'warning',
	finalizada: 'success'
};

/** Classe de fundo da barra/realce vertical da linha, por status (tokens DS). */
const STATUS_BAR_CLASS: Record<string, string> = {
	nao_iniciada: 'bg-text-muted',
	em_andamento: 'bg-info',
	para_validacao: 'bg-primary-500',
	para_ajustes: 'bg-warning',
	finalizada: 'bg-success'
};

const PRIORIDADE_LABEL: Record<string, string> = {
	baixa: 'Baixa',
	media: 'Média',
	alta: 'Alta',
	urgente: 'Urgente'
};

const PRIORIDADE_TONE: Record<string, BadgeTone> = {
	baixa: 'neutral',
	media: 'info',
	alta: 'warning',
	urgente: 'danger'
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

export function prioridadeTone(value: string | null): BadgeTone {
	if (!value) return 'neutral';
	return PRIORIDADE_TONE[value] ?? 'neutral';
}

export function tipoLabel(value: string | null): string | null {
	if (!value) return null;
	return TIPO_LABEL[value] ?? value;
}

/**
 * Chip padronizado (prioridade/tipo/status): TODOS com o mesmo formato — radius
 * 5px, mesma fonte/padding/peso — variando só a cor por tom. Fundo suave + texto
 * + borda do mesmo tom (tokens DS, dark-safe).
 */
export const CHIP_BASE =
	'inline-flex h-7 items-center justify-center whitespace-nowrap rounded-md border px-2 py-1 text-[11px] font-semibold uppercase leading-none tracking-wide';

const CHIP_TONE: Record<BadgeTone, string> = {
	neutral: 'border-border-subtle bg-surface-muted text-text-secondary dark:border-white/10',
	primary: 'border-primary-500/30 bg-primary-100 text-primary-700 dark:border-white/10',
	info: 'border-info/30 bg-info/10 text-info dark:border-white/10',
	warning: 'border-warning/40 bg-warning/10 text-warning dark:border-white/10',
	success: 'border-success/40 bg-success/10 text-success dark:border-white/10',
	danger: 'border-danger/40 bg-danger/10 text-danger dark:border-white/10'
};

/** Classes completas do chip para um tom (base + cores). */
export function chipClass(tone: BadgeTone): string {
	return `${CHIP_BASE} ${CHIP_TONE[tone]}`;
}
