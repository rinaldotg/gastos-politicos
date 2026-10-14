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

  /* ---------- acoes: copiar link e baixar CSV ---------- */
  function baixarCsv(nome, cab, linhas) {
    var esc = function (v) { v = v === null || v === undefined ? '' : String(v); return /[;"\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var txt = '﻿' + [cab].concat(linhas).map(function (l) { return l.map(esc).join(';'); }).join('\r\n');
    var a = el('a', { href: URL.createObjectURL(new Blob([txt], { type: 'text/csv;charset=utf-8' })), download: nome });
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }
  // csvs: [[rotulo, arquivo, function () { return [cabecalho, linhas]; }]]
  function acoes(box, csvs) {
    if (!box) return;
    box.textContent = '';
    var link = el('button', { type: 'button', class: 'botao botao-leve botao-mini', text: 'Copiar link desta página' });
    link.addEventListener('click', function () {
      var ok = function () { link.textContent = 'Link copiado ✓'; setTimeout(function () { link.textContent = 'Copiar link desta página'; }, 1800); };
      if (navigator.clipboard) navigator.clipboard.writeText(location.href).then(ok, function () {});
    });
    box.appendChild(link);
    (csvs || []).forEach(function (c) {
      var b = el('button', { type: 'button', class: 'botao botao-leve botao-mini', text: c[0] });
      b.addEventListener('click', function () { var d = c[2](); baixarCsv(c[1], d[0], d[1]); });
      box.appendChild(b);
    });
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
    acoes(box.querySelector('[data-acoes]'), [['Baixar emendas (CSV)', 'emendas-' + id + '.csv', function () {
      return [['ano', 'tipo', 'numero', 'codigo', 'destino', 'area', 'subarea', 'programa', 'acao', 'empenhado', 'liquidado', 'pago'],
        filtradas().map(function (l) { return [l[0], l[1] ? 'Pix' : 'Finalidade definida', l[2], l[3], l[4], l[5], l[6], l[7], l[8], l[9], l[10], l[11]]; })];
    }]]);
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
      if (i[8] || i[9]) info.appendChild(el('p', { class: 'nota', text: 'Finalidade informada na emenda: ' + [i[5], i[8], i[9]].filter(Boolean).join(' · ') + '. Isso indica a intenção do repasse; não comprova como o recebedor usou o dinheiro.' }));
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
      acoes(document.querySelector('[data-acoes]'), [['Baixar recebedores (CSV)', 'emenda-' + cod + '.csv', function () {
        return [['recebedor', 'cnpj', 'tipo', 'local', 'valor'], linhas.map(function (r) { return [r[0], r[1], r[2], r[3], r[4]]; })];
      }]]);
      var nomeP = p ? p.n : 'o parlamentar', rec1 = linhas.length ? linhas[0][0] : 'o recebedor';
      var mod = 'Prezados,\n\nCom base na Lei de Acesso à Informação (Lei nº 12.527/2011), solicito informações sobre a emenda parlamentar ' +
        (i[3] ? 'nº ' + i[3] + ' ' : '') + 'de ' + i[1] + ' (código ' + cod + '), de autoria de ' + nomeP + ', com destino a ' + (i[4] || 'localidade não informada') +
        ', cujo recebedor principal consta como ' + rec1 + '.\n\nGostaria de saber: (1) o objeto e a finalidade do recurso; (2) a situação atual da execução, com cronograma; ' +
        '(3) os valores recebidos e gastos até o momento; (4) onde posso consultar a prestação de contas.\n\nAgradeço desde já.';
      var tx = document.querySelector('[data-e-modelo]'); tx.value = mod.replace(/\\n/g, '\n');
      var ac = document.querySelector('[data-e-modelo-acoes]'); ac.appendChild(copiar(tx.value, 'Copiar modelo'));
      document.querySelector('[data-e-cobrar]').hidden = false;
      lista.querySelector('[data-e-cont]').textContent = linhas.length + ' recebedores';
      lista.hidden = false; render();
    }).catch(function () { vazio.hidden = false; });
  }


  function blocoObras(box, resumoEl, corpoEl, ob, comExecutor) {
    var cont = ob[0] || {}, lista = ob[1] || [], n = Object.keys(cont).reduce(function (s, k) { return s + cont[k]; }, 0);
    if (!n) return;
    resumoEl.textContent = n + (n === 1 ? ' obra: ' : ' obras: ') + Object.keys(cont).sort(function (a, b) { return cont[b] - cont[a]; }).map(function (k) { return cont[k] + ' ' + k.toLowerCase(); }).join(', ') + '.' + (n > lista.length ? ' Mostrando as ' + lista.length + ' primeiras.' : '');
    corpoEl.textContent = '';
    lista.forEach(function (o) {
      var cols = [el('td', {}, [document.createTextNode(o[1] || '(sem nome)'), el('small', { text: 'Código ' + o[0] + (o[3] ? ' · ' + o[3] : '') })])];
      if (comExecutor) cols.push(el('td', { text: o[8] || '' }));
      cols.push(el('td', {}, [el('span', { class: 'sit ' + (o[2] === 'Paralisada' ? 'sit-alerta' : ''), text: o[2] })]));
      if (!comExecutor) cols.push(el('td', { text: o[3] || '' }));
      cols.push(el('td', { class: 'num', text: o[4] ? brl(o[4]) : '—' }));
      if (!comExecutor) cols.push(el('td', { text: o[5] || '—' }));
      corpoEl.appendChild(el('tr', {}, cols));
    });
    box.hidden = false;
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
      var areas = {};
      linhas.forEach(function (x) { x[2].forEach(function (e) { var k = e[5] || 'Não informada'; areas[k] = (areas[k] || 0) + e[3]; }); });
      var ar = document.querySelector('[data-r-areas]');
      if (ar) {
        var lst = Object.keys(areas).sort(function (a, b) { return areas[b] - areas[a]; });
        ar.textContent = lst.length ? 'Áreas informadas nas emendas: ' + lst.slice(0, 6).map(function (k) { return k + ' (' + brl(areas[k]) + ')'; }).join(' · ') + '.' : '';
      }
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
      var pub = document.querySelector('[data-r-publico]');
      if (pub && !dados.b && /\b(FUNDO|PREFEITURA|MUNICIPIO|MUNICÍPIO|SECRETARIA|ESTADO|GOVERNO|CAMARA|CÂMARA)\b/i.test(dados.n)) {
        pub.hidden = false;
        if (/FUNDO/i.test(dados.n)) pub.querySelector('[data-r-publico-fundo]').hidden = false;
      }
      if (dados.b) fr.appendChild(el('p', { class: 'nota', text: 'Atenção: este é um banco público que opera repasses de emendas. O dinheiro passa por ele, mas o destino final não é o banco; por isso ele fica fora dos rankings e dos totais por município.' }));
      blocoObras(document.querySelector('[data-r-obras]'), document.querySelector('[data-r-obras-resumo]'), document.querySelector('[data-r-obras-corpo]'), dados.ob || [{}, []], false);
      ligarAno(selA, render);
      acoes(document.querySelector('[data-acoes]'), [['Baixar CSV (filtro atual)', 'recebedor-' + dig + '.csv', function () {
        var ano = selA.value, out = [];
        dados.p.forEach(function (x) {
          var p = pessoas[x[0]] || { n: '', u: '', p: '' };
          x[2].forEach(function (e) { if (!ano || String(e[4]) === ano) out.push([p.n, p.u, p.p, e[0], e[1], e[2] ? 'Pix' : 'Individual', e[4] || '', e[3]]); });
        });
        return [['parlamentar', 'uf', 'partido', 'codigo_emenda', 'ano_emenda', 'tipo', 'ano_pagamento', 'valor'], out];
      }]]);
      lista.hidden = false; render();
    }).catch(function () { vazio.hidden = false; });
  }

  /* ---------- cota mes a mes ---------- */
  var MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  function iniciarMeses(sec) {
    var pid = sec.getAttribute('data-pid'), selA = sec.querySelector('[data-pm-ano]'), corpo = sec.querySelector('[data-pm-corpo]'), dados = {};
    function linhasAno(ano) {
      var m = dados[ano] || {};
      return Object.keys(m).map(Number).sort(function (a, b) { return a - b; }).map(function (n) {
        var cats = Object.keys(m[n]).map(function (c) { return [c, m[n][c]]; }).sort(function (a, b) { return b[1] - a[1]; });
        return { n: n, cats: cats, total: cats.reduce(function (s, c) { return s + c[1]; }, 0) };
      });
    }
    function render() {
      var ano = selA.value, ls = linhasAno(ano), tot = ls.reduce(function (s, l) { return s + l.total; }, 0);
      sec.querySelector('[data-pm-resumo]').textContent = ls.length ?
        'Em ' + ano + ': ' + brl(tot) + ' em ' + ls.length + (ls.length === 1 ? ' mês' : ' meses') + ' com despesas (média de ' + brl(tot / ls.length) + ' por mês).' :
        'Sem despesas registradas em ' + ano + '.';
      corpo.textContent = '';
      ls.forEach(function (l) {
        var tr = el('tr', {}, [el('td', {}, [el('details', { class: 'rec-mais' }, [el('summary', { text: MESES[l.n - 1] || String(l.n) })].concat(
          l.cats.map(function (c) { return el('div', { class: 'rec' }, [el('span', { text: c[0] }), el('small', { text: brl(c[1]) })]); })))]),
          el('td', { class: 'num', text: brl(l.total) }), el('td', { class: 'num', text: l.cats[0] ? l.cats[0][0] : '' })]);
        corpo.appendChild(tr);
      });
    }
    get('data/pm/' + pid + '.json').then(function (d) {
      dados = d; selA.addEventListener('change', render); render();
      acoes(sec.querySelector('[data-acoes]'), [['Baixar mês a mês (CSV)', 'cota-mensal-' + pid + '.csv', function () {
        var out = [];
        Object.keys(dados).sort().forEach(function (a) { linhasAno(a).forEach(function (l) { l.cats.forEach(function (c) { out.push([a, l.n, c[0], c[1]]); }); }); });
        return [['ano', 'mes', 'tipo_de_despesa', 'valor'], out];
      }]]);
    }).catch(function () { sec.hidden = true; });
  }

  /* ---------- municipios ---------- */
  function iniciarMunicipios(sec) {
    var corpo = document.querySelector('[data-m-corpo]'), mais = document.querySelector('[data-m-mais]'), tit = document.querySelector('[data-m-tit]');
    var filtro = sec.querySelector('[data-m-filtro]'), selA = sec.querySelector('[data-m-ano]'), dados = [], limite = 30, atuais = [];
    function render() {
      var ano = selA.value || '0', q = norm(filtro.value.trim());
      var f = dados.filter(function (m) { return m[2][ano] && (!q || norm(m[0]).indexOf(q) >= 0); })
        .sort(function (a, b) { return b[2][ano][0] - a[2][ano][0]; });
      atuais = f;
      tit.textContent = q ? f.length + ' municípios encontrados' : 'Municípios que mais receberam' + (selA.value ? ' em ' + selA.value : '');
      corpo.textContent = '';
      f.slice(0, limite).forEach(function (m, i) {
        corpo.appendChild(el('tr', {}, [el('td', { class: 'pos', text: String(i + 1) }),
          el('td', {}, [el('a', { href: RAIZ + 'municipio/?m=' + m[1] + qa(selA.value), text: m[0] })]),
          el('td', { class: 'num', text: String(m[2][ano][1]) }), el('td', { class: 'num', text: brl(m[2][ano][0]) }),
          el('td', { class: 'num', text: m[3] ? brl(m[2][ano][0] / m[3]) : '—' })]));
      });
      mais.hidden = f.length <= limite; mais.textContent = 'Mostrar mais (' + (f.length - limite) + ')';
    }
    mais.addEventListener('click', function () { limite += 50; render(); });
    filtro.addEventListener('input', function () { limite = 30; render(); });
    ligarAno(selA, function () { limite = 30; render(); });
    acoes(document.querySelector('[data-acoes]'), [['Baixar lista (CSV)', 'municipios.csv', function () {
      var ano = selA.value || '0';
      return [['municipio', 'parlamentares', 'total_recebido'], atuais.map(function (m) { return [m[0], m[2][ano][1], m[2][ano][0]]; })];
    }]]);
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
      document.querySelector('[data-mu-info]').textContent = (ps.length ? 'Recebedores deste município receberam ' + brl(total) + (ano ? ' em ' + ano : '') + ' em emendas de ' + ps.length +
        (ps.length === 1 ? ' parlamentar.' : ' parlamentares.') : 'Nenhuma emenda paga a recebedores deste município em ' + ano + '.') +
        (d.pop && total ? ' Isso dá ' + brl(total / d.pop) + ' por habitante (população estimada de ' + d.pop.toLocaleString('pt-BR') + ').' : '');
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
      blocoObras(document.querySelector('[data-mu-obras]'), document.querySelector('[data-mu-obras-resumo]'), document.querySelector('[data-mu-obras-corpo]'), dados.ob || [{}, []], true);
      ligarAno(selA, render);
      var linhasMu = function () {
        var ano = selA.value;
        var ps = dados.p.map(function (x) { var v = valorAno(x[1], ano), p = pessoas[x[0]] || { n: '', u: '', p: '' }; return [p.n, p.u, p.p, v[1], v[0]]; }).filter(function (x) { return x[4] > 0; });
        var rs = dados.r.map(function (x) { return [x[0], x[1], valorAno(x[2], ano)[0]]; }).filter(function (x) { return x[2] > 0; });
        return [ps, rs];
      };
      acoes(document.querySelector('[data-acoes]'), [
        ['Baixar parlamentares (CSV)', 'municipio-' + m + '-parlamentares.csv', function () { return [['parlamentar', 'uf', 'partido', 'emendas', 'valor'], linhasMu()[0]]; }],
        ['Baixar recebedores (CSV)', 'municipio-' + m + '-recebedores.csv', function () { return [['recebedor', 'cnpj', 'valor'], linhasMu()[1]]; }]]);
      corpo.hidden = false; render();
    }).catch(function () { vazio.hidden = false; });
  }

  /* ---------- ranking e busca de recebedores ---------- */
  function iniciarRecebedores(sec) {
    var corpo = document.querySelector('[data-rb-corpo]'), tit = document.querySelector('[data-rb-tit]'), filtro = sec.querySelector('[data-rb-filtro]');
    var selA = sec.querySelector('[data-rb-ano]'), modo = 'v', rank = null, indice = null, mostrados = [], botoes = document.querySelectorAll('[data-rb-modo]');
    function linha(r, i) {
      return el('tr', {}, [el('td', { class: 'pos', text: String(i + 1) }),
        el('td', {}, [el('a', { href: RAIZ + 'recebedor/?d=' + encodeURIComponent(r[1]) + qa(selA.value), text: r[0] }), el('small', { text: r[1] })]),
        el('td', { class: 'num', text: r[3] === undefined ? '' : String(r[3]) }), el('td', { class: 'num', text: brl(r[2]) })]);
    }
    function render() {
      var q = norm(filtro.value.trim()), qd = q.replace(/\D/g, '');
      corpo.textContent = ''; mostrados = [];
      if (q.length >= 3) {
        if (!indice) { get('data/rec-busca.json').then(function (d) { indice = d; render(); }); tit.textContent = 'Buscando…'; return; }
        var f = indice.filter(function (r) { return qd.length >= 5 && /^[\d.\/-]+$/.test(q) ? r[1].indexOf(qd) >= 0 : norm(r[0]).indexOf(q) >= 0; });
        tit.textContent = f.length + ' recebedores encontrados (total de todos os anos)' + (f.length > 100 ? ', mostrando os 100 maiores' : '');
        mostrados = f.slice(0, 100);
        f.slice(0, 100).forEach(function (r, i) { corpo.appendChild(linha(r, i)); });
        return;
      }
      var r_ = rank && rank[selA.value];
      tit.textContent = (modo === 'v' ? 'Quem mais recebeu' : 'Recebeu de mais parlamentares') + (selA.value ? ' em ' + selA.value : '');
      if (r_) { mostrados = r_[modo]; r_[modo].forEach(function (r, i) { corpo.appendChild(linha(r, i)); }); }
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
    acoes(document.querySelector('[data-acoes]'), [['Baixar lista atual (CSV)', 'recebedores.csv', function () {
      return [['recebedor', 'cnpj', 'total', 'parlamentares'], mostrados.map(function (r) { return [r[0], r[1], r[2], r[3] === undefined ? '' : r[3]]; })];
    }]]);
    get('data/rec-rank.json').then(function (d) { rank = d; render(); });
  }


  /* ---------- pagina de estado ---------- */
  function iniciarEstado(sec) {
    var dados = JSON.parse(document.querySelector('[data-es-dados]').textContent), selA = sec.querySelector('[data-es-ano]');
    var nomeUf = sec.querySelector('h1').textContent;
    function soma(m, ano) { var t = 0; Object.keys(m).forEach(function (k) { if (!ano || k === ano) t += m[k]; }); return t; }
    function tabela(tipo, ano) {
      var box = document.querySelector('[data-es-' + tipo + ']'), corpo = document.querySelector('[data-es-' + tipo + '-corpo]');
      var xs = dados.p.filter(function (x) { return x[3] === (tipo === 'deps' ? 'd' : 's'); })
        .map(function (x) { return [x, soma(x[4], ano), soma(x[5], ano)]; })
        .filter(function (t) { return t[1] > 0 || t[2] > 0; })
        .sort(function (a, b) { return b[1] - a[1]; });
      box.hidden = !xs.length;
      document.querySelector('[data-es-' + tipo + '-tit]').textContent = (tipo === 'deps' ? 'Deputados federais' : 'Senadores') + ' (' + xs.length + ')';
      var rotCota = 'Cota ' + (ano ? 'em ' + ano : 'paga (todos os anos)'), rotEm = 'Emendas pagas ' + (ano ? '(emendas de ' + ano + ')' : '(desde 2014)');
      (tipo === 'deps' ? [['[data-es-col-cota]', rotCota], ['[data-es-col-em]', rotEm]] : [['[data-es-col-cota2]', rotCota], ['[data-es-col-em2]', rotEm]])
        .forEach(function (c) { document.querySelector(c[0]).textContent = c[1]; });
      corpo.textContent = '';
      xs.forEach(function (t) {
        corpo.appendChild(el('tr', {}, [el('td', {}, [el('a', { href: RAIZ + t[0][1], text: t[0][0] })]), el('td', { text: t[0][2] }),
          el('td', { class: 'num', text: brl(t[1]) }), el('td', { class: 'num', text: brl(t[2]) })]));
      });
    }
    function areas(ano) {
      var lista = dados.a[ano] || [], box = document.querySelector('[data-es-areas]'), total = lista.reduce(function (s, a) { return s + a[1]; }, 0);
      document.querySelector('[data-es-areas-tit]').textContent = 'Emendas pagas para ' + nomeUf + ', por área' + (ano ? ' (emendas de ' + ano + ')' : '');
      document.querySelector('[data-es-areas-intro]').textContent = lista.length ? 'Soma de ' + brl(total) + ' pagos em emendas individuais de parlamentares identificados, de qualquer estado, com destino a ' + nomeUf + '. Abra uma área para ver os municípios que mais receberam.' : 'Sem emendas pagas para este estado' + (ano ? ' em ' + ano : '') + '.';
      box.textContent = '';
      var max = lista.length ? lista[0][1] : 1;
      lista.forEach(function (a) {
        var d = el('details', { class: 'ano area' }, [el('summary', {}, [el('span', { class: 'ano-n area-n', text: a[0] }),
          el('span', { class: 'ano-barra', 'aria-hidden': 'true' }, [el('i', { style: 'width:' + (a[1] / max * 100).toFixed(1) + '%' })]),
          el('span', { class: 'ano-v', text: brl(a[1]) + ' pagos' })])]);
        var corpo = el('tbody');
        if (a[4].length) a[4].forEach(function (m) { corpo.appendChild(el('tr', {}, [el('td', { text: m[0] }), el('td', { class: 'num', text: brl(m[1]) })])); });
        else corpo.appendChild(el('tr', {}, [el('td', { colspan: '2', text: 'Nenhum município específico informado na fonte.' })]));
        d.appendChild(el('div', { class: 'tabela-rolavel' }, [el('table', { class: 'tabela' }, [el('thead', {}, [el('tr', {}, [el('th', { text: 'Município' }), el('th', { class: 'num', text: 'Pago' })])]), corpo])]));
        d.appendChild(el('p', { class: 'nota', text: a[3] + ' emendas nesta área; ' + brl(a[2]) + ' empenhados.' + (a[5] ? ' Mais ' + brl(a[5]) + ' foram para vários municípios de uma vez ou sem município informado na fonte, e por isso não aparecem na lista.' : '') }));
        box.appendChild(d);
      });
    }
    function render() { var ano = selA.value; tabela('deps', ano); tabela('sens', ano); areas(ano); }
    ligarAno(selA, render);
    render();
  }

  document.querySelectorAll('[data-busca]').forEach(function (f) {
    if (f.hasAttribute('data-comparar')) return;
    iniciarBusca(f, function (d) { location.href = RAIZ + d.url; });
  });
  document.querySelectorAll('[data-uf-select]').forEach(function (s) { s.addEventListener('change', function () { if (s.value) location.href = RAIZ + 'estado/' + s.value + '/'; }); });
  var es = document.querySelector('[data-estado]'); if (es) iniciarEstado(es);
  var r = document.querySelector('[data-ranking]'); if (r) iniciarRanking(r);
  document.querySelectorAll('[data-emendas]').forEach(iniciarEmendas);
  var te = document.querySelector('[data-emenda]'); if (te) iniciarTelaEmenda(te);
  var pm_ = document.querySelector('[data-pm]'); if (pm_) iniciarMeses(pm_);
  var tr_ = document.querySelector('[data-recebedor]'); if (tr_) iniciarTelaRecebedor(tr_);
  var mu = document.querySelector('[data-municipios]'); if (mu) iniciarMunicipios(mu);
  var m1 = document.querySelector('[data-municipio]'); if (m1) iniciarMunicipio(m1);
  var rb = document.querySelector('[data-recebedores]'); if (rb) iniciarRecebedores(rb);
  var px = document.querySelector('[data-pix]'); if (px) iniciarPix(px);
  var c = document.querySelector('[data-comparacao]'); if (c) iniciarComparacao(c, document.querySelector('[data-comparar]'));
})();
