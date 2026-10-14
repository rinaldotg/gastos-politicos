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

  function slug(t) { return norm(t).replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, ''); }
  function copiar(texto, rotulo) {
    var b = el('button', { type: 'button', class: 'botao botao-leve botao-mini', text: rotulo });
    b.addEventListener('click', function () {
      var ok = function () { b.textContent = 'Copiado ✓'; setTimeout(function () { b.textContent = rotulo; }, 1800); };
      if (navigator.clipboard) navigator.clipboard.writeText(texto).then(ok, function () {});
    });
    return b;
  }
  var PORTAL_EMENDAS = 'https://portaldatransparencia.gov.br/emendas/consulta';
  var CNPJ_RECEITA = 'https://solucoes.receita.fazenda.gov.br/servicos/cnpjreva/cnpjreva_solicitacao.asp';
  function locLink(loc, texto) {
    var m = /^(.+)\/([A-Z]{2})$/.exec(loc || '');
    return m ? el('a', { href: RAIZ + 'municipio/?m=' + slug(loc.replace('/', '-')), text: texto || loc }) : document.createTextNode(texto || loc || '');
  }
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
          el('td', {}, [nome, el('small', { text: r[1] })]), el('td', { text: r[2] }), el('td', {}, [locLink(r[3])]),
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
      var fo = document.querySelector('[data-e-fonte]');
      fo.appendChild(document.createTextNode('Conferir na fonte: no Portal da Transparência, cole o código '));
      fo.appendChild(el('strong', { text: cod }));
      fo.appendChild(document.createTextNode(' no campo "Código da Emenda". '));
      fo.appendChild(copiar(cod, 'Copiar código'));
      fo.appendChild(document.createTextNode(' '));
      fo.appendChild(el('a', { href: PORTAL_EMENDAS, target: '_blank', rel: 'noopener', text: 'Abrir consulta de emendas ↗' }));
      var cs = d.c || [], cb = document.querySelector('[data-e-conv]');
      if (cs.length) {
        var area = cb.querySelector('[data-e-conv-corpo]');
        cs.forEach(function (c) {
          var liga = c[4] ? ('Valor do convênio ' + brl(c[4]) + (c[5] ? ' · liberado ' + brl(c[5]) : '')) : '';
          var vig = (c[6] || c[7]) ? ('Vigência: ' + (c[6] || '?') + ' a ' + (c[7] || '?')) : '', pub = c[8] ? 'Publicado em ' + c[8] : '';
          area.appendChild(el('div', { class: 'convenio' }, [
            el('p', { class: 'conv-sit' }, c[3] ? [el('strong', { text: c[3] }), document.createTextNode(c[0] ? ' · convênio nº ' + c[0] : '')] : [el('strong', { text: c[0] ? 'Convênio nº ' + c[0] : 'Convênio' })]),
            el('p', { class: 'conv-obj', text: c[2] || 'Objeto não informado na fonte.' }),
            el('small', { text: [c[1] ? 'Convenente: ' + c[1] : '', liga, pub, vig].filter(Boolean).join(' · ') })
          ]));
        });
        cb.hidden = false;
      } else {
        document.querySelector('[data-e-semconv]').hidden = false;
      }
      linhas = d.f;
      lista.querySelector('[data-e-cont]').textContent = linhas.length + ' recebedores';
      lista.hidden = false; render();
    }).catch(function () { vazio.hidden = false; });
  }

  /* ---------- anos (filtro por ano do pagamento) ---------- */
  function anoDaUrl() { return new URLSearchParams(location.search).get('a') || ''; }
  function qa(a) { return a ? '&a=' + a : ''; }
  function ligarAno(sel, aoMudar) {
    sel.value = anoDaUrl();
    if (sel.value !== anoDaUrl()) sel.value = '';
    sel.addEventListener('change', function () {
      var u = new URL(location.href);
      if (sel.value) u.searchParams.set('a', sel.value); else u.searchParams.delete('a');
      history.replaceState(null, '', u.toString());
      aoMudar(sel.value);
    });
  }
  function valorAno(mapa, ano) {  // mapa {ano: valor | [valor, n]}; ano '' = soma de todos
    var tot = 0, n = 0;
    Object.keys(mapa).forEach(function (k) {
      if (ano && k !== ano) return;
      var v = mapa[k];
      tot += Array.isArray(v) ? v[0] : v; n += Array.isArray(v) ? v[1] : 0;
    });
    return [tot, n];
  }

  /* ---------- tela: parlamentares que destinaram emendas a um recebedor ---------- */
  function iniciarTelaRecebedor(sec) {
    var doc = new URLSearchParams(location.search).get('d') || '', N = +sec.getAttribute('data-n');
    var lista = document.querySelector('[data-r-lista]'), vazio = document.querySelector('[data-r-vazio]'), corpo = lista.querySelector('[data-r-corpo]');
    var selA = document.querySelector('[data-r-ano]'), dig = doc.replace(/\D/g, ''), dados = null, pessoas = {};
    if (!dig) { vazio.hidden = false; return; }
    function render() {
      var ano = selA.value, d = dados, linhas = [];
      d.p.forEach(function (x) {
        var es = x[2].filter(function (e) { return !ano || String(e[4]) === ano; });
        if (es.length) linhas.push([x[0], es.reduce(function (s, e) { return s + e[3]; }, 0), es]);
      });
      linhas.sort(function (a, b) { return b[1] - a[1]; });
      var total = linhas.reduce(function (s, x) { return s + x[1]; }, 0);
      document.querySelector('[data-r-titulo]').textContent = d.n;
      var inf = document.querySelector('[data-r-info]');
      inf.textContent = doc + (d.l ? ' · ' : '');
      if (d.l) inf.appendChild(locLink(d.l));
      inf.appendChild(document.createTextNode((d.t ? ' · ' + d.t : '') + ' — ' + (linhas.length ?
        'recebeu ' + brl(total) + (ano ? ' em ' + ano : '') + ' em emendas de ' + linhas.length + (linhas.length === 1 ? ' parlamentar.' : ' parlamentares.') :
        'não recebeu emendas pagas em ' + ano + '.')));
      corpo.textContent = '';
      linhas.forEach(function (x, i) {
        var p = pessoas[x[0]] || { n: 'Parlamentar', url: '', u: '', p: '' };
        var det = el('details', { class: 'rec-mais' }, [el('summary', { text: 'ver emendas' })]);
        var porCod = {};
        x[2].forEach(function (e) { var k = e[0]; (porCod[k] = porCod[k] || [e[0], e[1], e[2], 0]); porCod[k][3] += e[3]; });
        Object.keys(porCod).map(function (k) { return porCod[k]; }).sort(function (a, b) { return b[3] - a[3]; }).forEach(function (e) {
          det.appendChild(el('div', { class: 'rec' }, [el('a', { href: RAIZ + 'emenda/?c=' + encodeURIComponent(e[0]), text: (e[2] ? 'Pix' : 'Individual') + ' · ' + e[1] + ' · código ' + e[0] }),
            el('small', { text: brl(e[3]) })]));
        });
        corpo.appendChild(el('tr', {}, [el('td', { class: 'pos', text: String(i + 1) }),
          el('td', {}, [p.url ? el('a', { href: RAIZ + p.url, text: p.n }) : document.createTextNode(p.n), det]),
          el('td', { text: p.u || '' }), el('td', { text: p.p || '' }),
          el('td', { class: 'num', text: String(Object.keys(porCod).length) }), el('td', { class: 'num', text: brl(x[1]) })]));
      });
    }
    Promise.all([get('data/fr/' + (Number(dig) % N) + '.json'), carregarBusca()]).then(function (res) {
      dados = res[0][doc];
      res[1].forEach(function (x) { pessoas[x.id] = x; });
      if (!dados) { vazio.hidden = false; return; }
      var fr = document.querySelector('[data-r-fonte]');
      fr.appendChild(document.createTextNode('Conferir na fonte: '));
      fr.appendChild(copiar(dig, 'Copiar CNPJ'));
      fr.appendChild(document.createTextNode(' '));
      fr.appendChild(el('a', { href: CNPJ_RECEITA, target: '_blank', rel: 'noopener', text: 'Consulta de CNPJ na Receita ↗' }));
      fr.appendChild(document.createTextNode(' · '));
      fr.appendChild(el('a', { href: PORTAL_EMENDAS, target: '_blank', rel: 'noopener', text: 'Emendas no Portal da Transparência ↗' }));
      if (dados.b) fr.appendChild(el('p', { class: 'nota', text: 'Atenção: este é um banco público que opera repasses de emendas. O dinheiro passa por ele, mas o destino final não é o banco; por isso ele fica fora dos rankings e dos totais por município.' }));
      ligarAno(selA, render);
      lista.hidden = false; render();
    }).catch(function () { vazio.hidden = false; });
  }

  /* ---------- municipios ---------- */
  function iniciarMunicipios(sec) {
    var corpo = document.querySelector('[data-m-corpo]'), mais = document.querySelector('[data-m-mais]'), tit = document.querySelector('[data-m-tit]');
    var filtro = sec.querySelector('[data-m-filtro]'), selA = sec.querySelector('[data-m-ano]'), dados = [], limite = 30;
    function render() {
      var ano = selA.value || '0', q = norm(filtro.value.trim());
      var f = dados.filter(function (m) { return m[2][ano] && (!q || norm(m[0]).indexOf(q) >= 0); })
        .sort(function (a, b) { return b[2][ano][0] - a[2][ano][0]; });
      tit.textContent = q ? f.length + ' municípios encontrados' : 'Municípios que mais receberam' + (selA.value ? ' em ' + selA.value : '');
      corpo.textContent = '';
      f.slice(0, limite).forEach(function (m, i) {
        corpo.appendChild(el('tr', {}, [el('td', { class: 'pos', text: String(i + 1) }),
          el('td', {}, [el('a', { href: RAIZ + 'municipio/?m=' + m[1] + qa(selA.value), text: m[0] })]),
          el('td', { class: 'num', text: String(m[2][ano][1]) }), el('td', { class: 'num', text: brl(m[2][ano][0]) })]));
      });
      mais.hidden = f.length <= limite; mais.textContent = 'Mostrar mais (' + (f.length - limite) + ')';
    }
    mais.addEventListener('click', function () { limite += 50; render(); });
    filtro.addEventListener('input', function () { limite = 30; render(); });
    ligarAno(selA, function () { limite = 30; render(); });
    get('data/municipios.json').then(function (d) { dados = d; render(); });
  }
  function iniciarMunicipio(sec) {
    var m = new URLSearchParams(location.search).get('m') || '';
    var corpo = document.querySelector('[data-mu-corpo]'), vazio = document.querySelector('[data-mu-vazio]'), selA = document.querySelector('[data-mu-ano]');
    var dados = null, pessoas = {};
    if (!/^[a-z0-9-]+$/.test(m)) { vazio.hidden = false; return; }
    function render() {
      var ano = selA.value, d = dados;
      var ps = d.p.map(function (x) { var v = valorAno(x[1], ano); return [x[0], v[0], v[1]]; }).filter(function (x) { return x[1] > 0 || x[2] > 0; })
        .sort(function (a, b) { return b[1] - a[1]; });
      var rs = d.r.map(function (x) { return [x[0], x[1], valorAno(x[2], ano)[0]]; }).filter(function (x) { return x[2] > 0; })
        .sort(function (a, b) { return b[2] - a[2]; });
      var total = ps.reduce(function (s, x) { return s + x[1]; }, 0);
      document.querySelector('[data-mu-info]').textContent = ps.length ? 'Recebedores deste município receberam ' + brl(total) + (ano ? ' em ' + ano : '') + ' em emendas de ' + ps.length +
        (ps.length === 1 ? ' parlamentar.' : ' parlamentares.') : 'Nenhuma emenda paga a recebedores deste município em ' + ano + '.';
      var tp = document.querySelector('[data-mu-parl]'); tp.textContent = '';
      ps.forEach(function (x, i) {
        var p = pessoas[x[0]] || { n: 'Parlamentar', url: '', u: '', p: '' };
        tp.appendChild(el('tr', {}, [el('td', { class: 'pos', text: String(i + 1) }),
          el('td', {}, [p.url ? el('a', { href: RAIZ + p.url, text: p.n }) : document.createTextNode(p.n)]),
          el('td', { text: p.u || '' }), el('td', { text: p.p || '' }), el('td', { class: 'num', text: String(x[2]) }), el('td', { class: 'num', text: brl(x[1]) })]));
      });
      document.querySelector('[data-mu-rec-tit]').textContent = 'Quem recebeu' + (d.nr > d.r.length ? ' (os ' + d.r.length + ' maiores de ' + d.nr + ' no total)' : '');
      var tr = document.querySelector('[data-mu-rec]'); tr.textContent = '';
      rs.slice(0, 200).forEach(function (x, i) {
        tr.appendChild(el('tr', {}, [el('td', { class: 'pos', text: String(i + 1) }),
          el('td', {}, [x[1] ? el('a', { href: RAIZ + 'recebedor/?d=' + encodeURIComponent(x[1]) + qa(selA.value), text: x[0] }) : document.createTextNode(x[0]), el('small', { text: x[1] })]),
          el('td', { class: 'num', text: brl(x[2]) })]));
      });
    }
    Promise.all([get('data/m/' + m + '.json'), carregarBusca()]).then(function (res) {
      dados = res[0];
      res[1].forEach(function (x) { pessoas[x.id] = x; });
      document.querySelector('[data-mu-titulo]').textContent = dados.n;
      document.title = dados.n + ' · emendas recebidas · Gastos Públicos';
      ligarAno(selA, render);
      corpo.hidden = false; render();
    }).catch(function () { vazio.hidden = false; });
  }

  /* ---------- ranking e busca de recebedores ---------- */
  function iniciarRecebedores(sec) {
    var corpo = document.querySelector('[data-rb-corpo]'), tit = document.querySelector('[data-rb-tit]'), filtro = sec.querySelector('[data-rb-filtro]');
    var selA = sec.querySelector('[data-rb-ano]'), modo = 'v', rank = null, indice = null, botoes = document.querySelectorAll('[data-rb-modo]');
    function linha(r, i) {
      return el('tr', {}, [el('td', { class: 'pos', text: String(i + 1) }),
        el('td', {}, [el('a', { href: RAIZ + 'recebedor/?d=' + encodeURIComponent(r[1]) + qa(selA.value), text: r[0] }), el('small', { text: r[1] })]),
        el('td', { class: 'num', text: r[3] === undefined ? '' : String(r[3]) }), el('td', { class: 'num', text: brl(r[2]) })]);
    }
    function render() {
      var q = norm(filtro.value.trim()), qd = q.replace(/\D/g, '');
      corpo.textContent = '';
      if (q.length >= 3) {
        if (!indice) { get('data/rec-busca.json').then(function (d) { indice = d; render(); }); tit.textContent = 'Buscando…'; return; }
        var f = indice.filter(function (r) { return qd.length >= 5 && /^[\d.\/-]+$/.test(q) ? r[1].indexOf(qd) >= 0 : norm(r[0]).indexOf(q) >= 0; });
        tit.textContent = f.length + ' recebedores encontrados (total de todos os anos)' + (f.length > 100 ? ', mostrando os 100 maiores' : '');
        f.slice(0, 100).forEach(function (r, i) { corpo.appendChild(linha(r, i)); });
        return;
      }
      var r_ = rank && rank[selA.value];
      tit.textContent = (modo === 'v' ? 'Quem mais recebeu' : 'Recebeu de mais parlamentares') + (selA.value ? ' em ' + selA.value : '');
      if (r_) r_[modo].forEach(function (r, i) { corpo.appendChild(linha(r, i)); });
    }
    botoes.forEach(function (b) {
      b.addEventListener('click', function () {
        modo = b.getAttribute('data-rb-modo');
        botoes.forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
        render();
      });
    });
    filtro.addEventListener('input', render);
    ligarAno(selA, render);
    get('data/rec-rank.json').then(function (d) { rank = d; render(); });
  }

  document.querySelectorAll('[data-busca]').forEach(function (f) {
    if (f.hasAttribute('data-comparar')) return;
    iniciarBusca(f, function (d) { location.href = RAIZ + d.url; });
  });
  var r = document.querySelector('[data-ranking]'); if (r) iniciarRanking(r);
  document.querySelectorAll('[data-emendas]').forEach(iniciarEmendas);
  var te = document.querySelector('[data-emenda]'); if (te) iniciarTelaEmenda(te);
  var tr_ = document.querySelector('[data-recebedor]'); if (tr_) iniciarTelaRecebedor(tr_);
  var mu = document.querySelector('[data-municipios]'); if (mu) iniciarMunicipios(mu);
  var m1 = document.querySelector('[data-municipio]'); if (m1) iniciarMunicipio(m1);
  var rb = document.querySelector('[data-recebedores]'); if (rb) iniciarRecebedores(rb);
  var px = document.querySelector('[data-pix]'); if (px) iniciarPix(px);
  var c = document.querySelector('[data-comparacao]'); if (c) iniciarComparacao(c, document.querySelector('[data-comparar]'));
})();
