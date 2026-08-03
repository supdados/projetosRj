import type { StateIconId } from '$lib/icons/stateIcons';
import type { ProjectIconId } from '$lib/icons/projectIcons';

export interface SelectMenuOption {
	value: string;
	label: string;
	/** Cor CSS do dot semântico (ex: 'var(--ds-color-priority-alta)'). Omitir = sem dot. */
	dot?: string;
	/** Ícone de estado ou de projeto no lugar do dot; pinta com a cor de `dot`. */
	icon?: StateIconId | ProjectIconId;
	disabled?: boolean;
}
