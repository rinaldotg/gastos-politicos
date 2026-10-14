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


  /* ---------- emendas de uma pessoa ---------- */
  // linha: [ano, pix(1)/definida(0), numero, codigo, destino, funcao, subfuncao, programa, acao, empenhado, liquidado, pago]
  function iniciarEmendas(box) {
    var id = box.getAttribute('data-id'), tipo = 'todas', ano = '', linhas = [], abertas = {}, limites = {}, favs = {};
    var areasEl = box.querySelector('[data-areas]'), resumo = box.querySelector('[data-resumo]');
    var selAno = box.querySelector('[data-ano]'), destinos = box.querySelector('[data-destinos]');
    var PASSO = 10;
    function filtradas() {
      return linhas.filter(function (l) {
        return (tipo === 'todas' || (tipo === 'pix' ? l[1] === 1 : l[1] === 0)) && (!ano || String(l[0]) === ano);
      });
    }
    function agrupar(itens) {
      var mapa = {}, ordem = [];
      itens.forEach(function (l, i) {
        var k = l[3] || ('x' + i);
        if (!mapa[k]) { mapa[k] = { l: l, emp: 0, pago: 0, dest: [], acoes: [], k: k }; ordem.push(k); }
        var g = mapa[k]; g.emp += l[9]; g.pago += l[11];
        if (l[4] && g.dest.indexOf(l[4]) < 0) g.dest.push(l[4]);
        var ac = [l[7], l[8]].filter(Boolean).join(' · ');
        if (ac && g.acoes.indexOf(ac) < 0) g.acoes.push(ac);
      });
      return ordem.map(function (k) { return mapa[k]; }).sort(function (a, b) { return b.pago - a.pago || b.emp - a.emp; });
    }
    function linkRec(r) {
      var nome = r[1] ? el('a', { href: RAIZ + 'recebedor/?d=' + encodeURIComponent(r[1]), text: r[0] }) : document.createTextNode(r[0]);
      return el('div', { class: 'rec' }, [el('strong', {}, [nome]), el('small', { text: [r[1], r[3], brl(r[4])].filter(Boolean).join(' · ') })]);
    }
    function quemRecebeu(g) {
      var par = favs[g.k];
      if (!par || !par[0].length) {
        return el('td', { class: 'recebedor', text: g.pago > 0 ? 'Não informado na fonte' : 'Ainda sem pagamento registrado' });
      }
      var td = el('td', { class: 'recebedor' });
      par[0].forEach(function (r) { td.appendChild(linkRec(r)); });
      td.appendChild(el('a', { class: 'ver-todos', href: RAIZ + 'emenda/?c=' + encodeURIComponent(g.k),
        text: par[1] > par[0].length ? 'Ver todos os ' + par[1] + ' recebedores →' : 'Ver detalhes da emenda →' }));
      return td;
    }
    function tabela(itens, nome) {
      var lim = limites[nome] || PASSO, emendas = agrupar(itens);
      var corpo = el('tbody');
      emendas.slice(0, lim).forEach(function (g) {
        var l = g.l;
        corpo.appendChild(el('tr', {}, [
          el('td', {}, [document.createTextNode((l[1] ? 'Pix' : 'Finalidade definida') + (l[2] ? ' nº ' + l[2] : '')),
                        el('small', { text: 'Ano ' + l[0] + (l[3] ? ' · código ' + l[3] : '') })]),
          quemRecebeu(g),
          el('td', { text: g.dest.slice(0, 3).join(', ') + (g.dest.length > 3 ? ' e mais ' + (g.dest.length - 3) : '') || '—' }),
          el('td', {}, [document.createTextNode([l[6]].filter(Boolean).join('') || '—'), g.acoes.length ? el('small', { text: g.acoes[0] }) : document.createTextNode('')]),
          el('td', { class: 'num', text: brl(g.emp) }), el('td', { class: 'num', text: brl(g.pago) })
        ]));
      });
      var wrap = el('div', { class: 'tabela-rolavel' }, [el('table', { class: 'tabela tabela-emendas' }, [
        el('thead', {}, [el('tr', {}, [el('th', { text: 'Emenda' }), el('th', { text: 'Quem recebeu' }), el('th', { text: 'Destino' }),
          el('th', { text: 'Subárea e ação' }), el('th', { class: 'num', text: 'Empenhado' }), el('th', { class: 'num', text: 'Pago' })])]),
        corpo])]);
      var out = [wrap];
      if (emendas.length > lim) {
        var b = el('button', { type: 'button', class: 'botao botao-leve', text: 'Mostrar mais (' + (emendas.length - lim) + ')' });
        b.addEventListener('click', function () { limites[nome] = lim + 25; render(); });
        out.push(b);
      }
      return out;
    }
    function render() {
      var f = filtradas(), emp = 0, pago = 0, dest = {}, grupos = {};
      f.forEach(function (l) {
        emp += l[9]; pago += l[11];
        if (l[4]) dest[l[4]] = (dest[l[4]] || 0) + l[11];
        var g = l[5] || 'Área não informada';
        (grupos[g] = grupos[g] || { itens: [], emp: 0, pago: 0 });
        grupos[g].itens.push(l); grupos[g].emp += l[9]; grupos[g].pago += l[11];
      });
      var rot = tipo === 'pix' ? 'emendas Pix' : tipo === 'def' ? 'emendas com finalidade definida' : 'emendas individuais';
      resumo.textContent = f.length ? (f.length + ' lançamentos de ' + rot + (ano ? ' de ' + ano : '') + ': ' + brl(emp) + ' empenhados e ' + brl(pago) + ' pagos.')
                                   : 'Nenhuma emenda neste filtro.';
      areasEl.textContent = '';
      var maximo = 0;
      Object.keys(grupos).forEach(function (g) { maximo = Math.max(maximo, grupos[g].pago); });
      Object.keys(grupos).sort(function (a, b) { return grupos[b].pago - grupos[a].pago || grupos[b].emp - grupos[a].emp; }).forEach(function (g) {
        var gr = grupos[g];
        var barra = el('span', { class: 'ano-barra', 'aria-hidden': 'true' }, [el('i', { style: 'width:' + (maximo ? Math.max(0, gr.pago) / maximo * 100 : 0).toFixed(1) + '%' })]);
        var sum = el('summary', {}, [el('span', { class: 'ano-n area-n', text: g }), barra,
          el('span', { class: 'ano-v', text: brl(gr.pago) + ' pagos' })]);
        var d = el('details', { class: 'ano area' }, [sum]);
        if (abertas[g]) d.setAttribute('open', '');
        d.addEventListener('toggle', function () { abertas[g] = d.open; });
        var itens = gr.itens.slice().sort(function (a, b) { return b[11] - a[11] || b[9] - a[9]; });
        d.appendChild(el('p', { class: 'nota', text: gr.itens.length + ' lançamentos · ' + brl(gr.emp) + ' empenhados' }));
        tabela(itens, g).forEach(function (n) { d.appendChild(n); });
        areasEl.appendChild(d);
      });
      destinos.textContent = '';
      Object.keys(dest).sort(function (a, b) { return dest[b] - dest[a]; }).slice(0, 8).forEach(function (k) {
        if (dest[k] > 0) destinos.appendChild(el('li', {}, [el('span', { text: k }), el('span', { class: 'num', text: brl(dest[k]) })]));
      });
    }
    box.querySelectorAll('[data-tipo]').forEach(function (b) {
      b.addEventListener('click', function () {
        tipo = b.getAttribute('data-tipo'); limites = {};
        box.querySelectorAll('[data-tipo]').forEach(function (o) { o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); });
        render();
      });
    });
    selAno.addEventListener('change', function () { ano = selAno.value; limites = {}; render(); });
    get('data/e/' + id + '.json').then(function (resp) {
      var d = Array.isArray(resp) ? resp : resp.r;
      favs = Array.isArray(resp) ? {} : (resp.f || {});
      linhas = d;
      var anos = {}; d.forEach(function (l) { anos[l[0]] = 1; });
      Object.keys(anos).sort().reverse().forEach(function (a) { selAno.appendChild(el('option', { value: a, text: a })); });
      render();
    }).catch(function () { resumo.textContent = 'Não foi possível carregar o detalhe das emendas.'; });
  }

  /* ---------- ranking de emendas Pix ---------- */
  function iniciarPix(sec) {
    var selC = sec.querySelector('[data-p-cargo]'), selA = sec.querySelector('[data-p-ano]'), selO = sec.querySelector('[data-p-ordem]');
    var corpo = sec.querySelector('[data-p-corpo]'), mais = sec.querySelector('[data-p-mais]'), resumo = sec.querySelector('[data-p-resumo]');
    var dados = [], limite = 30;
    function render() {
      var ordem = Number(selO.value), ano = selA.value, tot = [0, 0];
      var lista = dados.filter(function (d) { return !selC.value || d[2] === selC.value; }).map(function (d) {
        var v = [0, 0];
        Object.keys(d[5]).forEach(function (a) { if (!ano || a === ano) { v[0] += d[5][a][0]; v[1] += d[5][a][1]; } });
        return { d: d, v: v };
      }).filter(function (x) { return x.v[0] > 0 || x.v[1] > 0; }).sort(function (a, b) { return b.v[ordem] - a.v[ordem]; });
      lista.forEach(function (x) { tot[0] += x.v[0]; tot[1] += x.v[1]; });
      resumo.textContent = lista.length + ' parlamentares' + (ano ? ' com emendas Pix de ' + ano : ' com emendas Pix') + ': ' + brl(tot[0]) + ' empenhados e ' + brl(tot[1]) + ' pagos.';
      corpo.textContent = '';
      lista.slice(0, limite).forEach(function (x, i) {
        corpo.appendChild(el('tr', {}, [
          el('td', { class: 'pos', text: String(i + 1) }),
          el('td', {}, [el('a', { href: RAIZ + x.d[1], text: x.d[0] })]),
          el('td', { text: x.d[3] }), el('td', { text: x.d[4] }),
          el('td', { class: 'num', text: brl(x.v[0]) }), el('td', { class: 'num', text: brl(x.v[1]) })
        ]));
      });
      mais.hidden = lista.length <= limite;
      mais.textContent = 'Mostrar mais (' + (lista.length - limite) + ')';
    }
    [selC, selA, selO].forEach(function (s) { s.addEventListener('change', function () { limite = 30; render(); }); });
    mais.addEventListener('click', function () { limite += 50; render(); });
    get('data/pix.json').then(function (d) { dados = d; render(); });
  }


  /* ---------- tela: todos os recebedores de uma emenda ---------- */
  function iniciarTelaEmenda(sec) {
    var cod = new URLSearchParams(location.search).get('c') || '', N = +sec.getAttribute('data-n');
    var lista = document.querySelector('[data-e-lista]'), vazio = document.querySelector('[data-e-vazio]');
    var corpo = lista.querySelector('[data-e-corpo]'), mais = lista.querySelector('[data-e-mais]'), filtro = lista.querySelector('[data-e-filtro]');
    var linhas = [], limite = 100;
    if (!/^\d+$/.test(cod)) { vazio.hidden = false; return; }
    function render() {
      var q = norm(filtro.value.trim()), f = linhas.filter(function (r) { return !q || norm(r[0] + ' ' + r[1]).indexOf(q) >= 0; });
      corpo.textContent = '';
      f.slice(0, limite).forEach(function (r, i) {
        var nome = r[1] ? el('a', { href: RAIZ + 'recebedor/?d=' + encodeURIComponent(r[1]), text: r[0] }) : document.createTextNode(r[0]);
        corpo.appendChild(el('tr', {}, [el('td', { class: 'pos', text: String(i + 1) }),
          el('td', {}, [nome, el('small', { text: r[1] })]), el('td', { text: r[2] }), el('td', { text: r[3] }),
          el('td', { class: 'num', text: brl(r[4]) })]));
      });
      mais.hidden = f.length <= limite;
      mais.textContent = 'Mostrar mais (' + (f.length - limite) + ')';
    }
    mais.addEventListener('click', function () { limite += 100; render(); });
    filtro.addEventListener('input', function () { limite = 100; render(); });
    Promise.all([get('data/fe/' + (Number(cod) % N) + '.json'), carregarBusca()]).then(function (res) {
      var d = res[0][cod];
      if (!d) { vazio.hidden = false; return; }
      var i = d.i, p = res[1].filter(function (x) { return x.id === i[0]; })[0];
      document.querySelector('[data-e-titulo]').textContent = 'Quem recebeu a emenda ' + (i[3] ? 'nº ' + i[3] + ' ' : '') + 'de ' + i[1];
      var info = document.querySelector('[data-e-info]');
      info.appendChild(document.createTextNode((i[2] ? 'Emenda Pix' : 'Emenda individual') + ' de '));
      info.appendChild(p ? el('a', { href: RAIZ + p.url, text: p.n }) : document.createTextNode('parlamentar'));
      info.appendChild(document.createTextNode((p && p.p ? ' (' + p.p + (p.u ? '/' + p.u : '') + ')' : '') + '. Destino: ' + (i[4] || 'não informado') +
        (i[5] ? ' · Área: ' + i[5] : '') + ' · Empenhado ' + brl(i[6]) + ' · Pago ' + brl(i[7]) + '.'));
      linhas = d.f;
      lista.querySelector('[data-e-cont]').textContent = linhas.length + ' recebedores';
      lista.hidden = false; render();
    }).catch(function () { vazio.hidden = false; });
  }

  /* ---------- tela: parlamentares que destinaram emendas a um recebedor ---------- */
  function iniciarTelaRecebedor(sec) {
    var doc = new URLSearchParams(location.search).get('d') || '', N = +sec.getAttribute('data-n');
    var lista = document.querySelector('[data-r-lista]'), vazio = document.querySelector('[data-r-vazio]'), corpo = lista.querySelector('[data-r-corpo]');
    var dig = doc.replace(/\D/g, '');
    if (!dig) { vazio.hidden = false; return; }
    Promise.all([get('data/fr/' + (Number(dig) % N) + '.json'), carregarBusca()]).then(function (res) {
      var d = res[0][doc], pessoas = {};
      res[1].forEach(function (x) { pessoas[x.id] = x; });
      if (!d) { vazio.hidden = false; return; }
      document.querySelector('[data-r-titulo]').textContent = d.n;
      var total = d.p.reduce(function (s, x) { return s + x[1]; }, 0);
      document.querySelector('[data-r-info]').textContent = doc + (d.l ? ' · ' + d.l : '') + (d.t ? ' · ' + d.t : '') + ' — recebeu ' + brl(total) +
        ' em emendas de ' + d.p.length + (d.p.length === 1 ? ' parlamentar.' : ' parlamentares.');
      d.p.forEach(function (x, i) {
        var p = pessoas[x[0]] || { n: 'Parlamentar', url: '', u: '', p: '' };
        var det = el('details', { class: 'rec-mais' }, [el('summary', { text: 'ver emendas' })]);
        x[2].sort(function (a, b) { return b[3] - a[3]; }).forEach(function (e) {
          det.appendChild(el('div', { class: 'rec' }, [el('a', { href: RAIZ + 'emenda/?c=' + encodeURIComponent(e[0]), text: (e[2] ? 'Pix' : 'Individual') + ' · ' + e[1] + ' · código ' + e[0] }),
            el('small', { text: brl(e[3]) })]));
        });
        corpo.appendChild(el('tr', {}, [el('td', { class: 'pos', text: String(i + 1) }),
          el('td', {}, [p.url ? el('a', { href: RAIZ + p.url, text: p.n }) : document.createTextNode(p.n), det]),
          el('td', { text: p.u || '' }), el('td', { text: p.p || '' }),
          el('td', { class: 'num', text: String(x[2].length) }), el('td', { class: 'num', text: brl(x[1]) })]));
      });
      lista.hidden = false;
    }).catch(function () { vazio.hidden = false; });
  }

  document.querySelectorAll('[data-busca]').forEach(function (f) {
    if (f.hasAttribute('data-comparar')) return;
    iniciarBusca(f, function (d) { location.href = RAIZ + d.url; });
  });
  var r = document.querySelector('[data-ranking]'); if (r) iniciarRanking(r);
  document.querySelectorAll('[data-emendas]').forEach(iniciarEmendas);
  var te = document.querySelector('[data-emenda]'); if (te) iniciarTelaEmenda(te);
  var tr_ = document.querySelector('[data-recebedor]'); if (tr_) iniciarTelaRecebedor(tr_);
  var px = document.querySelector('[data-pix]'); if (px) iniciarPix(px);
  var c = document.querySelector('[data-comparacao]'); if (c) iniciarComparacao(c, document.querySelector('[data-comparar]'));
})();
