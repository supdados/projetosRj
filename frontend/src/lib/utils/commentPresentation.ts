/**
 * Helpers PUROS de apresentação de comentários (árvore inline do hub).
 * Iniciais espelham `AssigneeAvatar.computeInitials`; a cor do avatar vive em
 * `$lib/utils/avatarPalette` (paleta curada, fonte única).
 */

/** Iniciais a partir do nome (mesma regra de AssigneeAvatar.computeInitials). */
export function initialsFromName(value: string): string {
	const parts = (value || '').trim().split(/\s+/).filter(Boolean);
	if (parts.length === 0) return '?';
	if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
	return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Data curta "dd/mm/aa hh:mm" (PT). Vazio para ISO inválido/nulo. */
export function formatCommentDate(iso: string | null): string {
	if (!iso) return '';
	const parsed = new Date(iso);
	if (Number.isNaN(parsed.getTime())) return '';
	return parsed.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

/** Segmento de texto de comentário: trecho normal ou menção destacada. */
export interface CommentSegment {
	text: string;
	isMention: boolean;
}

function escapeRegExp(value: string): string {
	return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Quebra o texto em segmentos, marcando menções `@...` para destaque visual.
 *
 * Quando `knownNames` é fornecido (autocomplete), casa nomes COM espaços
 * (ex.: "@Maria Silva") preferindo o mais longo; caso contrário, cai no padrão
 * de uma palavra `@\w+`. É apenas cosmético — não notifica ninguém (o backend
 * já notifica todos que veem a tarefa).
 */
export function splitMentions(text: string, knownNames?: readonly string[]): CommentSegment[] {
	const names = (knownNames ?? [])
		.map((n) => n.trim())
		.filter(Boolean)
		.sort((a, b) => b.length - a.length);

	const pattern = names.length
		? new RegExp(`@(?:${names.map(escapeRegExp).join('|')}|\\w+)`, 'gi')
		: /@\w+/g;

	const segments: CommentSegment[] = [];
	let lastIndex = 0;
	for (const match of text.matchAll(pattern)) {
		const start = match.index ?? 0;
		if (start > lastIndex) segments.push({ text: text.slice(lastIndex, start), isMention: false });
		segments.push({ text: match[0], isMention: true });
		lastIndex = start + match[0].length;
	}
	if (lastIndex < text.length) segments.push({ text: text.slice(lastIndex), isMention: false });
	return segments;
}
