/**
 * Máscara do número de processo SEI-RJ (formato canônico
 * "SEI-000000/000000/0000"). O prefixo "SEI-" NÃO faz parte do valor
 * mascarado: fica fixo na UI, e `seiDigitsOnly` descarta qualquer prefixo
 * colado junto do número ("SEI-380001/000664/2026" → só os dígitos).
 */

const SEI_MAX_DIGITS = 16;

/** Extrai só os dígitos — colar o número com "SEI-" não é erro, é normalizado. */
export function seiDigitsOnly(value: string): string {
	return value.replace(/[^0-9]/g, '').slice(0, SEI_MAX_DIGITS);
}

/** Agrupa os dígitos em 6/6/4 conforme o usuário digita ("3800010" → "380001/0"). */
export function formatSeiDigits(digits: string): string {
	const clean = seiDigitsOnly(digits);
	if (clean.length <= 6) return clean;
	if (clean.length <= 12) return `${clean.substring(0, 6)}/${clean.substring(6)}`;
	return `${clean.substring(0, 6)}/${clean.substring(6, 12)}/${clean.substring(12)}`;
}

/**
 * Mínimo aceito para persistir um número (primeiro grupo completo, 6 dígitos).
 * Regra ÚNICA dos dois caminhos de escrita (modal de criação e campo inline) —
 * fragmentos menores seriam ruído indistinguível de erro de digitação.
 */
export function hasMinimumSeiDigits(digits: string): boolean {
	return seiDigitsOnly(digits).length >= 6;
}
