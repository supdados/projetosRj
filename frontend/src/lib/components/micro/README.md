# Micro-interações dos KPIs — guia de melhores práticas

Padrões consolidados para as animações de hover dos cartões de KPI do dashboard
(`StatCard`). Objetivo: criar micro-interações **distintas, discretas, fluidas e
robustas** sem precisar pesquisar de novo a cada vez.

> Componentes atuais (um por KPI): `FolderReveal` (Projetos), `ClipboardStamp`
> (Concluídos), `FolderFlip` + `FolderShape` (Vigentes), `AlertHourglass`
> (Em Atraso). Todos em `frontend/src/lib/components/micro/`.

---

## 1. Princípios

- **Uma animação por KPI, discreta.** Nada espalhafatoso; durações curtas
  (0.2–0.5s para CSS) e movimento que comunique o significado do KPI.
- **Decorativo:** o componente é `aria-hidden`. O rótulo acessível fica no link
  do `StatCard` (`aria-label`/texto), nunca na animação.
- **Reutilizável e isolado:** props com defaults, `size` em px, sem dependências
  pesadas. Forma de pasta compartilhada via `FolderShape` (fonte única de
  proporção — não duplicar geometria).

---

## 2. Gatilho de hover (padrão)

O `StatCard` tem a classe `group`. Cada micro-componente abre no hover **do
próprio elemento** e **do cartão inteiro**:

```css
.x-root:is(:hover, :focus-within) .alvo,
:global(.group:hover) .alvo,
:global(.group:focus-within) .alvo { /* estado ativo */ }
```

- Use **`:focus-within`** (não `:focus-visible`) para casar com o `:focus-within`
  do próprio root — evita descasamento entre os dois gatilhos.
- Em componentes com JS (canvas), use **um único alvo**: `root.closest('.group') ?? root`.
  Nunca escute root **e** `.group` ao mesmo tempo — a borda interna entre eles
  dispara enter/leave extras (pingue-pongue).

---

## 3. Anti hover-loop / flicker (OBRIGATÓRIO)

**O bug clássico (“doom-flicker”/hover-loop):** um elemento que se transforma no
hover sai de baixo do cursor → dispara `mouseleave` → reverte → `mouseenter` →
**loop infinito** ativa/desativa.

**Regra de ouro:** a caixa que avalia o `:hover` **não pode se mover**. Só os
filhos animam, e eles **não capturam o cursor**:

```css
.x-root        { /* estática: NÃO transforma */ }
.x-stage, .x-stage * { pointer-events: none; } /* filhos animados não pegam hover */
```

Assim o `:hover` é avaliado só na raiz imóvel → o loop fica impossível.
(Ref.: dev.to/annlin/css-flicker-on-hover.)

---

## 4. CSS transitions robustas

- **`transition` no estado BASE**, rápida e **sem delay** → reversível e
  interrompível a qualquer ponto. Ao sair, a pose volta na hora.
- **Enter lento + curva de “assentar” + `transition-delay`/cascata só no `:hover`.**
  Se houver delay no base, o leave reproduz a **cascata reversa** (volta
  escalonada) e flica. Delay/stagger pertencem **apenas ao estado ativo**.

```css
.item { transition: transform 0.22s ease; }            /* base: leave rápido */
.group:hover .item { transition: transform 0.42s cubic-bezier(0.34,1.2,0.64,1);
                     transition-delay: 120ms; }          /* enter: lento + cascata */
```

- **Anime só `transform`/`opacity`** (composited, 60fps, sem reflow). Nunca anime
  propriedades que causem layout — reflow pode reentrar no cálculo de hover.
- **`@keyframes` é armadilha** para hover: timeline fixa que reverte/reinicia →
  o “cai-e-volta”/duas-ondas. Prefira `transition` (vai do valor atual ao alvo e
  **segura a pose** enquanto o hover durar). Use `forwards`/keyframes só quando o
  estado final deve **permanecer** e não há reversão.
- `will-change: transform` e `backface-visibility: hidden` para estabilidade GPU.
- 3D: `perspective` no container (`transform-style: preserve-3d`) **ou**
  `perspective()` na função de transform do próprio elemento (auto-contido,
  robusto a aninhamento).

---

## 5. Componentes com `<canvas>` + requestAnimationFrame

Quando CSS não basta (partículas, física: ex.: `AlertHourglass`).

**Máquina de estados finita** como única fonte da verdade:

```
idle → entering → active → leaving → idle
```

- O `loop()` **só LÊ** `phase`; `start`/`stop` **só REESCREVEM** `phase`.
- `start`/`stop` **idempotentes**: nunca resetam progresso. Re-entrar durante
  `leaving` só re-mira para `entering` → o estado parcial (pilha, alphas) é
  **reaproveitado**, sem salto/flicker.
