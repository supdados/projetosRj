export interface SelectMenuOption {
	value: string;
	label: string;
	/** Cor CSS do dot semântico (ex: 'var(--ds-color-priority-alta)'). Omitir = sem dot. */
	dot?: string;
	disabled?: boolean;
}
