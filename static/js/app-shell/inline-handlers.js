/**
 * Substitui handlers inline (onsubmit/onclick) por data-attributes,
 * necessário para operar sob CSP restritiva sem 'unsafe-inline' em script-src.
 *
 * Padrões suportados:
 *   <form data-confirm="Tem certeza?">        → confirma antes do submit
 *   <button data-action="prevMonth">          → chama window.prevMonth() no click
 *   <select data-action-change="updateFoo"    → chama window.updateFoo(value, el) no change
 *           data-action-args="42">              com argumento opcional antes do value
 */
(function () {
    function runGlobal(fnName, args) {
        if (!fnName) return true;
        var fn = window[fnName];
        if (typeof fn !== 'function') {
            console.warn('[inline-handlers] função global não encontrada:', fnName);
            return true;
        }
        return fn.apply(null, args || []);
    }

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        var message = form.getAttribute('data-confirm');
        if (message && !window.confirm(message)) {
            event.preventDefault();
        }
    }, true);

    document.addEventListener('click', function (event) {
        var el = event.target.closest('[data-action]');
        if (!el) return;
        var fnName = el.getAttribute('data-action');
        var rawArgs = el.getAttribute('data-action-args');
        var args = rawArgs ? rawArgs.split('|') : [];
        // Convenção: elemento clicado vai como último argumento; funções que não
        // usam extras ignoram naturalmente (JS aceita args excedentes).
        args.push(el);
        var result = runGlobal(fnName, args);
        if (result === false) {
            event.preventDefault();
        }
    });

    document.addEventListener('change', function (event) {
        var el = event.target.closest('[data-action-change]');
        if (!el) return;
        var fnName = el.getAttribute('data-action-change');
        var rawArgs = el.getAttribute('data-action-args');
        var staticArgs = rawArgs ? rawArgs.split('|') : [];
        // Convenção: primeiro argumento pode ser um ID em data-action-args;
        // depois vêm (value, element).
        var args = staticArgs.concat([el.value, el]);
        runGlobal(fnName, args);
    });
})();
