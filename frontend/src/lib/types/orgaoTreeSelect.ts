/**
 * Opção PLANA de órgão consumida pelo `OrgaoTreeSelect.svelte`.
 *
 * Espelha o shape de `serialize_orgao_option` (routes/api/serializers.py) — a
 * lista chega achatada na ordem hierárquica do backend (`get_visible_orgao_tree`)
 * e o componente reconstrói a árvore client-side por `pai_id`. `value` é o id do
 * órgão; nós cujo `pai_id` não está na lista viram raízes.
 */
export interface OrgaoSelectOption {
	value: number;
	label: string;
	sigla: string | null;
	nome: string | null;
	pai_id: number | null;
	is_inactive?: boolean;
}
