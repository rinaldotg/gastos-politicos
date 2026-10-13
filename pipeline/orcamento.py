"""Orcamento da Presidencia da Republica por programa e acao (execucao da despesa, Portal da Transparencia).

Mostra para onde o dinheiro dos orgaos da Presidencia foi (programa/acao), nao gasto pessoal.
Atribuido ao ocupante do cargo no mes. Agregado por mes/orgao/programa/acao para manter o banco pequeno.
Colunas escritas de memoria: o log imprime as reais.
"""
import io
import sys
import zipfile
from collections import defaultdict
from datetime import date

from . import common as c
from .presidencia import eh_presidencia, garantir_presidentes, ocupante

URL = "https://portaldatransparencia.gov.br/download-de-dados/despesas-execucao/{ano}{mes:02d}"


def carregar_mes(con, ids, ano, mes):
    lote = f"orcamento:{ano}{mes:02d}"
    try:
        r = c.get(URL.format(ano=ano, mes=mes), timeout=900)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        bruto = z.open(z.namelist()[0]).read()
    except Exception as e:
        print(f"  AVISO: execucao da despesa {ano}-{mes:02d} indisponivel: {e}", file=sys.stderr)
        return None
    colunas, linhas, col = c.ler_csv(bruto)
    pid = ocupante(ids, f"{ano}-{mes:02d}-15")
    agg = defaultdict(lambda: [0.0, 0.0, 0.0])
    for l in linhas:
        if not eh_presidencia(col(l, "Nome Órgão Superior", "Nome Orgao Superior")):
            continue
        k = (col(l, "Nome Órgão Subordinado", "Nome Orgao Subordinado"), col(l, "Nome Programa Orçamentário", "Nome Programa Orcamentario"),
             col(l, "Nome Ação", "Nome Acao"))
        v = agg[k]
        v[0] += c.numero(col(l, "Valor Empenhado (R$)", "Valor Empenhado"))
        v[1] += c.numero(col(l, "Valor Liquidado (R$)", "Valor Liquidado"))
        v[2] += c.numero(col(l, "Valor Pago (R$)", "Valor Pago"))
    con.execute("DELETE FROM orcamento_acao WHERE arquivo=?", (lote,))
    if pid:
        con.executemany("""INSERT INTO orcamento_acao (pessoa_id, ano, mes, orgao, programa, acao, empenhado, liquidado, pago, arquivo)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        [(pid, ano, mes, o, p, a, *v, lote) for (o, p, a), v in agg.items()])
    con.commit()
    return len(agg), colunas


def rodar(con, anos, recarregar_desde=None):
    ids = garantir_presidentes(con)
    hoje = date.today()
    recarregar_desde = recarregar_desde or hoje.year - 1
    falhas = 0
    for ano in anos:
        total = 0
        for mes in range(1, 13):
            if (ano, mes) > (hoje.year, hoje.month):
                break
            lote = f"orcamento:{ano}{mes:02d}"
            if ano < recarregar_desde and con.execute("SELECT 1 FROM orcamento_acao WHERE arquivo=? LIMIT 1", (lote,)).fetchone():
                continue
            res = carregar_mes(con, ids, ano, mes)
            if res is None:
                falhas += 1
                if falhas >= 3:
                    print("\nPARADO: 3 downloads seguidos recusados pelo Portal. Espere 1-2 horas e rode de novo.", file=sys.stderr)
                    return
            if res:
                falhas = 0
                total += res[0]
                if ano == anos[0] and mes == 1:
                    print(f"  Colunas da execucao da despesa: {res[1]}")
        c.log(con, "portal", "orcamento", ano, total)
        print(f"Orcamento da Presidencia {ano}: {total} linhas (mes x orgao x programa x acao)")
