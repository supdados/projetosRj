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

/**
 * Menção resolvida pelo servidor. `start`/`length` vêm em unidades UTF-16 — a
 * mesma unidade de `String.slice` — justamente para que um emoji antes da
 * menção (2 unidades, 1 code point em Python) não desloque o realce.
 */
export interface MentionSpan {
	start: number;
	length: number;
}

function escapeRegExp(value: string): string {
	return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Segmentos a partir das menções RESOLVIDAS pelo servidor (`comment.mentions`).
 *
 * É o caminho exato: o backend gravou `start`/`length` na escrita, contra a
 * lista real de pessoas do projeto, então nomes compostos ("@Ana Luiza
 * Ribeiro") são destacados por inteiro sem nenhuma adivinhação no cliente.
 * Intervalos fora do texto ou sobrepostos são descartados — defesa contra dado
 * inconsistente, não regra de negócio.
 */
export function segmentsFromMentions(
	text: string,
	mentions: readonly MentionSpan[]
): CommentSegment[] {
	const content = text ?? '';
	const ordered = [...mentions]
		.filter((m) => Number.isInteger(m.start) && m.length > 0 && m.start >= 0)
		.sort((a, b) => a.start - b.start);

	const segments: CommentSegment[] = [];
	let cursor = 0;
	for (const mention of ordered) {
		const end = mention.start + mention.length;
		if (mention.start < cursor || end > content.length) continue;
		if (mention.start > cursor) {
			segments.push({ text: content.slice(cursor, mention.start), isMention: false });
		}
		segments.push({ text: content.slice(mention.start, end), isMention: true });
		cursor = end;
	}
	if (cursor < content.length) segments.push({ text: content.slice(cursor), isMention: false });
	return segments;
}

/**
 * Quebra o texto em segmentos, marcando menções `@...` para destaque visual.
 *
 * LEGADO: só para comentários gravados ANTES de `comment.mentions` existir
 * (`mentions === null`). Quando `knownNames` é fornecido, casa nomes COM
 * espaços preferindo o mais longo; caso contrário, cai no padrão de uma palavra
 * `@\w+` — que é justamente o que destacava só o primeiro nome.
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
