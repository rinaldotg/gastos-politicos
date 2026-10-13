(function () {
  'use strict';
  var RAIZ = document.body.getAttribute('data-raiz') || '';
  var CARGO_ROTULO = { deputado: 'Deputado federal', senador: 'Senador', presidente: 'Presidente' };

  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') e.textContent = attrs[k]; else if (k === 'class') e.className = attrs[k]; else e.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return e;
  }
  function brl(v) {
    var n = Math.round(Math.abs(v)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return (v < 0 ? '−' : '') + 'R$ ' + n;
  }
  function norm(s) { return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  function get(url) { return fetch(RAIZ + url).then(function (r) { return r.json(); }); }

  /* ---------- busca ---------- */
  var buscaCache = null;
  function carregarBusca() { return buscaCache || (buscaCache = get('data/busca.json')); }

  function iniciarBusca(form, aoEscolher) {
    var input = form.querySelector('input'), lista = form.querySelector('ul'), itens = [], ativo = -1;
    function fechar() { lista.hidden = true; input.setAttribute('aria-expanded', 'false'); ativo = -1; }
    function marcar() {
      Array.prototype.forEach.call(lista.children, function (li, i) { li.setAttribute('aria-selected', i === ativo ? 'true' : 'false'); });
    }
    function escolher(i) { if (itens[i]) { aoEscolher(itens[i]); input.value = ''; fechar(); } }
    input.addEventListener('input', function () {
      var q = norm(input.value.trim());
      if (q.length < 2) { fechar(); return; }
      var partes = q.split(/\s+/);
      carregarBusca().then(function (dados) {
        itens = dados.filter(function (d) { return partes.every(function (p) { return d.a.indexOf(p) >= 0; }); })
          .sort(function (a, b) { return (a.a.indexOf(partes[0]) === 0 ? 0 : 1) - (b.a.indexOf(partes[0]) === 0 ? 0 : 1) || a.n.localeCompare(b.n); })
          .slice(0, 8);
        lista.textContent = '';
        if (!itens.length) { lista.appendChild(el('li', { text: 'Nenhum nome encontrado' })); }
        itens.forEach(function (d, i) {
          var li = el('li', { role: 'option', 'aria-selected': 'false' }, [
            el('span', { text: d.n }),
            el('small', { text: (CARGO_ROTULO[d.c] || '') + (d.u ? ' · ' + d.u : '') + (d.p ? ' · ' + d.p : '') })
          ]);
          li.addEventListener('mousedown', function (ev) { ev.preventDefault(); escolher(i); });
          lista.appendChild(li);
        });
        lista.hidden = false; input.setAttribute('aria-expanded', 'true'); ativo = itens.length ? 0 : -1; marcar();
      });
    });
    input.addEventListener('keydown', function (ev) {
      if (lista.hidden) return;
      if (ev.key === 'ArrowDown') { ativo = Math.min(ativo + 1, itens.length - 1); marcar(); ev.preventDefault(); }
      else if (ev.key === 'ArrowUp') { ativo = Math.max(ativo - 1, 0); marcar(); ev.preventDefault(); }
      else if (ev.key === 'Enter') { if (ativo >= 0) { escolher(ativo); ev.preventDefault(); } }
      else if (ev.key === 'Escape') { fechar(); }
    });
    input.addEventListener('blur', function () { setTimeout(fechar, 120); });
  }

  /* ---------- ranking da home ---------- */
  function iniciarRanking(sec) {
    var selC = sec.querySelector('[data-r-cargo]'), selA = sec.querySelector('[data-r-ano]'), corpo = sec.querySelector('tbody');
    var maisBtn = null, dados = null, limite = 25;
    function render() {
      if (!dados) return;
      var linhas = (dados[selC.value] || {})[selA.value] || [];
      corpo.textContent = '';
      linhas.slice(0, limite).forEach(function (r, i) {
        corpo.appendChild(el('tr', {}, [
          el('td', { class: 'pos', text: String(i + 1) }),
          el('td', {}, [el('a', { href: RAIZ + r[1], text: r[0] })]),
          el('td', { text: r[2] }), el('td', { text: r[3] }),
          el('td', { class: 'num', text: brl(r[4]) }), el('td', { class: 'num', text: String(r[5]) })
        ]));
      });
      if (!linhas.length) corpo.appendChild(el('tr', {}, [el('td', { colspan: '6', text: 'Sem dados para este ano.' })]));
      if (maisBtn) maisBtn.remove();
      if (linhas.length > limite) {
        maisBtn = el('button', { class: 'botao botao-leve', type: 'button', text: 'Mostrar mais (' + (linhas.length - limite) + ')' });
        maisBtn.addEventListener('click', function () { limite += 50; render(); });
        sec.querySelector('.tabela-rolavel').after(maisBtn);
      }
    }
    get('data/ranking.json').then(function (d) { dados = d; render(); });
    [selC, selA].forEach(function (s) { s.addEventListener('change', function () { limite = 25; render(); }); });
    document.querySelectorAll('.grupo[data-cargo]').forEach(function (a) {
      a.addEventListener('click', function () { selC.value = a.getAttribute('data-cargo'); limite = 25; render(); });
    });
  }

  /* ---------- comparacao ---------- */
  function iniciarComparacao(sec, form) {
    var pessoas = [], abertos = {};
    var wrap = sec.querySelector('[data-comp-tabela]'), vazio = sec.querySelector('[data-vazio]'), nota = sec.querySelector('[data-comp-nota]');
    function url() {
      var ids = pessoas.map(function (p) { return p.id; }).join(',');
      history.replaceState(null, '', ids ? '?p=' + ids : location.pathname);
    }
    function adicionar(id) {
      if (pessoas.length >= 4 || pessoas.some(function (p) { return p.id === id; })) return Promise.resolve();
      return get('data/p/' + id + '.json').then(function (d) { pessoas.push(d); });
    }
    function remover(id) { pessoas = pessoas.filter(function (p) { return p.id !== id; }); url(); render(); }
    function celulas(valores, comDestaque) {
      var max = Math.max.apply(null, valores.map(function (v) { return v === null ? -Infinity : v; }));
      return valores.map(function (v) {
        return el('td', { class: 'num' + (comDestaque && valores.length > 1 && v === max && max > 0 ? ' maior' : ''), text: v === null ? '—' : brl(v) });
      });
    }
    function linha(rotulo, valores, cls, destaque) {
      return el('tr', { class: cls || '' }, [el('td', { class: 'rotulo', text: rotulo })].concat(celulas(valores, destaque !== false)));
    }
    function render() {
      vazio.hidden = pessoas.length > 0; wrap.hidden = !pessoas.length; nota.hidden = !pessoas.length;
      if (!pessoas.length) return;
      var cab = el('tr', {}, [el('th', { class: 'rotulo', text: '' })].concat(pessoas.map(function (p) {
        var rm = el('button', { type: 'button', text: 'Remover' });
        rm.addEventListener('click', function () { remover(p.id); });
        return el('th', { class: 'pessoa', scope: 'col' }, [
          el('a', { href: RAIZ + p.url, text: p.n }),
          el('small', { text: (CARGO_ROTULO[p.c] || '') + (p.u ? ' · ' + p.u : '') + (p.p ? ' · ' + p.p : '') }), rm]);
      })));
      var corpo = el('tbody');
      var totais = pessoas.map(function (p) { return Object.keys(p.anos).reduce(function (s, a) { return s + p.anos[a][0]; }, 0); });
      corpo.appendChild(linha('Total desde 2014', totais, 'total', false));
      var anos = {};
      pessoas.forEach(function (p) { Object.keys(p.anos).forEach(function (a) { anos[a] = 1; }); });
      Object.keys(anos).sort().reverse().forEach(function (a) {
        var tr = el('tr', { class: 'ano-linha' });
        var btn = el('button', { type: 'button', 'aria-expanded': abertos[a] ? 'true' : 'false', text: a });
        btn.addEventListener('click', function () { abertos[a] = !abertos[a]; render(); });
        tr.appendChild(el('td', { class: 'rotulo' }, [btn]));
        celulas(pessoas.map(function (p) { return p.anos[a] ? p.anos[a][0] : null; }), true).forEach(function (c) { tr.appendChild(c); });
        corpo.appendChild(tr);
        if (abertos[a]) {
          var soma = {};
          pessoas.forEach(function (p) { (p.anos[a] ? p.anos[a][2] : []).forEach(function (c) { soma[c[0]] = (soma[c[0]] || 0) + c[1]; }); });
          Object.keys(soma).sort(function (x, y) { return soma[y] - soma[x]; }).forEach(function (cat) {
            corpo.appendChild(linha(cat, pessoas.map(function (p) {
              var f = (p.anos[a] ? p.anos[a][2] : []).filter(function (c) { return c[0] === cat; })[0];
              return f ? f[1] : null;
            }), 'cat-linha'));
          });
        }
      });
      var temEm = pessoas.some(function (p) { return Object.keys(p.em).length; });
      if (temEm) {
        corpo.appendChild(el('tr', {}, [el('th', { class: 'rotulo', colspan: String(pessoas.length + 1), text: 'Emendas individuais pagas, por ano da emenda' })]));
        var ems = {};
        pessoas.forEach(function (p) { Object.keys(p.em).forEach(function (a) { ems[a] = 1; }); });
        corpo.appendChild(linha('Total desde 2014', pessoas.map(function (p) { return Object.keys(p.em).reduce(function (s, a) { return s + p.em[a][2]; }, 0); }), 'total', false));
        Object.keys(ems).sort().reverse().forEach(function (a) {
          corpo.appendChild(linha(a, pessoas.map(function (p) { return p.em[a] ? p.em[a][2] : null; }), 'cat-linha'));
        });
      }
      wrap.textContent = '';
      wrap.appendChild(el('table', { class: 'tabela comp' }, [el('thead', {}, [cab]), corpo]));
    }
    var ini = (new URLSearchParams(location.search).get('p') || '').split(',').filter(Boolean).slice(0, 4).map(Number);
    Promise.all(ini.map(adicionar)).then(function () { render(); });
    iniciarBusca(form, function (d) { adicionar(d.id).then(function () { url(); render(); }); });
  }

  document.querySelectorAll('[data-busca]').forEach(function (f) {
    if (f.hasAttribute('data-comparar')) return;
    iniciarBusca(f, function (d) { location.href = RAIZ + d.url; });
  });
  var r = document.querySelector('[data-ranking]'); if (r) iniciarRanking(r);
  var c = document.querySelector('[data-comparacao]'); if (c) iniciarComparacao(c, document.querySelector('[data-comparar]'));
})();
