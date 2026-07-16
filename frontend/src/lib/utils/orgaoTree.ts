/**
 * Lógica pura de montagem de árvore por `pai_id`, compartilhada entre
 * `OrgaoTreeSelect.svelte` (single-select) e `AreaResponsavelPicker.svelte`
 * (multi-select). Extraído de `OrgaoTreeSelect.svelte` para eliminar
 * duplicação — comportamento idêntico ao original.
 */

export interface OrgaoTreeOptionLike {
	value: number;
	pai_id: number | null;
	sigla?: string | null;
	nome?: string | null;
}

export interface OrgaoTreeNode<T> {
	value: number;
	option: T;
	children: OrgaoTreeNode<T>[];
}

export interface OrgaoTreeRow<T> {
	value: number;
	option: T;
	depth: number;
	hasChildren: boolean;
	expanded: boolean;
	path: string;
	isSearch: boolean;
}

const COMBINING_MARKS = /[̀-ͯ]/g;

/** Normaliza para busca: NFD + remove marcas combinantes + lowercase. */
export function normalizeSearchText(s: string | null | undefined): string {
	return (s ?? '').normalize('NFD').replace(COMBINING_MARKS, '').toLowerCase();
}

const isSubsecretaria = (nome: string | null | undefined): boolean =>
	normalizeSearchText(nome).startsWith('subsecretaria');

/** Monta a árvore por `pai_id`, preservando a ordem de chegada. */
export function buildOrgaoTree<T extends OrgaoTreeOptionLike>(options: T[]): OrgaoTreeNode<T>[] {
	const byId = new Map<number, OrgaoTreeNode<T>>();
	for (const option of options) {
		byId.set(Number(option.value), { value: Number(option.value), option, children: [] });
	}
	const roots: OrgaoTreeNode<T>[] = [];
	for (const option of options) {
		const node = byId.get(Number(option.value))!;
		const parentId = option.pai_id;
		const parent = parentId == null ? undefined : byId.get(Number(parentId));
		if (parent) parent.children.push(node);
		else roots.push(node);
	}
	return roots;
}

/**
 * Default de expansão (spec): raízes sempre expandidas; nó "Subsecretaria..."
 * e todos os seus descendentes expandidos; demais nós expandidos só quando
 * têm ≤ 7 filhos diretos.
 */
export function computeDefaultExpanded<T extends OrgaoTreeOptionLike>(
	tree: OrgaoTreeNode<T>[]
): Set<number> {
	const out = new Set<number>();
	const seed = (nodes: OrgaoTreeNode<T>[], force: boolean, isRoot: boolean): void => {
		for (const node of nodes) {
			const sub = isSubsecretaria(node.option.nome);
			if (node.children.length > 0) {
				if (isRoot || force || sub || node.children.length <= 7) out.add(node.value);
			}
			seed(node.children, force || sub, false);
		}
	};
	seed(tree, false, true);
	return out;
}

/**
 * Todas as linhas ACHATADAS com o caminho de ancestrais como `path`, na ordem
 * de percurso da árvore (irmãos preservam a ordem de chegada). `term` vazio
 * retorna tudo; com `term`, filtra por sigla/nome (accent-insensitive).
 * Usado pelo picker multi-select busca-first (sem árvore navegável).
 */
export function flattenTreeWithPath<T extends OrgaoTreeOptionLike>(
	tree: OrgaoTreeNode<T>[],
	term: string,
	opts: { omitRootAncestor?: boolean } = {}
): OrgaoTreeRow<T>[] {
	const query = normalizeSearchText(term.trim());
	const out: OrgaoTreeRow<T>[] = [];
	// `omitRootAncestor`: quando todas as áreas descendem de uma raiz única
	// (GOVRJ), o prefixo dela em todo caminho é ruído — cai fora do path.
	const pathStart = opts.omitRootAncestor ? 1 : 0;
	const walk = (nodes: OrgaoTreeNode<T>[], ancestors: OrgaoTreeNode<T>[]): void => {
		for (const node of nodes) {
			const matches =
				!query ||
				normalizeSearchText(node.option.sigla).includes(query) ||
				normalizeSearchText(node.option.nome).includes(query);
			if (matches) {
				out.push({
					value: node.value,
					option: node.option,
					depth: 0,
					hasChildren: false,
					expanded: false,
					path: ancestors
						.slice(pathStart)
						.map((a) => a.option.sigla || a.option.nome || '')
						.join(' › '),
					isSearch: true
				});
			}
			walk(node.children, [...ancestors, node]);
		}
	};
	walk(tree, []);
	return out;
}

/** Linhas visíveis: árvore respeitando expansão, ou matches achatados na busca. */
export function buildOrgaoTreeRows<T extends OrgaoTreeOptionLike>(
	tree: OrgaoTreeNode<T>[],
	isExpanded: (v: number) => boolean,
	term: string
): OrgaoTreeRow<T>[] {
	const query = normalizeSearchText(term.trim());
	const out: OrgaoTreeRow<T>[] = [];
	if (query) {
		const walk = (nodes: OrgaoTreeNode<T>[], ancestors: OrgaoTreeNode<T>[]): void => {
			for (const node of nodes) {
				if (
					normalizeSearchText(node.option.sigla).includes(query) ||
					normalizeSearchText(node.option.nome).includes(query)
				) {
					out.push({
						value: node.value,
						option: node.option,
						depth: 0,
						hasChildren: false,
						expanded: false,
						path: ancestors.map((a) => a.option.sigla || a.option.nome || '').join(' › '),
						isSearch: true
					});
				}
				walk(node.children, [...ancestors, node]);
			}
		};
		walk(tree, []);
		return out;
	}
	const flatten = (nodes: OrgaoTreeNode<T>[], depth: number): void => {
		for (const node of nodes) {
			const hasChildren = node.children.length > 0;
			const expanded = isExpanded(node.value);
			out.push({
				value: node.value,
				option: node.option,
				depth,
				hasChildren,
				expanded,
				path: '',
				isSearch: false
			});
			if (hasChildren && expanded) flatten(node.children, depth + 1);
		}
	};
	flatten(tree, 0);
	return out;
}
