"""Remuneracao bruta dos assessores de gabinete (dado publico: Camara e Senado publicam por nome e mes).

Camara: o CSV mensal publicado e consolidado (sem nome nem lotacao), entao nao liga ao gabinete; so sondamos a pagina de cada deputado.
Senado: API administrativa de remuneracoes por ano/mes.
O gabinete vem da lotacao (mesma regra de gabinete.py). Soma por pessoa e mes; guarda o valor bruto.
Formatos escritos de memoria: o log imprime as colunas reais e quantas linhas ficaram sem gabinete.
"""
import re
import sys
from collections import defaultdict
from datetime import date

from . import common as c
from . import gabinete as g

MESES_PT = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
MESES_BUSCA = 24
BASE_CAMARA = "https://www2.camara.leg.br/transparencia/recursos-humanos/remuneracao/relatorios-consolidados-por-ano-e-mes/{ano}/{mes}-de-{ano}-csv"
SUFIXOS_CAMARA = ("", "/at_download/file", "/@@download/file", "/download")
BASE_SENADO = "https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/remuneracoes/{ano}/{mes}"
VARIANTES_SENADO = ("?formato=csv", "?formato=json", "")
BRUTO = ("remuneracao bruta", "total bruto", "bruto", "total de rendimentos", "total rendimentos", "rendimento total", "total da remuneracao", "remuneracao total")


def _meses(hoje=None):
    hoje = hoje or date.today()
    a, m = hoje.year, hoje.month
    for _ in range(MESES_BUSCA):
        yield a, m
        m -= 1
        if m == 0:
            a, m = a - 1, 12


def _coluna_bruto(l):
    for k in BRUTO:
        for col in l:
            if col == k:
                return col
    for k in BRUTO:
        for col in l:
            if k in col and "liquid" not in col and "desconto" not in col:
                return col
    return None


def _baixar_camara(ano, mes):
    for suf in SUFIXOS_CAMARA:
        u = BASE_CAMARA.format(ano=ano, mes=MESES_PT[mes - 1]) + suf
        try:
            r = c.get(u, timeout=300, rapido=True)
            if r.content[:1] == b"<":
                continue
            return g._ler(r.content)
        except Exception:
            continue
    return []


def _baixar_senado(ano, mes):
    for var in VARIANTES_SENADO:
        try:
            r = c.get(BASE_SENADO.format(ano=ano, mes=mes) + var, timeout=300, rapido=True)
            linhas = g._ler(r.content)
            if linhas:
                return linhas
        except Exception:
            continue
    return []


COMPONENTES_SENADO = ("remuneracao basica", "vantagens pessoais", "funcao comissionada", "gratificacao natalina", "horas extras", "outras eventuais", "abono permanencia")


def _somar_senado(con, linhas, mostrar):
    """O arquivo do Senado traz nome e valores, sem lotacao: ligamos pelo nome aos assessores atuais de cada senador.
    Valor = remuneracao basica + vantagens + funcao comissionada + 13o + horas extras + eventuais + abono (sem verbas indenizatorias)."""
    por_nome = defaultdict(set)
    for pid, nome in con.execute("SELECT pessoa_id, nome FROM gabinete_pessoa WHERE fonte='gab_senado'"):
        por_nome[g._nome_norm(nome)].add(pid)
    if mostrar and linhas:
        l0 = linhas[0]
        print(f"  Exemplo de linha do Senado: {dict(list(l0.items())[:20])}")
    acum, sem = {}, 0
    for l in linhas:
        nome = l.get("nome", "")
        ids = por_nome.get(g._nome_norm(nome))
        if not ids or len(ids) != 1:
            sem += 1
            continue
        pid = next(iter(ids))
        v = sum(c.numero(l.get(k, "")) for k in COMPONENTES_SENADO)
        k = (pid, g._nome_norm(nome))
        if k not in acum:
            cargo = con.execute("SELECT cargo FROM gabinete_pessoa WHERE pessoa_id=? AND fonte='gab_senado' AND nome=? LIMIT 1", (pid, nome)).fetchone()
            acum[k] = [nome.strip()[:120], (cargo[0] if cargo else "")[:120], 0.0]
        acum[k][2] += v
    return acum, sem


def _sonda_camara(con):
    """O arquivo mensal da Camara e consolidado (sem nome nem lotacao). Sonda a pagina do gabinete de um deputado para
    ver se ela traz a remuneracao por secretario; so imprime o formato no log."""
    r = con.execute("SELECT f.id_externo FROM pessoa p JOIN pessoa_fonte f ON f.pessoa_id=p.id AND f.fonte='camara' WHERE p.cargo='deputado_federal' ORDER BY p.id LIMIT 1").fetchone()
    if not r:
        return
    for u in (f"https://www.camara.leg.br/deputados/{r[0]}/pessoal-gabinete", f"https://dadosabertos.camara.leg.br/api/v2/deputados/{r[0]}"):
        try:
            resp = c.get(u, timeout=60, rapido=True)
            txt = re.sub(r"\s+", " ", c.decodificar(resp.content))
            i = txt.lower().find("remunera")
            print(f"  [sonda Camara] {u}: {len(txt)} caracteres; trecho: {txt[max(0, i - 300):i + 900] if i >= 0 else txt[:600]}")
        except Exception as e:
            print(f"  [sonda Camara] {u}: {e}", file=sys.stderr)


def _carregado(con, fonte, ano, mes):
    return con.execute("SELECT 1 FROM gabinete_remun WHERE fonte=? AND ano=? AND mes=? LIMIT 1", (fonte, ano, mes)).fetchone() is not None


def rodar(con):
    hoje = date.today()
    novos = 0
    mostrar = True
    _sonda_camara(con)
    for ano, mes in _meses(hoje):
        fonte = "gab_senado"
        recente = (hoje.year * 12 + hoje.month) - (ano * 12 + mes) <= 2
        if _carregado(con, fonte, ano, mes) and not recente:
            continue
        linhas = _baixar_senado(ano, mes)
        if not linhas:
            print(f"  AVISO: remuneracao Senado {mes:02d}/{ano} indisponivel", file=sys.stderr)
            continue
        acum, sem = _somar_senado(con, linhas, mostrar)
        mostrar = False
        if not acum:
            print(f"  AVISO: remuneracao Senado {mes:02d}/{ano}: nenhum assessor identificado ({len(linhas)} linhas)", file=sys.stderr)
            continue
        con.execute("DELETE FROM gabinete_remun WHERE fonte=? AND ano=? AND mes=?", (fonte, ano, mes))
        con.executemany("INSERT INTO gabinete_remun (pessoa_id, ano, mes, nome, cargo, bruto, fonte) VALUES (?,?,?,?,?,?,?)",
                        [(pid, ano, mes, v[0], v[1], round(v[2], 2), fonte) for (pid, _), v in acum.items()])
        c.log(con, fonte, "remuneracao", ano, len(acum))
        con.commit()
        novos += len(acum)
        print(f"Remuneracao Senado {mes:02d}/{ano}: {len(acum)} assessores, {len({k[0] for k in acum})} gabinetes")
    return novos