- **Um único rAF garantido** (anti rAF-fantasma/preso):

```ts
let raf = 0;
function requestLoop() { if (raf) return; raf = requestAnimationFrame(loop); }
function cancelLoop()  { if (!raf) return; cancelAnimationFrame(raf); raf = 0; }
```

- `loop()` zera `raf = 0` no topo (invariante “raf≠0 ⇔ frame agendado”), congela
  em `active` com `return` **sem reagendar** (0 CPU), e chama um `resetToIdle()`
  atômico quando termina.
- **hover-intent ~90ms na saída** (cancelável) para não cortar um fluxo caro num
  leave→enter rápido.
- **Pausar em `document.hidden`** via `visibilitychange` (não desperdiça CPU em
  aba oculta; religar só se `phase !== 'idle'`).
- **Debounce ~120ms no `resize`** (recalcular dimensões só em `idle`, nunca no
  meio do fluxo). Limpar o timer no cleanup.
- `onMount` retorna o cleanup: remover listeners, `cancelLoop()`, limpar timers.
- HiDPI: `canvas.width = cssW * dpr` e `ctx.scale(dpr, dpr)` (cap `dpr` em 2).
- Aleatoriedade do JS é permitida em componentes normais (varia partículas).

**Avalie helper compartilhado com ceticismo:** para 1 consumidor é abstração
prematura; os componentes CSS não usam JS algum. Mantivemos inline.

---

## 6. Acessibilidade e movimento reduzido

- Sempre `aria-hidden="true"` no componente (é decorativo).
- `@media (prefers-reduced-motion: reduce)`: zerar `transition`/`animation`
  (CSS) ou desligar partículas/rAF (canvas). Preservar a informação essencial de
  forma estática quando possível.

---

## 7. Assets (imagens)

Servidos pelo **Flask** em `/static/img/dashboard/...` (NÃO no bundle Svelte; o
`static/spa` é gitignored). Os arquivos-fonte em `static/img/` são versionados.

Converter PNG → **webp transparente** com ImageMagick:

```bash
# Fundo branco/claro sólido (e o objeto NÃO é branco):
magick in.png -fuzz 14% -transparent white -trim +repage -resize 320x320 out.webp

# Fundo da MESMA cor do objeto (ex.: vidro transparente): floodfill dos 4 cantos,
# preservando o interior fechado:
magick in.png -alpha set -fuzz 12% -fill none \
  -draw "alpha 0,0 floodfill" -draw "alpha W-1,0 floodfill" \
  -draw "alpha 0,H-1 floodfill" -draw "alpha W-1,H-1 floodfill" \
  -trim +repage -resize 320x320 out.webp
```

Verificar transparência compondo sobre cor sólida:
`magick out.webp -background red -flatten /tmp/check.png`.

---

## 8. Integração no `StatCard`

- `StatCard` raiz tem a classe `group` (dispara o hover no cartão inteiro).
- Ícones flat herdam a cor do tom via `currentColor` (o span aplica `iconColor[tone]`).
- Componentes com cor própria (pastas) recebem `accent`/`accentDark`/`accentLight`.
- Passar via snippet `icon`:

```svelte
{#snippet icon()}
  <MeuMicro size={46} />
{/snippet}
```

---

## 9. Fluxo de trabalho

1. Editar o componente em `micro/`.
2. `cd frontend && npm run build` (grava em `../static/spa`). **Rebuild é
   obrigatório** — o backend serve o bundle estático.
3. Recarregar a página e testar (inclui **teste de estresse**: mouse
   entrando/saindo rápido e repetido — não pode piscar nem travar).
4. `npm run check` deve ficar 0 erros (os ~10 warnings pré-existentes não são de
   `micro/`).

---

## 10. Checklist para uma nova micro-interação

- [ ] `aria-hidden` + `prefers-reduced-motion`.
- [ ] Gatilho `:hover/:focus-within` próprio + `:global(.group:hover/:focus-within)`.
- [ ] Raiz estática; filhos animados com `pointer-events: none`.
- [ ] `transition` no base (rápida, sem delay); enter lento + delay só no `:hover`.
- [ ] Anima só `transform`/`opacity`; `will-change` + `backface-visibility`.
- [ ] Se canvas/rAF: FSM, start/stop idempotentes, rAF único, hover-intent,
      pausa em `visibilitychange`, debounce de resize, cleanup completo.
- [ ] Assets webp transparentes em `static/img/dashboard/`.
- [ ] `npm run build` + teste de estresse de hover.
