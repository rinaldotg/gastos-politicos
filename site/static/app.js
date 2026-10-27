(function () {
  'use strict';
  var RAIZ = document.body.getAttribute('data-raiz') || '';
  var CARGO_ROTULO = { deputado: 'Deputado federal', senador: 'Senador', presidente: 'Presidente', m: 'Cidade (emendas recebidas)' };

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
    var input = form.querySelector('input'), lista = form.querySelector('ul'), itens = [], ativo = -1, comM = form.hasAttribute('data-com-municipios'), soParl = form.hasAttribute('data-so-parlamentares');
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
        itens = dados.filter(function (d) { return (comM || d.c !== 'm') && (!soParl || d.c === 'deputado' || d.c === 'senador') && partes.every(function (p) { return d.a.indexOf(p) >= 0; }); })
          .sort(function (a, b) { return (a.a.indexOf(partes[0]) === 0 ? 0 : 1) - (b.a.indexOf(partes[0]) === 0 ? 0 : 1) || a.n.localeCompare(b.n); })
          .slice(0, 8);
        lista.textContent = '';
        if (!itens.length) { lista.appendChild(el('li', { text: comM ? 'Nenhum parlamentar ou cidade encontrado' : 'Nenhum nome encontrado' })); }
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
    form.addEventListener('submit', function (ev) { ev.preventDefault(); if (!lista.hidden && itens.length) escolher(ativo >= 0 ? ativo : 0); });
    input.addEventListener('blur', function () { setTimeout(fechar, 120); });
  }

  /* ---------- ranking da home ---------- */
  function iniciarRanking(sec) {
    var selC = sec.querySelector('[data-r-cargo]'), selA = sec.querySelector('[data-r-ano]'), corpo = sec.querySelector('tbody');
    var selU = sec.querySelector('[data-r-uf]'), selP = sec.querySelector('[data-r-partido]'), selO = sec.querySelector('[data-r-ordem]');
    var maisBtn = null, dados = null, limite = 25;
    function render() {
      if (!dados) return;
      var todas = (dados[selC.value] || {})[selA.value] || [];
      opcoes(selU, todas, 2, 'Todos os estados'); opcoes(selP, todas, 3, 'Todos os partidos');
      var linhas = todas.filter(function (r) { return (!selU.value || r[2] === selU.value) && (!selP.value || r[3] === selP.value); });
      var porMes = selO && selO.value === 'mes', v = function (r) { return porMes ? (r[5] ? r[4] / r[5] : 0) : r[4]; };
      linhas = linhas.slice().sort(function (x, y) { return v(y) - v(x); });
      corpo.textContent = '';
      var maxv = linhas.length ? Math.max(1, v(linhas[0])) : 1;
      linhas.slice(0, limite).forEach(function (r, i) {
        corpo.appendChild(el('tr', {}, [
          el('td', { class: 'pos', text: String(i + 1) }),
          el('td', {}, [el('a', { href: RAIZ + r[1], text: r[0] })]),
          el('td', { text: r[2] }), el('td', { text: r[3] }),
          el('td', { class: 'num' }, [document.createTextNode(brl(porMes ? v(r) : r[4]) + (porMes ? '/mês' : '')), el('span', { class: 'barra-gasto' }, [el('i', { 'data-w': String(Math.max(2, Math.round(v(r) / maxv * 100))), style: 'width:0' })])]),
          el('td', { class: 'num', text: String(r[5]) })
        ]));
      });
      if (!linhas.length) corpo.appendChild(el('tr', {}, [el('td', { colspan: '6', text: 'Sem dados para este filtro.' })]));
      requestAnimationFrame(function () { requestAnimationFrame(function () { corpo.querySelectorAll('.barra-gasto i').forEach(function (b) { b.style.width = b.getAttribute('data-w') + '%'; }); }); });
      if (maisBtn) maisBtn.remove();
      if (linhas.length > limite) {
        maisBtn = el('button', { class: 'botao botao-leve', type: 'button', text: 'Mostrar mais (' + (linhas.length - limite) + ')' });
        maisBtn.addEventListener('click', function () { limite += 50; render(); });
        sec.querySelector('.tabela-rolavel').after(maisBtn);
      }
    }
    function opcoes(sel, linhas, i, vazio) {
      if (!sel) return; var atual = sel.value, set = {};
      linhas.forEach(function (r) { if (r[i]) set[r[i]] = 1; });
      var ks = Object.keys(set).sort(); if (atual && !set[atual]) atual = '';
      sel.innerHTML = '<option value="">' + vazio + '</option>' + ks.map(function (k) { return '<option>' + k.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</option>'; }).join('');
      sel.value = atual;
    }
    get('data/ranking.json').then(function (d) { dados = d; render(); });
    [selC, selA, selU, selP, selO].forEach(function (s) { if (s) s.addEventListener('change', function () { limite = 25; render(); }); });
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
      var soPres = pessoas.every(function (p) { return p.c === 'presidente' && p.m; });
      if (soPres) {
        corpo.appendChild(linha('Total no mandato', totais, 'total', false));
        corpo.appendChild(el('tr', {}, [el('td', { class: 'rotulo', text: 'Meses nos dados' })].concat(pessoas.map(function (p) { return el('td', { class: 'num', text: String(p.m[0]) }); }))));
        corpo.appendChild(linha('Gasto por mês', pessoas.map(function (p, i) { return totais[i] / p.m[0]; }), 'total'));
        var somaM = {};
        pessoas.forEach(function (p) { Object.keys(p.anos).forEach(function (a) { p.anos[a][2].forEach(function (c) { somaM[c[0]] = (somaM[c[0]] || 0) + c[1]; }); }); });
        Object.keys(somaM).sort(function (x, y) { return somaM[y] - somaM[x]; }).forEach(function (cat) {
          corpo.appendChild(linha(cat, pessoas.map(function (p) {
            var t = 0, ach = false;
            Object.keys(p.anos).forEach(function (a) { p.anos[a][2].forEach(function (c) { if (c[0] === cat) { t += c[1]; ach = true; } }); });
            return ach ? t : null;
          }), 'cat-linha'));
        });
        wrap.textContent = '';
        wrap.appendChild(el('table', { class: 'tabela comp' }, [el('thead', {}, [cab]), corpo]));
        return;
      }
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
        if (dest[k] <= 0) return;
        var sl_ = slug(k.replace('/', '-')), nome_ = [locLink(k)];
        if (TCE && TCE[sl_]) nome_.push(el('small', {}, [document.createTextNode(' · '), el('a', { href: RAIZ + 'municipio/?m=' + sl_ + '#tce', text: 'ver onde a prefeitura gastou' })]));
        destinos.appendChild(el('li', {}, [el('span', {}, nome_), el('span', { class: 'num', text: brl(dest[k]) })]));
      });
    }
    box.addEventListener('tce', function () { if (linhas.length) render(); });
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
  var ROTULO_CLASSE = { publico: 'Ente público ou fundo', empresa: 'Empresa privada', entidade: 'Entidade sem fins lucrativos', privado_outro: 'Entidade privada (tipo não identificado)', pf: 'Pessoa física', banco: 'Banco público (intermediário)' };
  function ehPriv(c) { return c === 'empresa' || c === 'entidade' || c === 'privado_outro'; }
  function chipClasse(c, sanc) {
    if (!ehPriv(c) && !(sanc && sanc.length)) return document.createTextNode('');
    var out = [];
    if (ehPriv(c)) out.push(el('span', { class: 'chip chip-priv', text: ROTULO_CLASSE[c] }));
    if (sanc && sanc.length) out.push(el('span', { class: 'chip alerta', title: 'Consta em cadastro de sanções do Portal da Transparência', text: '⚠ cadastro de sanções: ' + sanc[0][0] }));
    return el('span', {}, out);
  }
  var TCE = null;
  function carregarTce() {
    if (TCE) return Promise.resolve(TCE);
    return get('data/tce-lista.json').then(function (t) { TCE = t; return t; }).catch(function () { TCE = {}; return TCE; });
  }
  var RE_PUBLICO = /\b(FUNDO|PREFEITURA|MUNICIPIO|MUNICÍPIO|SECRETARIA|ESTADO|GOVERNO|CAMARA|CÂMARA)\b/i;
  function trilhaEmenda(box, d, p, cod, linhas, cs) {
    var i = d.i, tot = linhas.reduce(function (s, r) { return s + r[4]; }, 0), pub = 0, nPub = 0, priv = 0, nPriv = 0, nSanc = 0;
    linhas.forEach(function (r) {
      if (r[5] === 'publico' || (!r[5] && RE_PUBLICO.test(r[0]))) { pub += r[4]; nPub++; }
      if (ehPriv(r[5])) { priv += r[4]; nPriv++; }
      if (r[6]) nSanc++;
    });
    var autor = p ? p.n : 'o parlamentar', fim = [];
    var passos = [
      ['1. Origem', autor + ' indicou esta emenda ' + (i[2] ? '(Pix, transferência especial)' : '(individual, com finalidade definida)') + ' no orçamento de ' + i[1] + '. Empenhado: ' + brl(i[6]) + ' · pago: ' + brl(i[7]) + '.'],
      ['2. Finalidade declarada', ([i[5], i[8], i[9]].filter(Boolean).join(' · ') || 'a fonte não informa a finalidade') + (i[4] ? '. Destino: ' + i[4] : '') + '. É a intenção do repasse, não a prova do uso.'],
      ['3. Quem recebeu', linhas.length ? (linhas.length + (linhas.length === 1 ? ' recebedor' : ' recebedores') + ', ' + brl(tot) + ' pagos. ' +
        (nPub ? brl(pub) + ' foram para entes públicos ou fundos (prefeitura, secretaria, fundo): ali o rastreio federal termina. ' : 'Nenhum é prefeitura ou fundo pelo nome. ') +
        (nPriv ? brl(priv) + ' (' + (tot ? Math.round(priv / tot * 100) : 0) + '%) foram direto para ' + nPriv + (nPriv === 1 ? ' empresa ou entidade privada' : ' empresas ou entidades privadas') + ' (marcadas na lista abaixo).' : 'Nada foi pago direto a empresa ou entidade privada.') +
        (nSanc ? ' ATENÇÃO: ' + nSanc + (nSanc === 1 ? ' recebedor consta' : ' recebedores constam') + ' em cadastro de sanções.' : '')) : 'Sem pagamento registrado ainda.'],
      ['4. Execução', cs.length ? ('Há ' + cs.length + (cs.length === 1 ? ' convênio' : ' convênios') + ' registrado: veja objeto, valores e vigência logo abaixo.') :
        (i[2] ? 'Emenda Pix não exige convênio nem projeto prévio: não há contrato federal para acompanhar.' : 'Sem convênio registrado na fonte.')],
      ['5. A partir daqui', nPub ? 'O gasto é do município ou estado. Procure o empenho no portal de transparência dele, consulte SIOPS (saúde) ou SIOPE (educação) e o Tribunal de Contas do estado; ou use o modelo de pedido no fim desta página.' :
        'Peça ao recebedor o objeto, a prestação de contas e as notas fiscais; o modelo de pedido está no fim desta página.']
    ];
    var ol = box.querySelector('[data-e-trilha-passos]'), vistos = {}, ligas = [];
    linhas.forEach(function (r) {
      var sl = slug((r[3] || '').replace('/', '-'));
      if (TCE && TCE[sl] && !vistos[sl] && ligas.length < 3) { vistos[sl] = 1; ligas.push(el('a', { href: RAIZ + 'municipio/?m=' + sl + '#tce', text: 'Despesa de ' + r[3] + ' (TCE-SP) →' })); }
    });
    passos.forEach(function (x, n) {
      var li = el('li', {}, [el('strong', { text: x[0] + ' — ' }), document.createTextNode(x[1])]);
      if (n === 4 && ligas.length) { li.appendChild(document.createTextNode(' Neste caso já dá para ver para onde o município gastou: ')); ligas.forEach(function (a, j) { if (j) li.appendChild(document.createTextNode(' · ')); li.appendChild(a); }); }
      ol.appendChild(li);
    });
    box.hidden = false;
  }
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
          el('td', {}, [nome, chipClasse(r[5], r[6] ? [['sanção']] : null), el('small', { text: r[1] })]), el('td', { text: r[2] }), el('td', {}, [locLink(r[3])]),
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
      carregarTce().then(function () { trilhaEmenda(document.querySelector('[data-e-trilha]'), d, p, cod, linhas, cs); });
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
      var pv = document.querySelector('[data-r-priv]');
      if (pv && !dados.b && (ehPriv(dados.g) || (dados.s && dados.s.length))) {
        pv.hidden = false;
        pv.querySelector('[data-r-priv-tipo]').textContent = (ROTULO_CLASSE[dados.g] || 'Recebedor') + ' (classificação pelo nome; pode haver erro).';
        var al = pv.querySelector('[data-r-priv-sanc]');
        if (dados.s && dados.s.length) {
          al.hidden = false;
          al.textContent = 'Consta em cadastro de sanções do Portal da Transparência: ' + dados.s.map(function (x) { return x[0] + (x[1] ? ' (' + x[1] + ')' : '') + (x[2] ? ', desde ' + x[2] : '') + (x[3] ? ' até ' + x[3] : '') + (x[4] ? ', órgão: ' + x[4] : ''); }).join('; ') + '. Confira as datas: a sanção pode ser posterior ou anterior ao pagamento.';
        }
      }
      var pub = document.querySelector('[data-r-publico]');
      if (pub && !dados.b && !ehPriv(dados.g) && /\b(FUNDO|PREFEITURA|MUNICIPIO|MUNICÍPIO|SECRETARIA|ESTADO|GOVERNO|CAMARA|CÂMARA)\b/i.test(dados.n)) {
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
      if (ls.length) {
        var cat = {};
        ls.forEach(function (l) { l.cats.forEach(function (c) { cat[c[0]] = (cat[c[0]] || 0) + c[1]; }); });
        var top = Object.keys(cat).sort(function (a, b) { return cat[b] - cat[a]; })[0];
        corpo.appendChild(el('tr', { class: 'total' }, [el('td', { text: 'Total em ' + ano }), el('td', { class: 'num', text: brl(tot) }), el('td', { class: 'num', text: top || '' })]));
      }
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

  /* ---------- privados ---------- */
  function iniciarPrivados(sec) {
    var anoSel = sec.querySelector('[data-v-ano]'), aba = sec.querySelector('[data-v-aba]'), tipo = sec.querySelector('[data-v-tipo]'), uf = sec.querySelector('[data-v-uf]'), sanc = sec.querySelector('[data-v-sanc]'), q = sec.querySelector('[data-v-q]');
    var cab = document.querySelector('[data-v-cab]'), corpo = document.querySelector('[data-v-corpo]'), mais = document.querySelector('[data-v-mais]');
    var dados = null, limite = 50, atuais = [];
    function render() {
      if (!dados) return;
      var nq = norm(q.value.trim()), rec = aba.value === 'rec', lista;
      sec.querySelectorAll('[data-v-tipo]').forEach(function (x) { x.parentNode.hidden = !rec; });
      sanc.parentNode.hidden = !rec;
      cab.textContent = ''; corpo.textContent = '';
      if (rec) {
        cab.appendChild(el('tr', {}, [el('th', { text: 'Recebedor' }), el('th', { text: 'Local' }), el('th', { class: 'num', text: 'Parlamentares' }), el('th', { class: 'num', text: 'Total recebido' })]));
        lista = dados.rec.filter(function (r) {
          return (!tipo.value || r[2] === tipo.value) && (!uf.value || (r[5] || '').slice(-2) === uf.value) && (!sanc.checked || r[6].length) &&
            (!nq || norm(r[0] + ' ' + r[1]).indexOf(nq) >= 0);
        });
        lista.slice(0, limite).forEach(function (r) {
          corpo.appendChild(el('tr', {}, [el('td', {}, [el('a', { href: RAIZ + 'recebedor/?d=' + encodeURIComponent(r[1]), text: r[0] }), chipClasse(r[2], r[6].length ? r[6] : null), el('small', { text: r[1] })]),
            el('td', {}, [locLink(r[5])]), el('td', { class: 'num', text: String(r[4]) }), el('td', { class: 'num', text: brl(r[3]) })]));
        });
      } else {
        cab.appendChild(el('tr', {}, [el('th', { text: 'Parlamentar' }), el('th', { text: 'UF' }), el('th', { text: 'Partido' }), el('th', { class: 'num', text: 'Pago a privados' }), el('th', { class: 'num', text: 'Total pago em emendas' }), el('th', { class: 'num', text: '% privado' })]));
        lista = dados.parl.filter(function (r) { return (!uf.value || r[2] === uf.value) && (!nq || norm(r[0]).indexOf(nq) >= 0); });
        lista.slice(0, limite).forEach(function (r) {
          corpo.appendChild(el('tr', {}, [el('td', {}, [el('a', { href: RAIZ + r[1], text: r[0] })]), el('td', { text: r[2] }), el('td', { text: r[3] }),
            el('td', { class: 'num', text: brl(r[5]) }), el('td', { class: 'num', text: brl(r[6]) }), el('td', { class: 'num', text: Math.round(r[7]) + '%' })]));
        });
      }
      atuais = lista;
      mais.hidden = lista.length <= limite; mais.textContent = 'Mostrar mais (' + (lista.length - limite) + ')';
    }
    mais.addEventListener('click', function () { limite += 100; render(); });
    [aba, tipo, uf, sanc].forEach(function (x) { x.addEventListener('change', function () { limite = 50; render(); }); });
    q.addEventListener('input', function () { limite = 50; render(); });
    function carregar() {
      get('data/privados' + (anoSel.value ? '-' + anoSel.value : '') + '.json').then(function (d) {
        dados = d; limite = 50;
        sec.querySelector('[data-v-resumo]').textContent = 'Das emendas pagas ' + (anoSel.value ? 'em ' + anoSel.value : 'desde 2014') + ' (' + brl(d.total) + ', sem bancos intermediários), ' + brl(d.total_priv) + ' (' + (d.total ? Math.round(d.total_priv / d.total * 100) : 0) + '%) foram pagos direto a empresas e entidades privadas.';
        render();
      });
    }
    anoSel.addEventListener('change', carregar);
    get('data/privados.json').then(function (d) {
      dados = d;
      sec.querySelector('[data-v-resumo]').textContent = 'Das emendas pagas desde 2014 (' + brl(d.total) + ', sem bancos intermediários), ' + brl(d.total_priv) + ' (' + (d.total ? Math.round(d.total_priv / d.total * 100) : 0) + '%) foram pagos direto a empresas e entidades privadas.';
      acoes(document.querySelector('[data-acoes]'), [['Baixar lista (CSV)', 'privados.csv', function () {
        return aba.value === 'rec' ? [['recebedor', 'cnpj', 'tipo', 'local', 'parlamentares', 'total', 'sancao'], atuais.map(function (r) { return [r[0], r[1], ROTULO_CLASSE[r[2]], r[5], r[4], r[3], r[6].length ? r[6][0][0] : '']; })]
          : [['parlamentar', 'uf', 'partido', 'pago_a_privados', 'total_emendas', 'pct_privado'], atuais.map(function (r) { return [r[0], r[2], r[3], r[5], r[6], r[7]]; })];
      }]]);
      render();
    });
  }

  /* ---------- quanto custa um mandato: periodo ---------- */
  function iniciarCusto(box) {
    var d = {};
    try { d = JSON.parse(box.getAttribute('data-anos')); } catch (e) { d = {}; }
    var sub = Number(box.getAttribute('data-sub')) || 0, gab = Number(box.getAttribute('data-gab')) || 0, mor = Number(box.getAttribute('data-mor')) || 0;
    var sel = box.querySelector('[data-custo-ano]'), anos = Object.keys(d).sort().reverse();
    anos.forEach(function (a) { sel.appendChild(el('option', { value: a, text: a })); });
    function set(sel_, v) { var x = box.querySelector(sel_); if (x) x.textContent = v === null ? '—' : brl(v); }
    function render() {
      var usar = sel.value ? [sel.value] : anos, meses = 0, cota = 0;
      usar.forEach(function (a) { meses += d[a][0]; cota += d[a][1]; });
      var rotP = sel.value ? 'Em ' + sel.value : 'Em todos os anos';
      box.querySelector('[data-custo-cab]').textContent = rotP;
      Array.prototype.forEach.call(box.querySelectorAll('td[data-rot="No período"]'), function (td) { td.setAttribute('data-rot', rotP); });
      set('[data-custo-sub]', meses ? sub * meses : null);
      set('[data-custo-gab]', meses && gab ? gab * meses : null);
      set('[data-custo-mor]', meses && mor ? mor * meses : null);
      set('[data-custo-cota]', cota);
      var uso = 0, mu = 0, tem = false;
      usar.forEach(function (a) { if (d[a].length > 2) { tem = true; uso += d[a][2]; mu += d[a][3]; } });
      set('[data-custo-gabuso]', tem ? uso : null);
      var gm = box.querySelector('[data-custo-gabmeses]'); if (gm) gm.textContent = mu + (mu === 1 ? ' mês' : ' meses');
      var tetos = (meses ? sub * meses + gab * meses + mor * meses : 0);
      box.querySelector('[data-custo-resumo]').textContent = meses ?
        meses + ' meses no período. Somando subsídio, tetos e cota, o limite legal é de ' + brl(tetos + cota) + ' (a cota é o gasto registrado; o restante são valores legais, não gasto efetivo).' : 'Sem meses com despesa registrada neste período.';
    }
    sel.addEventListener('change', render);
    render();
  }

  /* ---------- fornecedores por ano ---------- */
  function iniciarForn(box) {
    var d = {};
    try { d = JSON.parse(box.getAttribute('data-anos')); } catch (e) { d = {}; }
    var sel = box.querySelector('[data-forn-ano]'); if (!sel) return;
    var corpo = box.querySelector('[data-forn-corpo]'), cab = box.querySelector('[data-forn-cab]'), orig = corpo.innerHTML, cab0 = cab.textContent;
    Object.keys(d).sort().reverse().forEach(function (a) { sel.appendChild(el('option', { value: a, text: a })); });
    function render() {
      if (!sel.value) { corpo.innerHTML = orig; cab.textContent = cab0; return; }
      cab.textContent = 'Total em ' + sel.value;
      corpo.textContent = '';
      (d[sel.value] || []).forEach(function (r) {
        corpo.appendChild(el('tr', {}, [el('td', { text: r[0] }), el('td', { class: 'num', text: brl(r[1]) }), el('td', { class: 'num', text: String(r[2]) })]));
      });
    }
    sel.addEventListener('change', render);
    document.addEventListener('change', function (e) {
      var t = e.target, outro = t && t.hasAttribute && t.hasAttribute('data-pm-ano') ? sel : (t === sel ? document.querySelector('[data-pm-ano]') : null);
      if (!outro || outro === t) return;
      if (outro === sel) { if (Array.prototype.some.call(sel.options, function (o) { return o.value === t.value; })) { sel.value = t.value; render(); } }
      else outro.value = sel.value || outro.value, outro.dispatchEvent(new Event('change'));
    });
  }

  /* ---------- tema: automatico -> claro -> escuro ---------- */
  (function () {
    var b = document.querySelector('[data-tema-btn]'); if (!b) return;
    var rot = b.querySelector('[data-tema-rot]'), nomes = { '': 'Auto', claro: 'Claro', escuro: 'Escuro' };
    function atual() { return document.documentElement.getAttribute('data-tema') || ''; }
    function mostrar() { rot.textContent = nomes[atual()]; }
    b.addEventListener('click', function () {
      var prox = { '': 'claro', claro: 'escuro', escuro: '' }[atual()];
      if (prox) document.documentElement.setAttribute('data-tema', prox); else document.documentElement.removeAttribute('data-tema');
      try { if (prox) localStorage.setItem('tema', prox); else localStorage.removeItem('tema'); } catch (e) {}
      mostrar();
    });
    mostrar();
  })();

  /* ---------- tamanho do texto (A- / A+) ---------- */
  Array.prototype.forEach.call(document.querySelectorAll('[data-texto]'), function (b) {
    b.addEventListener('click', function () {
      var atual = parseFloat(document.documentElement.style.fontSize) || 112.5;
      var novo = Math.max(100, Math.min(137.5, atual + (b.getAttribute('data-texto') === '+' ? 12.5 : -12.5)));
      document.documentElement.style.fontSize = novo + '%';
      try { localStorage.setItem('tamanho-texto', String(novo)); } catch (e) {}
    });
  });

  /* ---------- reportar erro e compartilhar imagem ---------- */
  var rep_ = document.querySelector('[data-reportar]');
  if (rep_) rep_.href = 'mailto:oquepagamos@gmail.com?subject=' + encodeURIComponent('Erro ou falta em: ' + document.title) +
    '&body=' + encodeURIComponent('Página: ' + location.href + '\n\nO que está errado ou faltando (se puder, cite a fonte oficial):\n');

  function quebrar(ctx, texto, largura) {
    var palavras = String(texto).split(/\s+/), linhas = [], atual = '';
    palavras.forEach(function (p) {
      var t = atual ? atual + ' ' + p : p;
      if (ctx.measureText(t).width > largura && atual) { linhas.push(atual); atual = p; } else atual = t;
    });
    if (atual) linhas.push(atual);
    return linhas;
  }
  function imagemCompartilhar() {
    var titulo = (document.querySelector('h1') || {}).textContent || document.title;
    var sub = ((document.querySelector('.pessoa-cab .cargo') || {}).textContent || '').trim();
    var fatos = Array.prototype.map.call(document.querySelectorAll('.faixa-resumo > div'), function (d) {
      return [(d.querySelector('span') || {}).textContent || '', (d.querySelector('strong') || {}).textContent || ''];
    }).slice(0, 4);
    return (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(function () {
      return new Promise(function (ok) {
        var img = new Image(); img.onload = function () { ok(img); }; img.onerror = function () { ok(null); }; img.src = RAIZ + 'static/logo.png';
      });
    }).then(function (logo) {
      var W = 1080, H = 1350, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
      var ctx = cv.getContext('2d'), FT = '"Bricolage Grotesque", "Instrument Sans", system-ui, sans-serif';
      ctx.fillStyle = '#f2c335'; ctx.fillRect(0, 0, W, 190);
      ctx.fillStyle = '#f6f7fb'; ctx.fillRect(0, 190, W, H - 190);
      if (logo) ctx.drawImage(logo, 56, 40, 110, 110);
      ctx.fillStyle = '#10202f'; ctx.font = '700 46px ' + FT; ctx.textBaseline = 'alphabetic';
      ctx.fillText('Gastos Públicos', 190, 92);
      ctx.font = '500 30px ' + FT; ctx.fillText('@oquepagamos', 190, 138);
      var y = 330; ctx.fillStyle = '#10202f'; ctx.font = '700 76px ' + FT;
      quebrar(ctx, titulo, W - 112).slice(0, 3).forEach(function (l) { ctx.fillText(l, 56, y); y += 90; });
      ctx.fillStyle = '#4a5868'; ctx.font = '500 34px ' + FT; y += 6;
      quebrar(ctx, sub, W - 112).slice(0, 2).forEach(function (l) { ctx.fillText(l, 56, y); y += 46; });
      y += 40;
      fatos.forEach(function (f_) {
        ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#dfe3ea'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.roundRect ? ctx.roundRect(56, y, W - 112, 150, 20) : ctx.rect(56, y, W - 112, 150); ctx.fill(); ctx.stroke();
        ctx.fillStyle = '#4a5868'; ctx.font = '500 30px ' + FT; ctx.fillText(f_[0], 90, y + 52);
        ctx.fillStyle = '#10202f'; ctx.font = '700 58px ' + FT; ctx.fillText(f_[1], 90, y + 118);
        y += 172;
      });
      ctx.fillStyle = '#4a5868'; ctx.font = '500 26px ' + FT;
      ctx.fillText('Fatos de dados oficiais (Câmara, Senado, Portal da Transparência, TSE).', 56, H - 110);
      ctx.fillText('Gasto não é irregularidade. Veja o método e confira a fonte:', 56, H - 72);
      ctx.fillStyle = '#10202f'; ctx.font = '700 30px ' + FT; ctx.fillText(location.host + location.pathname, 56, H - 30);
      return new Promise(function (res) { cv.toBlob(res, 'image/png'); });
    });
  }
  document.querySelectorAll('img[data-foto]').forEach(function (im) {
    im.addEventListener('error', function () { im.remove(); });
    if (im.complete && im.naturalWidth === 0 && im.getAttribute('src')) im.remove();
  });
  document.querySelectorAll('[data-zap]').forEach(function (a) {
    a.addEventListener('click', function () { a.href = 'https://wa.me/?text=' + encodeURIComponent(document.title + ' ' + location.href); });
  });
  document.querySelectorAll('[data-compartilhar]').forEach(function (btn) {
    var rot = btn.textContent;
    btn.addEventListener('click', function () {
      btn.disabled = true; btn.textContent = 'Gerando imagem…';
      imagemCompartilhar().then(function (blob) {
        var nome = (location.pathname.replace(/\/+$/, '').split('/').pop() || 'gastos-publicos') + '.png';
        var texto = document.title + ' ' + location.href;
        var arq = blob && window.File ? new File([blob], nome, { type: 'image/png' }) : null;
        if (arq && navigator.canShare && navigator.canShare({ files: [arq] })) {
          return navigator.share({ files: [arq], title: document.title, text: texto }).catch(function () {});
        }
        if (blob) { var a_ = el('a', { href: URL.createObjectURL(blob), download: nome }); document.body.appendChild(a_); a_.click(); a_.remove(); }
      }).then(function () { btn.disabled = false; btn.textContent = rot; }, function () { btn.disabled = false; btn.textContent = rot; });
    });
  });

  /* abas da pagina do parlamentar + abre blocos recolhidos quando o link aponta para dentro deles */
  var abasNav = document.querySelector('[data-abas]');
  function mostrarAba(nome) {
    if (!abasNav) return;
    var ok = false;
    abasNav.querySelectorAll('[data-aba-btn]').forEach(function (b) { if (b.getAttribute('data-aba-btn') === nome) ok = true; });
    if (!ok) nome = abasNav.querySelector('[data-aba-btn]').getAttribute('data-aba-btn');
    abasNav.querySelectorAll('[data-aba-btn]').forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-aba-btn') === nome ? 'true' : 'false'); });
    document.querySelectorAll('.aba-painel').forEach(function (p) { p.hidden = p.getAttribute('data-aba') !== nome; });
  }
  if (abasNav) {
    abasNav.hidden = abasNav.querySelectorAll('[data-aba-btn]').length < 2;
    abasNav.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('[data-aba-btn]'); if (!b) return;
      mostrarAba(b.getAttribute('data-aba-btn'));
      try { history.replaceState(null, '', '#' + b.getAttribute('data-aba-btn')); } catch (x) { /* sem historico */ }
    });
    mostrarAba(abasNav.querySelector('[data-aba-btn]').getAttribute('data-aba-btn'));
  }
  function abrirHash() {
    var h = location.hash && location.hash.slice(1); if (!h) return;
    var t = document.getElementById(h); if (!t) return;
    var painel = t.closest ? t.closest('.aba-painel') : null;
    if (painel) mostrarAba(painel.getAttribute('data-aba'));
    for (var n = t; n; n = n.parentElement) if (n.tagName === 'DETAILS') n.open = true;
    (painel === t && abasNav ? abasNav : t).scrollIntoView();
  }
  window.addEventListener('hashchange', abrirHash); abrirHash();

  /* ---------- partidos: tabela geral ---------- */
  function iniciarPartidos(sec) {
    var selA = sec.querySelector('[data-pt-ano]'), q = sec.querySelector('[data-pt-q]'), cab = document.querySelector('[data-pt-cab]'), corpo = document.querySelector('[data-pt-corpo]');
    var dados = null, ordem = 1, desc = false;
    var COLS = [['Partido', 1, 'txt'], ['Fundo Partidário recebido', 2, 'brl'], ['Fundo eleitoral recebido', 3, 'brl'], ['Receitas do partido', 4, 'brl'], ['Gasto com pessoal', 5, 'brl']];
    function render() {
      if (!dados) return;
      var lista = (dados.linhas[selA.value] || []).slice(), nq = norm(q.value.trim());
      lista = lista.filter(function (r) { return !nq || norm(r[1]).indexOf(nq) >= 0; });
      var col = ordem, tipo = COLS[col - 1][2];
      lista.sort(function (a, b) {
        var x = a[col], y = b[col];
        if (tipo === 'txt') return desc ? String(y).localeCompare(String(x), 'pt-BR') : String(x).localeCompare(String(y), 'pt-BR');
        if (x === null && y === null) return 0; if (x === null) return 1; if (y === null) return -1;
        return desc ? y - x : x - y;
      });
      cab.textContent = '';
      cab.appendChild(el('tr', {}, COLS.map(function (c, i) {
        var b = el('button', { type: 'button', class: 'botao-th', text: c[0] + (ordem === c[1] ? (desc ? ' ▼' : ' ▲') : '') });
        b.addEventListener('click', function () { if (ordem === c[1]) desc = !desc; else { ordem = c[1]; desc = c[2] !== 'txt'; } render(); });
        return el('th', { class: i ? 'num' : '' }, [b]);
      })));
      corpo.textContent = '';
      lista.forEach(function (r) {
        corpo.appendChild(el('tr', {}, [el('td', {}, [el('a', { href: RAIZ + 'partido/' + r[0] + '/', text: r[1] })])]
          .concat([2, 3, 4, 5].map(function (i) { return el('td', { class: 'num', text: r[i] === null ? '—' : brl(r[i]) }); }))));
      });
      sec.querySelector('[data-pt-resumo]').textContent = lista.length + (lista.length === 1 ? ' partido' : ' partidos') + ' em ' + selA.value + '. "—" significa sem dado naquele ano (a prestação de contas do TSE sai com atraso e o fundo eleitoral só existe em anos de eleição).';
    }
    get('data/partidos.json').then(function (d) {
      dados = d; selA.addEventListener('change', render); q.addEventListener('input', render); render();
      acoes(document.querySelector('[data-acoes]'), [['Baixar tabela (CSV)', 'partidos-' + selA.value + '.csv', function () {
        return [COLS.map(function (c) { return c[0]; }), (dados.linhas[selA.value] || []).map(function (r) { return [r[1]].concat(r.slice(2)); })];
      }]]);
    }).catch(function () { sec.querySelector('[data-pt-resumo]').textContent = 'Não foi possível carregar os dados.'; });
  }

  /* ---------- partido: dinheiro (TSE) ---------- */
  function iniciarPartidoDados(sec) {
    var slug = document.querySelector('[data-partido-pagina]').getAttribute('data-slug');
    var selA = sec.querySelector('[data-pt-ano]'), selB = sec.querySelector('[data-pt-base]'), d = null;
    var RE_P = /pessoal|sal[aá]ri|folha|remunera|encargos|f[eé]rias|13|rescis/i;
    var rcbCache = {}, rcbAtual = { r: [], pf: [0, 0] }, rcbFiltrados = [], limite = 50;
    var qEl = sec.querySelector('[data-pt-q]'), minEl = sec.querySelector('[data-pt-min]'), ordEl = sec.querySelector('[data-pt-ord]'), maisEl = sec.querySelector('[data-pt-mais]');
    function pintarRcb() {
      var nq = norm(qEl.value.trim()), dq = qEl.value.replace(/\D/g, ''), mn = Number(minEl.value) || 0;
      rcbFiltrados = rcbAtual.r.filter(function (r) { return r[2] >= mn && (!nq || norm(r[0]).indexOf(nq) >= 0 || (dq.length >= 3 && r[1].indexOf(dq) >= 0)); });
      if (ordEl.value === 'nome') rcbFiltrados = rcbFiltrados.slice().sort(function (x, y) { return x[0].localeCompare(y[0], 'pt-BR'); });
      var tot = rcbFiltrados.reduce(function (s_, r) { return s_ + r[2]; }, 0), tb = sec.querySelector('[data-pt-rcb]'); tb.textContent = '';
      rcbFiltrados.slice(0, limite).forEach(function (r) { tb.appendChild(el('tr', {}, [el('td', { text: r[0] }), el('td', { text: r[1] }), el('td', { class: 'num', text: brl(r[2]) }), el('td', { class: 'num', text: String(r[3]) })])); });
      if (!rcbFiltrados.length) tb.appendChild(el('tr', {}, [el('td', { colspan: '4', text: 'Nenhum recebedor com esses filtros.' })]));
      maisEl.hidden = rcbFiltrados.length <= limite;
      sec.querySelector('[data-pt-rcb-resumo]').textContent = rcbFiltrados.length + ' de ' + rcbAtual.r.length + ' empresas e entidades, somando ' + brl(tot) +
        (rcbAtual.pf[0] ? '. Pessoas físicas pagas, em valor somado e sem identificação: ' + brl(rcbAtual.pf[0]) + ' em ' + rcbAtual.pf[1] + ' pagamentos.' : '.');
    }
    function carregarRcb() {
      var chave = selA.value + '-' + selB.value, A0 = (d.anos[selA.value] || {})[selB.value];
      limite = 50;
      var ok = function (j) { rcbCache[chave] = j; rcbAtual = j; pintarRcb(); };
      if (!A0 || !A0.nrcb && !A0.rec.length) { rcbAtual = { r: [], pf: [0, 0] }; pintarRcb(); return; }
      if (rcbCache[chave]) return ok(rcbCache[chave]);
      get('data/partido-' + slug + '/' + chave + '.json').then(ok).catch(function () { rcbAtual = { r: [], pf: [0, 0] }; pintarRcb(); });
    }
    [qEl, minEl, ordEl].forEach(function (x) { x.addEventListener(x === qEl ? 'input' : 'change', function () { limite = 50; pintarRcb(); }); });
    maisEl.addEventListener('click', function () { limite += 100; pintarRcb(); });
    acoes(sec.querySelector('[data-pt-acoes]'), [['Baixar esta lista (CSV)', 'recebedores-' + slug + '.csv', function () {
      return [['recebedor', 'cnpj', 'valor', 'lancamentos'], rcbFiltrados];
    }]]);
    function tab(sel_, linhas, cols) {
      var tb = sec.querySelector(sel_); tb.textContent = '';
      if (!linhas.length) { tb.appendChild(el('tr', {}, [el('td', { colspan: String(cols), text: 'Sem dados neste ano e tipo de conta.' })])); return; }
      linhas.forEach(function (tr) { tb.appendChild(tr); });
    }
    function render() {
      var A = (d.anos[selA.value] || {})[selB.value] || { rec: [], des: [], rcb: [] };
      var totR = A.rec.reduce(function (s, r) { return s + r[1]; }, 0), totD = A.des.reduce(function (s, r) { return s + r[1]; }, 0);
      sec.querySelector('[data-pt-aviso]').textContent = (A.rec.length || A.des.length) ? 'Receitas somam ' + brl(totR) + ' e despesas somam ' + brl(totD) + ' (maiores linhas abaixo).' : 'Este tipo de conta não tem dados neste ano.';
      tab('[data-pt-rec]', A.rec.map(function (r) { return el('tr', {}, [el('td', { text: r[0] }), el('td', { class: 'num', text: brl(r[1]) }), el('td', { class: 'num', text: String(r[2]) })]); }), 3);
      tab('[data-pt-des]', A.des.map(function (r) { return el('tr', {}, [el('td', { text: r[0] }), el('td', { class: 'num', text: brl(r[1]) }), el('td', { class: 'num', text: String(r[2]) })]); }), 3);
      var pes = A.des.filter(function (r) { return RE_P.test(r[0]); }).reduce(function (s, r) { return s + r[1]; }, 0);
      sec.querySelector('[data-pt-pessoal]').textContent = pes ? 'Despesas que parecem ser com pessoal (salários, encargos e similares): ' + brl(pes) + ' no ano. Só o total é público; não há salário por funcionário.' : '';
      carregarRcb();
      var C = d.cand[selA.value] || [], blc = sec.querySelector('[data-pt-cand-bloco]');
      blc.hidden = !C.length;
      var tc = sec.querySelector('[data-pt-cand]'); tc.textContent = '';
      C.forEach(function (r) { tc.appendChild(el('tr', {}, [el('td', { text: r[0] }), el('td', { text: r[1] }), el('td', { text: r[2] }), el('td', { class: 'num', text: brl(r[3]) }), el('td', { class: 'num', text: brl(r[4]) })])); });
    }
    get('data/partido-' + slug + '.json').then(function (j) {
      d = j; Object.keys(d.anos).sort().reverse().forEach(function (y) { selA.appendChild(el('option', { value: y, text: y })); });
      var anual = Object.keys(d.anos).filter(function (y) { return d.anos[y].anual; }).sort().reverse()[0];
      if (anual) selA.value = anual;
      Array.prototype.forEach.call(selB.options, function (o) { o.setAttribute('data-rot', o.textContent); });
      function ajustar() {
        var Y = d.anos[selA.value] || {}, primeiro = null;
        function tem(b) { return !!(Y[b] && (Y[b].rec.length || Y[b].des.length)); }
        Array.prototype.forEach.call(selB.options, function (o) {
          o.textContent = o.getAttribute('data-rot') + (tem(o.value) ? '' : ' (sem dados neste ano)');
          if (tem(o.value) && !primeiro) primeiro = o.value;
        });
        if (!tem(selB.value) && primeiro) selB.value = primeiro;
      }
      selA.addEventListener('change', function () { ajustar(); render(); }); selB.addEventListener('change', render);
      ajustar(); render();
    }).catch(function () { sec.querySelector('[data-pt-aviso]').textContent = 'Não foi possível carregar os dados deste partido.'; });
  }

  /* ---------- pares ---------- */
  function iniciarPares(sec) {
    var selC = sec.querySelector('[data-p-cargo]'), selU = sec.querySelector('[data-p-uf]'), q = sec.querySelector('[data-p-q]'), selAno = sec.querySelector('[data-p-ano]');
    var cab = document.querySelector('[data-p-cab]'), corpo = document.querySelector('[data-p-corpo]'), mais = document.querySelector('[data-p-mais]');
    var dados = null, ordem = 6, asc = true, limite = 60, atuais = [];
    function fmt(v, f) { return v === null || v === undefined ? '—' : f === 'brl' ? brl(v) : f === 'pct' ? Math.round(v) + '%' : String(Math.round(v)); }
    function med(v) { v = v.filter(function (x) { return x !== null; }).sort(function (a, b) { return a - b; }); return v.length ? (v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2) : null; }
    function render() {
      if (!dados) return;
      var nq = norm(q.value.trim());
      var base = dados.linhas.filter(function (l) { return l[5] === selC.value && (!selU.value || l[3] === selU.value); });
      var ind = dados.ind;
      cab.textContent = '';
      var tr = el('tr', {}, [el('th', { text: 'Parlamentar' }), el('th', { text: 'UF' }), el('th', { text: 'Partido' })]);
      ind.forEach(function (x, i) {
        var th = el('th', { class: 'num', title: x[1] + (x[2] === null ? ' (sem juízo de valor)' : x[2] ? ' (menor valor = gasta menos)' : ' (maior valor = mais)'), 'aria-sort': ordem === 6 + i ? (asc ? 'ascending' : 'descending') : 'none' });
        var b = el('button', { type: 'button', class: 'botao-th', text: (x[4] || x[1]) + (ordem === 6 + i ? (asc ? ' ↑' : ' ↓') : '') });
        b.addEventListener('click', function () { if (ordem === 6 + i) asc = !asc; else { ordem = 6 + i; asc = !!x[2]; } limite = 60; render(); });
        th.appendChild(b); tr.appendChild(th);
      });
      tr.appendChild(el('th', { class: 'num', text: 'Meses' }));
      cab.appendChild(tr);
      var lista = base.filter(function (l) { return !nq || norm(l[1]).indexOf(nq) >= 0; }).sort(function (a, b) {
        var x = a[ordem], y = b[ordem];
        if (x === null) return 1; if (y === null) return -1;
        return asc ? x - y : y - x;
      });
      atuais = lista;
      var medianas = ind.map(function (_, i) { return med(base.map(function (l) { return l[6 + i]; })); });
      sec.querySelector('[data-p-resumo]').textContent = base.length + ' parlamentares' + (selU.value ? ' em ' + selU.value : '') + ' com ao menos 3 meses de cota registrada ' + dados.periodo + '.';
      corpo.textContent = '';
      corpo.appendChild(el('tr', { class: 'total' }, [el('td', { text: 'Mediana do grupo' }), el('td'), el('td')].concat(ind.map(function (x, i) { return el('td', { class: 'num', text: fmt(medianas[i], x[3]) }); })).concat([el('td')])));
      lista.slice(0, limite).forEach(function (l) {
        corpo.appendChild(el('tr', {}, [el('td', {}, [el('a', { href: RAIZ + l[2], text: l[1] })]), el('td', { text: l[3] }), el('td', { text: l[4] }),
          ].concat(ind.map(function (x, i) { return el('td', { class: 'num', text: fmt(l[6 + i], x[3]) }); })).concat([el('td', { class: 'num', text: String(l[6 + ind.length]) })])));
      });
      mais.hidden = lista.length <= limite;
      mais.textContent = 'Mostrar mais (' + (lista.length - limite) + ')';
    }
    mais.addEventListener('click', function () { limite += 100; render(); });
    [selC, selU].forEach(function (s_) { s_.addEventListener('change', function () { limite = 60; render(); }); });
    q.addEventListener('input', function () { limite = 60; render(); });
    function carregarPares() {
      get('data/pares' + (selAno.value ? '-' + selAno.value : '') + '.json').then(function (d) { dados = d; limite = 60; render(); });
    }
    selAno.addEventListener('change', carregarPares);
    get('data/pares.json').then(function (d) {
      dados = d;
      acoes(document.querySelector('[data-acoes]'), [['Baixar tabela (CSV)', 'pares' + (selAno.value ? '-' + selAno.value : '') + '.csv', function () {
        return [['parlamentar', 'uf', 'partido'].concat(dados.ind.map(function (x) { return x[1]; })), atuais.map(function (l) { return [l[1], l[3], l[4]].concat(dados.ind.map(function (_, i) { return l[6 + i]; })); })];
      }]]);
      render();
    });
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
  function blocoTce(tc, ano) {
    var box = document.querySelector('[data-mu-tce]');
    if (!box || !tc) return;
    var anos = ano ? [ano] : Object.keys(tc), fun = {}, pag = {};
    anos.forEach(function (a) {
      var t = tc[a]; if (!t) return;
      t.f.forEach(function (x) { var k = x[0]; fun[k] = fun[k] || [0, 0, 0, 0]; for (var j = 0; j < 4; j++) fun[k][j] += x[j + 1]; });
      t.p.forEach(function (x) { var k = x[0] + '|' + x[1] + '|' + x[2] + '|' + x[3] + '|' + x[4]; pag[k] = pag[k] || x.slice(0, 6).concat([0]); pag[k][6] += x[6]; });
    });
    var ks = Object.keys(fun).sort(function (a, b) { var s = function (k) { return fun[k].reduce(function (u, v) { return u + v; }, 0); }; return s(b) - s(a); });
    box.hidden = !ks.length;
    if (!ks.length) return;
    var tot = [0, 0, 0, 0];
    var tb = box.querySelector('[data-mu-tce-funcao]'); tb.textContent = '';
    ks.forEach(function (k) {
      var v = fun[k]; for (var j = 0; j < 4; j++) tot[j] += v[j];
      tb.appendChild(el('tr', {}, [el('td', { text: k }), el('td', { class: 'num', text: brl(v[1]) }), el('td', { class: 'num', text: brl(v[2]) }),
        el('td', { class: 'num', text: brl(v[0] + v[3]) }), el('td', { class: 'num', text: brl(v[0] + v[1] + v[2] + v[3]) })]));
    });
    var geral = tot[0] + tot[1] + tot[2] + tot[3];
    box.querySelector('[data-mu-tce-resumo]').textContent = 'A prefeitura e seus órgãos pagaram ' + brl(geral) + (ano ? ' em ' + ano : ' nos anos carregados (' + anos.filter(function (a) { return tc[a]; }).join(', ') + ')') +
      ', dos quais ' + brl(tot[1]) + ' (' + (geral ? Math.round(tot[1] / geral * 100) : 0) + '%) com recursos de transferências federais.';
    var fr = {};
    anos.forEach(function (a) {
      var t = tc[a]; if (!t || !t.r) return;
      t.r.forEach(function (x) { var k = x[0] + '|' + x[1]; fr[k] = fr[k] || [x[0], x[1], x[2], 0, 0, 0, x[6]]; fr[k][3] += x[3]; fr[k][4] += x[4]; fr[k][5] += x[5]; });
    });
    var tf = box.querySelector('[data-mu-tce-forn]');
    if (tf) {
      tf.textContent = '';
      Object.keys(fr).map(function (k) { return fr[k]; }).sort(function (a, b) { return b[3] - a[3]; }).slice(0, 40).forEach(function (x) {
        tf.appendChild(el('tr', {}, [el('td', {}, [document.createTextNode(x[1]), chipClasse(x[2], x[6] && x[6].length ? x[6] : null), el('small', { text: 'CNPJ ' + x[0] })]),
          el('td', { class: 'num', text: brl(x[3]) }), el('td', { class: 'num', text: brl(x[4]) }),
          el('td', { class: 'num', text: x[3] ? Math.round(x[5] / x[3] * 100) + '%' : '—' })]));
      });
    }
    var lp = Object.keys(pag).map(function (k) { return pag[k]; }).sort(function (a, b) { return b[4] - a[4] || b[6] - a[6]; }).slice(0, 60);
    var tp = box.querySelector('[data-mu-tce-pag]'); tp.textContent = '';
    lp.forEach(function (x) {
      var nome = x[1] || 'Não informado';
      tp.appendChild(el('tr', {}, [el('td', {}, [document.createTextNode(nome), el('small', { text: (x[0] ? 'CNPJ ' + x[0] : '') + (x[4] ? ' · cita emenda' : '') + (x[5] ? ' · ' + x[5].slice(0, 140) : '') })]),
        el('td', { text: x[2] }), el('td', { text: x[3] === 'federal' ? 'Federal' : x[3] === 'estadual' ? 'Estadual' : 'Própria/outras' }), el('td', { class: 'num', text: brl(x[6]) })]));
    });
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
      blocoTce(d.tc, ano);
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


  function iniciarCongresso(raiz) {
    var cg = { sel: {}, ufs: {}, dest: '', ouv: [], contar: null, nomes: null, n: 0 };
    cg.lista = function () { return Object.keys(cg.ufs).sort(); };
    cg.LEG = { L57: [2023, 2026], L56: [2019, 2022], L55: [2015, 2018] };
    cg.periodo = function () { return '0'; };
    cg.notificar = function () { cg.ouv.forEach(function (f) { f(); }); };
    iniciarHemiciclo(raiz, cg);
    iniciarMapaDinheiro(raiz, cg);
  }

  function iniciarHemiciclo(raiz, cg) {
    var esc = function (v) { return String(v === null || v === undefined ? '' : v).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); };
    var el = raiz.querySelector('[data-hemi-dados]'); if (!el) return;
    var P; try { P = JSON.parse(el.textContent); } catch (e) { return; }
    if (!P.length) return;
    var cores = ['#1f6feb', '#d9822b', '#2a9d6f', '#8e5bd1', '#c2417a', '#0f9bb3', '#a9852a', '#5b6b7a', '#e0533d', '#4f8a2f', '#7a4fb0', '#2f7f9e', '#b5651d', '#3b4cc0', '#8a8a2a', '#c0392b'];
    P.forEach(function (p, i) { p.cor = cores[i % cores.length]; p.d.sort(function (a, b) { return b[3] - a[3]; }); p.n.sort(function (a, b) { return b[3] - a[3]; }); });
    var ns = 'http://www.w3.org/2000/svg', svgs = [];
    var ROT = { d: ['deputado', 'deputados', 'Câmara'], n: ['senador', 'senadores', 'Senado'] };
    function cadeiras(chave) {
      var box = raiz.querySelector('[data-hemi-svg="' + chave + '"]'); if (!box) return;
      var tot = 0, i, j; P.forEach(function (p) { tot += p[chave].length; }); if (!tot) return;
      var linhas = Math.max(3, Math.round(Math.sqrt(tot / 3.2))), raios = [], soma = 0;
      for (i = 0; i < linhas; i++) raios.push(0.42 + 0.58 * i / (linhas - 1));
      raios.forEach(function (r) { soma += r; });
      var seats = [], resto = tot;
      raios.forEach(function (r, k) {
        var n = k === linhas - 1 ? resto : Math.round(tot * r / soma); resto -= n;
        for (j = 0; j < n; j++) seats.push({ a: n === 1 ? 0.5 : j / (n - 1), r: r });
      });
      seats.sort(function (x, y) { return x.a - y.a || x.r - y.r; });
      var W = 600, H = 300, cx = W / 2, cy = H - 14, R = 270, rs = Math.max(3.2, Math.min(8, R * 0.58 / linhas * 0.5));
      var svg = document.createElementNS(ns, 'svg');
      svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H); svg.setAttribute('role', 'img');
      svg.setAttribute('aria-label', ROT[chave][2] + ' com ' + tot + ' ' + ROT[chave][1] + ', agrupados por partido');
      var pts = []; P.forEach(function (p, pi) { p[chave].forEach(function (d, di) { pts.push({ pi: pi, di: di }); }); });
      pts.forEach(function (q, idx) {
        var s = seats[idx], ang = Math.PI * (1 - s.a), c = document.createElementNS(ns, 'circle'), d = P[q.pi][chave][q.di];
        c.setAttribute('cx', (cx + Math.cos(ang) * s.r * R).toFixed(1)); c.setAttribute('cy', (cy - Math.sin(ang) * s.r * R).toFixed(1));
        c.setAttribute('r', rs.toFixed(1)); c.setAttribute('fill', P[q.pi].cor); c.setAttribute('class', 'cad');
        c.setAttribute('data-p', q.pi); c.setAttribute('data-c', chave); c.setAttribute('data-d', q.di); c.setAttribute('data-u', d[2]);
        var t = document.createElementNS(ns, 'title'); t.textContent = d[0] + ' (' + P[q.pi].s + '-' + d[2] + ')'; c.appendChild(t);
        svg.appendChild(c);
      });
      var cen = document.createElementNS(ns, 'text'); cen.setAttribute('x', cx); cen.setAttribute('y', cy - 10); cen.setAttribute('text-anchor', 'middle'); cen.setAttribute('class', 'hemi-n');
      cen.textContent = tot + ' ' + ROT[chave][1]; svg.appendChild(cen);
      box.appendChild(svg); svgs.push(svg);
      svg.addEventListener('click', function (e) {
        var c = e.target.closest ? e.target.closest('.cad') : null; if (!c) return;
        var pi = +c.getAttribute('data-p'); cg.ufs = {}; cg.sel = {}; cg.sel[pi] = true; cg.dest = P[pi][chave][+c.getAttribute('data-d')][0]; cg.notificar();
      });
    }
    cadeiras('d'); cadeiras('n');
    var leg = raiz.querySelector('[data-hemi-leg]'), painel = raiz.querySelector('[data-hemi-painel]');
    P.forEach(function (p, pi) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'hemi-chip'; b.setAttribute('data-p', pi); b.setAttribute('aria-pressed', 'false');
      b.title = p.d.length + ' deputado(s) e ' + p.n.length + ' senador(es)';
      b.innerHTML = '<i style="background:' + p.cor + '"></i>' + esc(p.s) + ' <b>' + (p.d.length + p.n.length) + '</b>';
      b.addEventListener('click', function () { if (cg.lista().length) { cg.ufs = {}; cg.sel = {}; } if (cg.sel[pi]) delete cg.sel[pi]; else cg.sel[pi] = true; cg.dest = ''; cg.notificar(); });
      leg.appendChild(b);
    });
    function escolhidos() { return P.map(function (p, i) { return cg.sel[i] ? i : -1; }).filter(function (i) { return i >= 0; }); }
    cg.contar = function () {
      var out = {}; escolhidos().forEach(function (i) { ['d', 'n'].forEach(function (k) { P[i][k].forEach(function (d) { out[d[2]] = (out[d[2]] || 0) + 1; }); }); }); return out;
    };
    cg.nomes = function () { return escolhidos().map(function (i) { return P[i].s; }); };
    function marcar() {
      var n = escolhidos().length;
      svgs.forEach(function (svg) {
        svg.classList.toggle('foco', n > 0 || cg.lista().length > 0);
        svg.querySelectorAll('.cad').forEach(function (c) {
          var ok = (!n || cg.sel[+c.getAttribute('data-p')]) && (!cg.lista().length || cg.ufs[c.getAttribute('data-u')]);
          c.classList.toggle('on', !!ok);
        });
      });
      var temUf = cg.lista().length > 0;
      leg.querySelectorAll('.hemi-chip').forEach(function (b) {
        var pi = +b.getAttribute('data-p'), on = !!cg.sel[pi], tot = 0;
        ['d', 'n'].forEach(function (k) { P[pi][k].forEach(function (d) { if (!temUf || cg.ufs[d[2]]) tot++; }); });
        b.querySelector('b').textContent = tot; b.classList.toggle('zero', temUf && !tot);
        b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    }
    function desenhar() {
      var ids = escolhidos(), modoUf = !ids.length && cg.lista().length > 0;
      if (modoUf) ids = P.map(function (p, i) { return i; });
      if (!ids.length) { painel.innerHTML = '<p class="apoio">Escolha um ou mais partidos na legenda, ou toque numa cadeira.' + (cg.lista().length ? ' Em foco: <strong>' + esc(cg.lista().join(', ')) + '</strong>.' : '') + '</p>'; return; }
      var lista = [], nd = 0, ns_ = 0, soma = 0;
      ids.forEach(function (i) { ['d', 'n'].forEach(function (k) { P[i][k].forEach(function (d) {
        if (cg.lista().length && !cg.ufs[d[2]]) return;
        lista.push({ d: d, k: k, p: P[i] }); soma += d[3]; if (k === 'd') nd++; else ns_++;
      }); }); });
      lista.sort(function (a, b) { return b.d[3] - a.d[3]; });
      var h = '<h3>' + (modoUf ? 'Deputados e senadores de ' + esc(cg.lista().join(', ')) : ids.map(function (i) { return '<span class="hemi-sel"><i style="background:' + P[i].cor + '"></i>' + esc(P[i].s) + '</span>'; }).join(' ')) + '</h3>';
      h += '<p class="apoio"><strong>' + nd + '</strong> deputado' + (nd === 1 ? '' : 's') + ' e <strong>' + ns_ + '</strong> senador' + (ns_ === 1 ? '' : 'es') + (cg.lista().length ? ' em ' + esc(cg.lista().join(', ')) : '') +
        ' · cota usada em ' + raiz.getAttribute('data-ano') + ': <strong>' + brl(soma) + '</strong>' + (lista.length ? ' (média ' + brl(soma / lista.length) + ' por parlamentar)' : '') + '</p>';
      h += '<p class="hemi-acoes"><button type="button" class="botao botao-leve" data-limpar>Limpar partidos</button>' + (cg.lista().length ? ' <button type="button" class="botao botao-leve" data-limpar-uf>Tirar estados (' + esc(cg.lista().join(', ')) + ')</button>' : '') + '</p>';
      function li(x) {
        var d = x.d, im = d[4] ? '<img class="mini-foto" src="' + esc(d[4]) + '" alt="" width="32" height="32" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.style.visibility=\'hidden\'">' : '<i class="mini-foto"></i>';
        return '<li' + (d[0] === cg.dest ? ' class="dest"' : '') + '>' + im + '<a href="' + RAIZ + d[1] + '">' + esc(d[0]) + '</a> <span>' + esc(x.p.s) + '-' + esc(d[2]) + '</span><b>' + brl(d[3]) + '</b></li>';
      }
      function coluna(tit, arr) {
        return '<div class="hemi-col"><h4>' + tit + ' <span>(' + arr.length + ')</span></h4>' + (arr.length ? '<ol class="hemi-lista">' + arr.slice(0, 200).map(li).join('') + '</ol>' + (arr.length > 200 ? '<p class="nota">Mostrando os 200 maiores.</p>' : '') : '<p class="apoio">Nenhum.</p>') + '</div>';
      }
      h += '<div class="hemi-duas">' + coluna('Deputados', lista.filter(function (x) { return x.k === 'd'; })) + coluna('Senadores', lista.filter(function (x) { return x.k === 'n'; })) + '</div>';
      if (!modoUf && ids.length === 1 && P[ids[0]].l) h += '<p><a class="botao botao-leve" href="' + RAIZ + 'partido/' + P[ids[0]].l + '/">Dinheiro do partido (fundos e gastos)</a></p>';
      painel.innerHTML = h;
      var l1 = painel.querySelector('[data-limpar]'); if (l1) l1.addEventListener('click', function () { cg.sel = {}; cg.dest = ''; cg.notificar(); });
      var l2 = painel.querySelector('[data-limpar-uf]'); if (l2) l2.addEventListener('click', function () { cg.ufs = {}; cg.notificar(); });
      var dst = painel.querySelector('.dest'); if (dst && dst.scrollIntoView) dst.scrollIntoView({ block: 'nearest' });
    }
    var pag = raiz.querySelector('[data-pag]'), cache = {}, aba = 'c', gen = 0;
    function carregar(k) { return cache[k] || (cache[k] = get('data/cg/' + k + '.json').catch(function () { return { c: {}, f: {} }; })); }
    var SIT = { '01': 'Nula', '02': 'Ativa', '03': 'Suspensa', '04': 'Inapta', '08': 'Baixada' };
    function cnpjFmt(d) { d = String(d || '').replace(/\D/g, ''); return d.length === 14 ? d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5') : d.length === 8 ? d.replace(/^(\d{2})(\d{3})(\d{3})$/, '$1.$2.$3') + '/…' : d; }
    function dataBr(d) { return /^\d{8}$/.test(d || '') ? d.slice(6) + '/' + d.slice(4, 6) + '/' + d.slice(0, 4) : (d || ''); }
    function curtoN(t, n) { t = String(t || ''); return t.length > n ? t.slice(0, n - 1) + '…' : t; }
    var shardsRf = {};
    function carregarRf(b8) { var k = b8.slice(0, 3); return shardsRf[k] || (shardsRf[k] = get('data/rf/' + k + '.json').catch(function () { return {}; })); }
    var cytoP = null;
    function carregarCyto() {
      if (window.cytoscape) return Promise.resolve(window.cytoscape);
      return cytoP || (cytoP = new Promise(function (ok, no) {
        var sc = document.createElement('script'); sc.src = RAIZ + 'static/cytoscape.min.js';
        sc.onload = function () { ok(window.cytoscape); }; sc.onerror = function () { no(); }; document.head.appendChild(sc);
      }));
    }
    function semSoc(l) { return l && l.length ? '<br><small class="rel-socs">Sócios: ' + l.map(function (x) { return esc(x[0]); }).join(', ') + '</small>' : ''; }
    function abrirRelacoes(cnpj, b8, voltar) {
      b8 = b8 || String(cnpj).replace(/\D/g, '').slice(0, 8);
      var dlg = raiz.querySelector('dialog.cg-rel');
      if (!dlg) { dlg = document.createElement('dialog'); dlg.className = 'cg-dialog cg-rel'; raiz.appendChild(dlg); dlg.addEventListener('click', function (ev) { if (ev.target === dlg) dlg.close(); }); }
      dlg.innerHTML = '<p class="apoio">Carregando…</p>';
      if (dlg.showModal) { if (!dlg.open) dlg.showModal(); } else dlg.setAttribute('open', '');
      carregarRf(b8).then(function (sh) {
        var d = sh[b8];
        if (!d) { dlg.innerHTML = '<h3>' + esc(cnpjFmt(cnpj || b8)) + '</h3><p class="apoio">Ainda não há dados do cadastro da Receita para esta empresa.</p><p><button type="button" class="botao" data-fechar>Fechar</button></p>'; dlg.querySelector('[data-fechar]').addEventListener('click', function () { dlg.close(); }); return; }
        var est = d.e.filter(function (x) { return x[0] === cnpj; })[0] || d.e.filter(function (x) { return x[8] === '1'; })[0] || d.e[0] || [];
        var h = '<h3>' + esc(d.r) + '</h3><p class="apoio">' + (est[1] ? esc(est[1]) + ' · ' : '') + 'CNPJ <strong>' + esc(cnpjFmt(est[0] || cnpj)) + '</strong> · situação <strong>' + esc(SIT[est[2]] || est[2] || '—') + '</strong>' + (est[3] ? ' · aberta em ' + esc(dataBr(est[3])) : '') + '</p>';
        if (est[4]) h += '<p class="apoio">' + esc(est[4]) + (est[5] ? ' — ' + esc(est[5]) + '/' + esc(est[6]) : '') + (est[7] ? ' · CEP ' + esc(est[7]) : '') + '</p>';
        if (d.cota) h += '<p class="apoio">Recebeu <strong>' + brl(d.cota) + '</strong> da cota parlamentar (soma no site, desde 2014).</p>';
        var bxs = {}; Object.keys(d.rs).forEach(function (k) { d.rs[k][1].forEach(function (e) { if (e[2] === '08') bxs[e[0]] = 1; }); });
        Object.keys(d.re).forEach(function (k) { d.re[k][1].forEach(function (e) { if (e[2] === '08') bxs[e[0]] = 1; }); });
        var nbx = Object.keys(bxs).length;
        h += '<div class="rel-opcs">' + (nbx ? '<label class="rel-opc"><input type="checkbox" data-baixadas checked> Mostrar empresas baixadas (' + nbx + ')</label>' : '') + '<label class="rel-opc"><input type="checkbox" data-socios2 checked> Mostrar outros sócios das empresas ligadas</label></div>';
        h += '<div class="rel-grafo" data-grafo></div><p class="rel-leg"><span><i class="b b-alvo"></i>empresa</span> <span><i class="b b-socio"></i>sócio</span> <span><i class="b b-end"></i>endereço</span> <span><i class="b b-rel"></i>outra empresa</span> <span><i class="b b-cota"></i>também recebeu cota</span></p><div class="rel-info" data-rel-info aria-live="polite">Toque num círculo para ver os detalhes.</div>';
        var socs = {}; d.s.forEach(function (x) { var k = x[5] || ('n:' + x[0]); if (!socs[k]) socs[k] = x; });
        var ks = Object.keys(socs);
        h += '<details open><summary>Sócios (' + ks.length + ')</summary><ul class="rel-lista">' + ks.map(function (k) { var x = socs[k]; return '<li><strong>' + esc(x[0]) + '</strong> <span>' + esc(x[2]) + (x[1] ? ' · ' + esc(x[1]) : '') + (x[3] ? ' · desde ' + esc(dataBr(x[3])) : '') + '</span></li>'; }).join('') + '</ul></details>';
        ks.forEach(function (k) {
          var r = d.rs[k]; if (!r || !r[1].length) return;
          h += '<details><summary>Outras empresas de ' + esc(socs[k][0]) + ' (' + r[0] + ')</summary><ul class="rel-lista">' + r[1].map(function (e) { return '<li' + (e[2] === '08' ? ' class="baixada"' : '') + '>' + esc(e[1]) + ' <span>' + esc(cnpjFmt(e[5] || e[0])) + ' · ' + esc(SIT[e[2]] || e[2] || '—') + (e[3] ? ' · ' + esc(e[3]) : '') + '</span>' + (e[4] ? ' <b>recebeu ' + brl(e[4]) + '</b>' : '') + semSoc(e[6]) + '</li>'; }).join('') + '</ul>' + (r[0] > r[1].length ? '<p class="nota">Mostrando ' + r[1].length + ' de ' + r[0] + '.</p>' : '') + '</details>';
        });
        Object.keys(d.re).forEach(function (k) {
          var r = d.re[k];
          h += '<details><summary>Outras empresas ativas no mesmo endereço (' + r[0] + ')</summary><ul class="rel-lista">' + r[1].map(function (e) { return '<li' + (e[2] === '08' ? ' class="baixada"' : '') + '>' + esc(e[1]) + ' <span>' + esc(cnpjFmt(e[6] || e[5])) + (e[3] ? ' · ' + esc(e[3]) : '') + '</span>' + (e[4] ? ' <b>recebeu ' + brl(e[4]) + '</b>' : '') + semSoc(e[8]) + '</li>'; }).join('') + '</ul>' + (r[0] > r[1].length ? '<p class="nota">Mostrando ' + r[1].length + ' de ' + r[0] + '.</p>' : '') + '</details>';
        });
        h += '<p class="nota">Dados abertos do cadastro de CNPJ da Receita Federal. Ter sócio ou endereço em comum é comum (mesmo contador, família, prédio comercial) e <strong>não indica irregularidade</strong>. Sócios pessoa física são ligados por nome e dígitos centrais do CPF; homônimos podem se misturar.</p>';
        h += '<p class="hemi-acoes">' + (voltar ? '<button type="button" class="botao botao-leve" data-voltar>Voltar</button>' : '') + '<button type="button" class="botao" data-fechar>Fechar</button></p>';
        dlg.innerHTML = h;
        dlg.querySelector('[data-fechar]').addEventListener('click', function () { dlg.close(); });
        var bv = dlg.querySelector('[data-voltar]'); if (bv) bv.addEventListener('click', function () { abrirRelacoes(voltar[0], voltar[1], voltar[2]); });
        var info = dlg.querySelector('[data-rel-info]'), box = dlg.querySelector('[data-grafo]');
        carregarCyto().then(function (cy) {
          var els = [], vistos = {}, nid = 0;
          function no(id, label, tipo, extra) { if (vistos[id]) return; vistos[id] = 1; els.push({ group: 'nodes', data: Object.assign({ id: id, label: curtoN(label, 30), tipo: tipo }, extra || {}) }); }
          var arestas = {};
          function liga(a, b, rot) { var k = a + '|' + b; if (arestas[k] || arestas[b + '|' + a]) return; arestas[k] = 1; els.push({ group: 'edges', data: { id: 'x' + (nid++), source: a, target: b, label: rot || '' } }); }
          function socios2(o8, soc) { (soc || []).slice(0, 6).forEach(function (x) { var k = x[3] || ('n:' + x[0] + ':' + o8); no('s:' + k, x[0], 'socio2', { razao: x[0], qual: x[2], doc: x[1] }); liga('s:' + k, 'e:' + o8, curtoN(x[2], 16)); }); }
          no('e:' + b8, d.r, 'alvo', { b8: b8, cnpj: est[0] || cnpj, razao: d.r });
          ks.forEach(function (k) {
            var x = socs[k]; no('s:' + k, x[0], 'socio', { razao: x[0], qual: x[2], doc: x[1] }); liga('e:' + b8, 's:' + k, curtoN(x[2], 18));
            ((d.rs[k] || [0, []])[1]).forEach(function (e) { no('e:' + e[0], e[1], e[4] ? 'cota' : 'rel', { b8: e[0], cnpj: e[5], razao: e[1], sit: e[2], uf: e[3], cota: e[4] }); liga('s:' + k, 'e:' + e[0]); socios2(e[0], e[6]); });
          });
          Object.keys(d.re).forEach(function (k) {
            no('a:' + k, 'Mesmo endereço', 'end', { razao: est[4] || 'Endereço', n: d.re[k][0] }); liga('e:' + b8, 'a:' + k);
            d.re[k][1].forEach(function (e) { no('e:' + e[0], e[1], e[4] ? 'cota' : 'rel', { b8: e[0], cnpj: e[6] || e[5], razao: e[1], sit: e[2], uf: e[3], cota: e[4] }); liga('a:' + k, 'e:' + e[0]); socios2(e[0], e[8]); });
          });
          var css = getComputedStyle(document.documentElement), cor = function (v, f) { return (css.getPropertyValue(v) || '').trim() || f; };
          var tinta = cor('--tinta', '#14213d'), acento = cor('--acento', '#1f4fd8'), linha = cor('--linha', '#c9d1e0'), papel = cor('--papel', '#fff');
          var g = cy({ container: box, elements: els, minZoom: 0.3, maxZoom: 2.5, wheelSensitivity: 0.25,
            style: [
              { selector: 'node', style: { label: 'data(label)', 'font-size': 10, color: tinta, 'text-wrap': 'wrap', 'text-max-width': 90, 'text-valign': 'bottom', 'text-margin-y': 4, 'background-color': '#8fa3c7', 'border-width': 2, 'border-color': papel, width: 22, height: 22 } },
              { selector: 'node[tipo="alvo"]', style: { 'background-color': acento, width: 44, height: 44, 'font-weight': 700 } },
              { selector: 'node[tipo="socio"]', style: { shape: 'diamond', 'background-color': '#7a4fb0', width: 28, height: 28 } },
              { selector: 'node[tipo="socio2"]', style: { shape: 'diamond', 'background-color': '#b9a3d9', width: 20, height: 20, 'font-size': 9 } },
              { selector: 'node[tipo="end"]', style: { shape: 'round-rectangle', 'background-color': '#4f8a2f', width: 28, height: 22 } },
              { selector: 'node[tipo="cota"]', style: { 'background-color': '#d9822b', width: 26, height: 26 } },
              { selector: 'edge', style: { width: 1.5, 'line-color': linha, label: 'data(label)', 'font-size': 8, color: tinta, 'text-rotation': 'autorotate', 'text-background-color': papel, 'text-background-opacity': 0.8 } },
              { selector: ':selected', style: { 'border-color': tinta, 'border-width': 3 } }],
            layout: { name: 'cose', animate: false, nodeRepulsion: 9000, idealEdgeLength: 70, padding: 20 } });
          var cb = dlg.querySelector('[data-baixadas]'), cs = dlg.querySelector('[data-socios2]');
          function atualizar() {
            var mostraB = !cb || cb.checked, mostraS = !cs || cs.checked;
            g.nodes().forEach(function (n) {
              var t = n.data('tipo');
              if (t === 'rel' || t === 'cota') n.style('display', (n.data('sit') === '08' && !mostraB) ? 'none' : 'element');
            });
            g.nodes('[tipo = "socio2"]').forEach(function (n) {
              var vivo = n.neighborhood('node').some(function (m) { return (m.data('tipo') === 'rel' || m.data('tipo') === 'cota') && m.style('display') !== 'none'; });
              n.style('display', mostraS && vivo ? 'element' : 'none');
            });
            dlg.querySelectorAll('li.baixada').forEach(function (li) { li.hidden = !mostraB; });
          }
          [cb, cs].forEach(function (c) { if (c) c.addEventListener('change', atualizar); });
          g.on('tap', 'node', function (ev) {
            var n = ev.target.data(), t = '';
            if (n.tipo === 'socio') t = '<strong>' + esc(n.razao) + '</strong> · ' + esc(n.qual || 'sócio') + (n.doc ? ' · ' + esc(n.doc) : '');
            else if (n.tipo === 'end') t = '<strong>Endereço da empresa</strong>: ' + esc(n.razao) + ' · ' + n.n + ' outra(s) empresa(s) ativa(s) neste endereço.';
            else t = '<strong>' + esc(n.razao) + '</strong>' + (n.cnpj ? ' · ' + esc(cnpjFmt(n.cnpj)) : '') + (n.sit ? ' · ' + esc(SIT[n.sit] || n.sit) : '') + (n.uf ? ' · ' + esc(n.uf) : '') + (n.cota ? ' · recebeu ' + brl(n.cota) + ' de parlamentares' : '');
            if (n.b8 && n.b8 !== b8) t += ' <button type="button" class="link-ver" data-centrar="' + esc(n.b8) + '" data-cnpj="' + esc(n.cnpj || '') + '">ver relações desta empresa</button>';
            info.innerHTML = t;
            var bt = info.querySelector('[data-centrar]'); if (bt) bt.addEventListener('click', function () { abrirRelacoes(bt.getAttribute('data-cnpj'), bt.getAttribute('data-centrar'), [cnpj, b8, voltar]); });
          });
        }).catch(function () { box.innerHTML = '<p class="apoio">Não consegui carregar o gráfico; use as listas abaixo.</p>'; });
      });
    }
    function abrirForn(e, gente, fmtDoc) {
      var dlg = raiz.querySelector('dialog.cg-dialog:not(.cg-rel)');
      if (!dlg) { dlg = document.createElement('dialog'); dlg.className = 'cg-dialog'; raiz.appendChild(dlg); dlg.addEventListener('click', function (ev) { if (ev.target === dlg) dlg.close(); }); }
      var ids = Object.keys(e.pes).sort(function (x, y) { return e.pes[y] - e.pes[x]; });
      dlg.innerHTML = '<h3>' + esc(e.nome) + '</h3><p class="apoio">CNPJ/CPF: <strong>' + esc(fmtDoc(e.doc)) + '</strong> · total recebido dos parlamentares abaixo: <strong>' + brl(e.total) + '</strong></p>' +
        '<ol class="hemi-lista">' + ids.map(function (id) {
          var g = gente[id]; if (!g) return '';
          var im = g[4] ? '<img class="mini-foto" src="' + esc(g[4]) + '" alt="" width="32" height="32" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.style.visibility=\'hidden\'">' : '<i class="mini-foto"></i>';
          return '<li>' + im + '<a href="' + RAIZ + g[1] + '">' + esc(g[0]) + '</a> <span>' + esc(g[3]) + '-' + esc(g[2]) + '</span><b>' + brl(e.pes[id]) + '</b></li>';
        }).join('') + '</ol><p><button type="button" class="botao" data-fechar>Fechar</button></p>';
      dlg.querySelector('[data-fechar]').addEventListener('click', function () { dlg.close(); });
      if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
    }
    function pagamentos() {
      if (!pag) return;
      var chaves = [], rot = [];
      escolhidos().forEach(function (i) { chaves.push('p-' + P[i].k); rot.push(P[i].s); });
      if (!chaves.length) cg.lista().forEach(function (u) { chaves.push('uf-' + u); rot.push(u); });
      pag.hidden = !chaves.length; if (!chaves.length) return;
      var per = cg.periodo(), meu = ++gen;
      Promise.all(chaves.map(carregar)).then(function (rs) {
        if (meu !== gen) return;
        var ok = function (y) { y = +y; return per === '0' || (cg.LEG[per] ? y >= cg.LEG[per][0] && y <= cg.LEG[per][1] : String(y) === per); };
        var cat = {}, forn = {}, gente = {};
        rs.forEach(function (r) {
          Object.keys(r.g || {}).forEach(function (k) { gente[k] = r.g[k]; });
          Object.keys(r.c).forEach(function (y) { if (ok(y)) r.c[y].forEach(function (t) { cat[t[0]] = (cat[t[0]] || 0) + t[1]; }); });
          Object.keys(r.f).forEach(function (y) { if (ok(y)) r.f[y].forEach(function (t) {
            var dg = String(t[2] || '').replace(/\D/g, ''), k = dg.length >= 11 ? dg : 'n:' + t[0].toUpperCase();
            var e = forn[k] || (forn[k] = { nome: t[0], doc: t[2] || '', total: 0, pes: {}, rf: 0 });
            if (t[4]) e.rf = 1;
            e.total += t[1]; if (!e.doc && t[2]) e.doc = t[2];
            t[3].forEach(function (q) { e.pes[q[0]] = (e.pes[q[0]] || 0) + q[1]; });
          }); });
        });
        function fmtDoc(d) {
          var n = String(d || '').replace(/\D/g, '');
          if (/^\d{14}$/.test(d || '') || (n.length === 14 && !/[*]/.test(d))) return n.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
          if (n.length === 11 && !/[*]/.test(d)) return n.replace(/^\d{3}(\d{3})(\d{3})\d{2}$/, '***.$1.$2-**');
          return d || '—';
        }
        var ordenar = function (o) { return Object.keys(o).map(function (k) { return [k, o[k]]; }).sort(function (a, b) { return b[1] - a[1]; }); };
        var C = ordenar(cat), F = Object.keys(forn).map(function (k) { return forn[k]; }).sort(function (x, y) { return y.total - x.total; }), tot = 0; C.forEach(function (t) { tot += t[1]; });
        var perTxt = per === '0' ? 'desde 2014' : cg.LEG[per] ? 'na legislatura ' + cg.LEG[per][0] + '–' + cg.LEG[per][1] : 'em ' + per;
        var h = '<h3>Pagamentos da cota feitos por ' + esc(rot.join(', ')) + '</h3><p class="apoio">Período: <strong>' + perTxt + '</strong> (muda no seletor acima do mapa) · total pago: <strong>' + brl(tot) + '</strong></p>';
        h += '<div class="mapa-vis" role="group"><button type="button" data-pag-aba="c" aria-pressed="' + (aba === 'c') + '">Por tipo de gasto</button><button type="button" data-pag-aba="f" aria-pressed="' + (aba === 'f') + '">Para quem pagaram</button></div>';
        function avatar(pid, v) {
          var g = gente[pid]; if (!g) return '';
          var t = g[0] + ' (' + g[3] + '-' + g[2] + '): ' + brl(v);
          return '<a class="av" href="' + RAIZ + g[1] + '" title="' + esc(t) + '">' + (g[4] ? '<img class="mini-foto" src="' + esc(g[4]) + '" alt="' + esc(g[0]) + '" width="30" height="30" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.style.visibility=\'hidden\'">' : '<i class="mini-foto"></i>') + '</a>';
        }
        function quem(e, i) {
          var ids = Object.keys(e.pes).sort(function (x, y) { return e.pes[y] - e.pes[x]; });
          var mostra = ids.slice(0, 4).map(function (id) { return avatar(id, e.pes[id]); }).join('');
          return '<div class="avs">' + mostra + '</div><button type="button" class="link-ver" data-forn="' + i + '">' + (ids.length > 4 ? '+' + (ids.length - 4) + ' · ver todos (' + ids.length + ')' : ids.length + ' parlamentar' + (ids.length > 1 ? 'es' : '')) + '</button>';
        }
        var FL = F.slice(0, 30), L = aba === 'c' ? C.slice(0, 20) : FL;
        if (aba === 'c') {
          h += L.length ? '<div class="tabela-rolagem"><table class="tabela-pag"><thead><tr><th>Tipo de gasto</th><th class="num">Valor</th><th class="num">%</th></tr></thead><tbody>' +
            L.map(function (t) { return '<tr><td>' + esc(t[0]) + '</td><td class="num">' + brl(t[1]) + '</td><td class="num">' + (tot ? Math.round(t[1] / tot * 100) : 0) + '%</td></tr>'; }).join('') + '</tbody></table></div>' : '<p class="apoio">Sem pagamentos registrados neste período.</p>';
        } else {
          h += L.length ? '<div class="tabela-rolagem"><table class="tabela-pag"><thead><tr><th>Fornecedor</th><th>CNPJ/CPF</th><th class="num">Valor</th><th>Parlamentares que pagaram</th></tr></thead><tbody>' +
            FL.map(function (e, i) { return '<tr' + (e.rf ? ' class="linha-rel" data-rel-linha="' + esc(String(e.doc).replace(/\\D/g, '')) + '"' : '') + '><td>' + esc(e.nome) + '</td><td class="doc">' + (e.rf ? '<a href="#" class="doc-link" data-rel="' + esc(String(e.doc).replace(/\D/g, '')) + '" title="Ver sócios e empresas ligadas">' + esc(fmtDoc(e.doc)) + '</a>' : esc(fmtDoc(e.doc))) + '</td><td class="num">' + brl(e.total) + '</td><td class="quem">' + quem(e, i) + '</td></tr>'; }).join('') + '</tbody></table></div>' : '<p class="apoio">Sem pagamentos registrados neste período.</p>';
        }
        h += '<p class="nota">' + (aba === 'f' ? 'Fornecedores: os maiores de cada parlamentar em cada ano (até 15), por isso a lista pode somar menos que o total. ' : '') + 'Cota para o exercício da atividade parlamentar (Câmara) e CEAPS (Senado); gasto não é irregularidade.</p>';
        pag.innerHTML = h;
        pag.querySelectorAll('[data-forn]').forEach(function (b) { b.addEventListener('click', function () { abrirForn(FL[+b.getAttribute('data-forn')], gente, fmtDoc); }); });
        pag.querySelectorAll('tr[data-rel-linha]').forEach(function (tr) {
          tr.addEventListener('click', function (ev) { if (ev.target.closest && ev.target.closest('a,button')) return; abrirRelacoes(tr.getAttribute('data-rel-linha')); });
        });
        pag.querySelectorAll('[data-rel]').forEach(function (l) { l.addEventListener('click', function (ev) { ev.preventDefault(); abrirRelacoes(l.getAttribute('data-rel')); }); });
        pag.querySelectorAll('[data-pag-aba]').forEach(function (b) { b.addEventListener('click', function () { aba = b.getAttribute('data-pag-aba'); pagamentos(); }); });
      });
    }
    cg.ouv.push(function () { marcar(); desenhar(); pagamentos(); });
    marcar(); desenhar(); pagamentos();
  }

  function iniciarPosicao(sec) {
    var url = sec.getAttribute('data-url'), cargo = sec.getAttribute('data-cargo'), pid = sec.getAttribute('data-id');
    var sel = sec.querySelector('[data-pos-ano]'), texto = sec.querySelector('[data-pos-texto]'), trilho = sec.querySelector('[data-pos-trilho]');
    var a = sec.querySelector('[data-pos-comparar]'); if (a && pid) a.href = RAIZ + 'comparar/?p=' + pid;
    get('data/ranking.json').then(function (d) {
      var porAno = d[cargo] || {}, anos = Object.keys(porAno).filter(function (y) {
        return (porAno[y] || []).some(function (r) { return r[1] === url && r[4] > 0; });
      }).sort().reverse();
      if (!anos.length) return;
      sec.hidden = false;
      anos.forEach(function (y) { var o = document.createElement('option'); o.value = y; o.textContent = y + (y === sec.getAttribute('data-atual') ? ' (parcial)' : ''); sel.appendChild(o); });
      var ini = anos.indexOf(sec.getAttribute('data-ano')); sel.value = anos[ini >= 0 ? ini : 0];
      function desenhar() {
        var lista = (porAno[sel.value] || []).filter(function (r) { return r[4] > 0; });
        var vs = lista.map(function (r) { return r[4]; }).sort(function (x, y) { return x - y; });
        var eu = lista.filter(function (r) { return r[1] === url; })[0]; if (!eu || !vs.length) return;
        var abaixo = vs.filter(function (v) { return v < eu[4]; }).length, pct = Math.round(abaixo / vs.length * 100);
        var med = vs[Math.floor(vs.length / 2)], max = vs[vs.length - 1], rot = cargo === 'senador' ? 'senadores' : 'deputados';
        texto.innerHTML = 'Em <strong>' + sel.value + '</strong>, usou <strong>' + brl(eu[4]) + '</strong> da cota: mais que <strong>' + pct + '%</strong> dos ' + vs.length + ' ' + rot +
          ' com gasto no ano. A mediana é ' + brl(med) + '.' + (eu[5] && eu[5] < 12 ? ' Considere que foram ' + eu[5] + ' meses com despesa.' : '');
        trilho.textContent = '';
        var pos = function (v) { return 'calc(14px + (100% - 28px) * ' + (max > 0 ? v / max : 0).toFixed(4) + ')'; };
        vs.forEach(function (v) { var t = document.createElement('i'); t.className = 'pos-traco'; t.style.left = pos(v); trilho.appendChild(t); });
        var m = document.createElement('b'); m.className = 'pos-med'; m.style.left = pos(med); m.title = 'Mediana'; trilho.appendChild(m);
        var pt = document.createElement('em'); pt.className = 'pos-ponto'; pt.style.left = pos(eu[4]); pt.title = brl(eu[4]); trilho.appendChild(pt);
        trilho.classList.remove('pronto'); void trilho.offsetWidth; trilho.classList.add('pronto');
      }
      sel.addEventListener('change', desenhar); desenhar();
    });
  }

  function iniciarMapaDinheiro(raiz, cg) {
    var el = raiz.querySelector('[data-mapa-dados]'); if (!el) return;
    var D; try { D = JSON.parse(el.textContent); } catch (e) { return; }
    var esc = function (v) { return String(v === null || v === undefined ? '' : v).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
    var POS = { RR: [2, 0], AP: [4, 0], AM: [1, 1], PA: [3, 1], MA: [4, 1], CE: [5, 1], RN: [6, 1], AC: [0, 2], RO: [1, 2], MT: [2, 2], TO: [3, 2], PI: [4, 2], PE: [5, 2], PB: [6, 2],
      GO: [2, 3], DF: [3, 3], BA: [4, 3], AL: [5, 3], SE: [6, 3], MS: [2, 4], MG: [3, 4], ES: [4, 4], PR: [2, 5], SP: [3, 5], RJ: [4, 5], SC: [2, 6], RS: [2, 7] };
    var selT = raiz.querySelector('[data-mapa-tipo]'), selA = raiz.querySelector('[data-mapa-ano]'), grade = raiz.querySelector('[data-mapa-grade]'), painel = raiz.querySelector('[data-mapa-painel]');
    var modo = raiz.querySelector('[data-mapa-modo]');
    var LEG = cg.LEG; cg.periodo = function () { return selA.value; };
    function soma(d, t, a) {
      var m = d && d[t]; if (!m) return 0;
      if (LEG[a]) { var s = 0, y; for (y = LEG[a][0]; y <= LEG[a][1]; y++) s += m[String(y)] || 0; return s; }
      return m[a] || 0;
    }
    function nomePer(a) { return a === '0' ? 'desde 2014' : LEG[a] ? 'na legislatura ' + LEG[a][0] + '–' + LEG[a][1] : 'em ' + a; }
    function clicar(uf) { if (cg.nomes().length) { cg.sel = {}; cg.ufs = {}; } if (cg.ufs[uf]) delete cg.ufs[uf]; else cg.ufs[uf] = true; cg.dest = ''; cg.notificar(); }
    function curto(v) { return v >= 1e9 ? (v / 1e9).toFixed(1).replace('.', ',') + ' bi' : v >= 1e6 ? Math.round(v / 1e6) + ' mi' : v >= 1e3 ? Math.round(v / 1e3) + ' mil' : String(Math.round(v)); }
    Object.keys(POS).forEach(function (uf) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'uf-tile'; b.setAttribute('data-uf', uf);
      b.style.gridColumn = String(POS[uf][0] + 1); b.style.gridRow = String(POS[uf][1] + 1);
      b.innerHTML = '<b>' + uf + '</b><span></span>';
      b.addEventListener('click', function () { clicar(uf); });
      grade.appendChild(b);
    });
    var svgBox = raiz.querySelector('[data-mapa-svg]'), paths = {}, NS = 'http://www.w3.org/2000/svg';
    get('static/mapa-brasil.json').then(function (m) {
      var svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', m.viewBox); svg.setAttribute('role', 'group'); svg.setAttribute('aria-label', 'Mapa do Brasil por estado');
      m.locais.forEach(function (l) {
        var p = document.createElementNS(NS, 'path'); p.setAttribute('d', l[1]); p.setAttribute('class', 'uf-path'); p.setAttribute('data-uf', l[0]);
        p.setAttribute('tabindex', '0'); p.setAttribute('role', 'button');
        p.addEventListener('click', function () { clicar(l[0]); });
        p.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); clicar(l[0]); } });
        svg.appendChild(p); paths[l[0]] = p;
      });
      svgBox.appendChild(svg); desenhar();
    }).catch(function () { setVis('grade'); });
    function setVis(v) {
      svgBox.hidden = v !== 'mapa'; grade.hidden = v !== 'grade';
      raiz.querySelectorAll('[data-mapa-vis]').forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-mapa-vis') === v ? 'true' : 'false'); });
    }
    raiz.querySelectorAll('[data-mapa-vis]').forEach(function (b) { b.addEventListener('click', function () { setVis(b.getAttribute('data-mapa-vis')); }); });
    function valores() {
      var t = selT.value, a = selA.value, out = {}, max = 0, ct = cg.nomes && cg.nomes().length ? cg.contar() : null;
      Object.keys(POS).forEach(function (uf) { var v = ct ? (ct[uf] || 0) : soma(D[uf], t, a); out[uf] = v; if (v > max) max = v; });
      return { v: out, max: max, ct: !!ct };
    }
    function desenhar() {
      var r = valores(), nm = cg.nomes ? cg.nomes() : [];
      if (modo) modo.textContent = r.ct ? 'Cor do mapa: quantos parlamentares de ' + nm.join(', ') + ' (deputados e senadores) cada estado tem.' :
        'Cor do mapa: ' + (selT.value === 'e' ? 'emendas pagas ao estado' : 'cota usada pelos parlamentares do estado') + ' (' + nomePer(selA.value) + '). Mais forte = mais dinheiro.';
      var rot = function (uf) { return r.v[uf] ? (r.ct ? r.v[uf] + ' parlamentar(es)' : brl(r.v[uf])) : (r.ct ? 'nenhum' : 'sem dados'); };
      Object.keys(paths).forEach(function (uf) {
        var i = r.max ? Math.sqrt(r.v[uf] / r.max) : 0, p = paths[uf];
        p.style.setProperty('--i', (0.08 + 0.92 * i).toFixed(3)); p.classList.toggle('sel', !!cg.ufs[uf]);
        p.setAttribute('aria-label', (D[uf] ? D[uf].n : uf) + ': ' + rot(uf));
        if (cg.ufs[uf] && p.parentNode) p.parentNode.appendChild(p);
      });
      grade.querySelectorAll('.uf-tile').forEach(function (b) {
        var uf = b.getAttribute('data-uf'), i = r.max ? Math.sqrt(r.v[uf] / r.max) : 0;
        b.style.setProperty('--i', (0.08 + 0.92 * i).toFixed(3));
        b.classList.toggle('forte', i > 0.55); b.classList.toggle('sel', !!cg.ufs[uf]);
        b.querySelector('span').textContent = r.v[uf] ? (r.ct ? String(r.v[uf]) : curto(r.v[uf])) : '—';
        b.setAttribute('aria-label', (D[uf] ? D[uf].n : uf) + ': ' + rot(uf));
      });
    }
    function mostrar() {
      var L = cg.lista(); painel.hidden = !L.length; if (!L.length) { painel.innerHTML = ''; return; }
      var a = selA.value, per = nomePer(a), e = 0, c = 0, p = 0;
      L.forEach(function (u) { if (D[u]) { e += soma(D[u], 'e', a); c += soma(D[u], 'c', a); p += D[u].p; } });
      var tit = L.length === 1 ? esc(D[L[0]] ? D[L[0]].n : L[0]) : L.length + ' estados: ' + esc(L.join(', '));
      painel.innerHTML = '<h3>' + tit + '</h3><dl class="mapa-num"><div><dt>Emendas pagas ' + (L.length === 1 ? 'ao estado ' : 'aos estados ') + per + '</dt><dd>' + (e ? brl(e) : '—') + '</dd></div>' +
        '<div><dt>Cota usada por ' + p + ' deputados e senadores ' + per + '</dt><dd>' + (c ? brl(c) : '—') + '</dd></div></dl>' +
        '<p class="hemi-acoes">' + L.map(function (u) { return '<a class="botao botao-leve" href="' + RAIZ + 'estado/' + u.toLowerCase() + '/">Ver ' + esc(D[u] ? D[u].n : u) + '</a>'; }).join('') + '</p>';
    }
    [selT, selA].forEach(function (s) { s.addEventListener('change', function () { cg.notificar(); }); });
    cg.ouv.push(function () { desenhar(); mostrar(); });
    desenhar();
  }
  document.querySelectorAll('[data-busca]').forEach(function (f) {
    if (f.hasAttribute('data-comparar')) return;
    iniciarBusca(f, function (d) { location.href = RAIZ + d.url; });
  });
  document.querySelectorAll('[data-uf-select]').forEach(function (s) { s.addEventListener('change', function () { if (s.value) location.href = RAIZ + 'estado/' + s.value + '/'; }); });
  var es = document.querySelector('[data-estado]'); if (es) iniciarEstado(es);
  var po_ = document.querySelector('[data-posicao]'); if (po_) iniciarPosicao(po_);
  var cg_ = document.querySelector('[data-congresso]'); if (cg_) iniciarCongresso(cg_);
  var r = document.querySelector('[data-ranking]'); if (r) iniciarRanking(r);
  document.querySelectorAll('[data-emendas]').forEach(function (b) { iniciarEmendas(b); carregarTce().then(function () { b.dispatchEvent(new Event('tce')); }); });
  var te = document.querySelector('[data-emenda]'); if (te) iniciarTelaEmenda(te);
  var pts_ = document.querySelector('[data-partidos]'); if (pts_) iniciarPartidos(pts_);
  var ptd_ = document.querySelector('[data-partido-dados]'); if (ptd_) iniciarPartidoDados(ptd_);
  var fo_ = document.querySelector('[data-forn]'); if (fo_) iniciarForn(fo_);
  var cu_ = document.querySelector('[data-custo]'); if (cu_) iniciarCusto(cu_);
  var at_ = document.querySelector('[data-atencao]');
  if (at_) { var sel_ = at_.querySelector('[data-at-ano]'); sel_.addEventListener('change', function () { document.querySelectorAll('[data-at-visao]').forEach(function (d) { d.hidden = d.getAttribute('data-at-visao') !== sel_.value; }); }); }
  var pv_ = document.querySelector('[data-privados]'); if (pv_) iniciarPrivados(pv_);
  var pa_ = document.querySelector('[data-pares]'); if (pa_) iniciarPares(pa_);
  var pm_ = document.querySelector('[data-pm]'); if (pm_) iniciarMeses(pm_);
  var tr_ = document.querySelector('[data-recebedor]'); if (tr_) iniciarTelaRecebedor(tr_);
  var mu = document.querySelector('[data-municipios]'); if (mu) iniciarMunicipios(mu);
  var m1 = document.querySelector('[data-municipio]'); if (m1) iniciarMunicipio(m1);
  var rb = document.querySelector('[data-recebedores]'); if (rb) iniciarRecebedores(rb);
  var px = document.querySelector('[data-pix]'); if (px) iniciarPix(px);
  var c = document.querySelector('[data-comparacao]'); if (c) iniciarComparacao(c, document.querySelector('[data-comparar]'));
})();
