"""Remuneracao bruta dos assessores de gabinete (dado publico: Camara e Senado publicam por nome e mes).

Camara: CSV mensal "Remuneracao mensal dos servidores" (transparencia/recursos-humanos/remuneracao).
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


def _somar(con, linhas, cargo, padrao, ano, mes, rotulo, mostrar):
    indice = g._indice(con, cargo)
    col = _coluna_bruto(linhas[0]) if linhas else None
    if mostrar:
        print(f"  Colunas da remuneracao {rotulo}: {sorted(linhas[0].keys())}; coluna de valor bruto: {col}")
    if col is None:
        return {}, 0
    acum, sem = {}, 0
    for l in linhas:
        lot = g._nome_norm(g._campo(l, "lotacao"))
        if "GAB" not in lot:
            continue
        m = padrao.search(lot)
        if not m:
            continue
        resto = re.sub(r"^[A-Z0-9]{3,12}\s+(?=.*\bGABINETE\b)", "", m.group(1)).strip()
        pid = g._achar_parlamentar(resto, indice)
        nome = g._campo(l, "nome")
        if pid is None or not nome or g._nome_norm(nome) == g._nome_norm(resto):
            sem += 1
            continue
        k = (pid, g._nome_norm(nome))
        v = c.numero(l.get(col, ""))
        if k not in acum:
            acum[k] = [nome.strip()[:120], g._campo(l, "cargo").strip()[:120], 0.0]
        acum[k][2] += v
    return acum, sem


def _carregado(con, fonte, ano, mes):
    return con.execute("SELECT 1 FROM gabinete_remun WHERE fonte=? AND ano=? AND mes=? LIMIT 1", (fonte, ano, mes)).fetchone() is not None


def rodar(con):
    hoje = date.today()
    novos = 0
    primeiro = {"gab_camara": True, "gab_senado": True}
    for ano, mes in _meses(hoje):
        recente = (hoje.year * 12 + hoje.month) - (ano * 12 + mes) <= 2
        for rotulo, cargo, padrao, fonte, baixar in (("Camara", "deputado_federal", g.PAD_CAMARA, "gab_camara", _baixar_camara),
                                                    ("Senado", "senador", g.PAD_SENADO, "gab_senado", _baixar_senado)):
            if _carregado(con, fonte, ano, mes) and not recente:
                continue
            linhas = baixar(ano, mes)
            if not linhas:
                print(f"  AVISO: remuneracao {rotulo} {mes:02d}/{ano} indisponivel", file=sys.stderr)
                continue
            acum, sem = _somar(con, linhas, cargo, padrao, ano, mes, rotulo, primeiro[fonte])
            primeiro[fonte] = False
            if not acum:
                print(f"  AVISO: remuneracao {rotulo} {mes:02d}/{ano}: nenhum assessor identificado ({len(linhas)} linhas)", file=sys.stderr)
                continue
            con.execute("DELETE FROM gabinete_remun WHERE fonte=? AND ano=? AND mes=?", (fonte, ano, mes))
            con.executemany("INSERT INTO gabinete_remun (pessoa_id, ano, mes, nome, cargo, bruto, fonte) VALUES (?,?,?,?,?,?,?)",
                            [(pid, ano, mes, v[0], v[1], round(v[2], 2), fonte) for (pid, _), v in acum.items()])
            c.log(con, fonte, "remuneracao", ano, len(acum))
            con.commit()
            novos += len(acum)
            print(f"Remuneracao {rotulo} {mes:02d}/{ano}: {len(acum)} assessores, {len({k[0] for k in acum})} gabinetes ({sem} linhas de gabinete sem parlamentar)")
    return novos
