/**
 * Paleta curada dos avatares (não hue por hash): tons análogos ao azul da
 * marca + bronze. O quadrante verde/amarelo/laranja/vermelho fica de fora —
 * é semântico (prioridade/status, app.css:48-51) e um avatar nessas cores
 * leria como badge. Luminância 35–50%: texto branco legível nos dois temas.
 */
const AVATAR_PALETTE: readonly string[] = [
	'hsl(207 55% 38%)', // azul institucional (família do primary #005a92)
	'hsl(196 48% 37%)', // azul-petróleo
	'hsl(185 38% 35%)', // teal acinzentado
	'hsl(218 30% 47%)', // slate
	'hsl(232 28% 50%)', // índigo suave
	'hsl(260 22% 50%)', // violeta acinzentado
	'hsl(290 18% 46%)', // ameixa discreta
	'hsl(44 50% 36%)' // bronze (família da secundária #bc9d32)
];

/** Hash determinístico: mesma pessoa, mesma cor em todo o app. */
function avatarPaletteIndex(value: string): number {
	let hash = 0;
	const source = value || '?';
	for (let i = 0; i < source.length; i++) {
		hash = (hash * 31 + source.charCodeAt(i)) % 360;
	}
	return hash % AVATAR_PALETTE.length;
}

/** Cor de fundo do avatar para um nome. Ex.: avatarColorForName('Ana Souza'). */
export function avatarColorForName(value: string): string {
	return AVATAR_PALETTE[avatarPaletteIndex(value)];
}
