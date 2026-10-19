"""Orcamento da Presidencia da Republica por programa e acao (execucao da despesa, Portal da Transparencia).

Mostra para onde o dinheiro dos orgaos da Presidencia foi (programa/acao), nao gasto pessoal.
Atribuido ao ocupante do cargo no mes. Agregado por mes/orgao/programa/acao para manter o banco pequeno.
Colunas escritas de memoria: o log imprime as reais.
"""
import io
import re
import sys
import zipfile
from collections import defaultdict
from datetime import date

from . import common as c
from .presidencia import eh_presidencia, garantir_presidentes, ocupante

ANO_MIN_MINISTERIOS = 2019  # custo por ministerio: a partir deste ano (cada mes e um download grande; amplie aqui se quiser mais anos)
URL = "https://portaldatransparencia.gov.br/download-de-dados/despesas-execucao/{ano}{mes:02d}"


CUSTEIO = re.compile(r"material de consumo|passagens|consultoria|terceiros|locacao de mao|arrendamento mercantil|diarias|auxilio.alimentacao|auxilio.transporte|"
                     r"obrigacoes tributarias|tecnologia da informacao|exercicios anteriores|indenizacoes e restituicoes")
INATIVOS = re.compile(r"aposentadoria|reserva remunerada|reformas|pensoes|pensao")


def bucket(grupo, modalidade, elemento=""):
    """Classifica o gasto: pessoal_ativo e custeio (= custo de funcionamento), inativos (aposentados e pensionistas),
    divida (juros e amortizacao) e programas (transferencias, beneficios, investimentos e demais gastos finalisticos)."""
    g, m, e = c.sem_acento(grupo).lower(), c.sem_acento(modalidade).lower(), c.sem_acento(elemento).lower()
    if "juros" in g or "amortiza" in g or "divida" in g:
        return "divida"
    if "pessoal" in g:
        return "inativos" if INATIVOS.search(e) else "pessoal_ativo"
    if "outras despesas correntes" in g and "transfer" not in m and CUSTEIO.search(e):
        return "custeio"
    return "programas"


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
    org = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])  # (orgao superior, bucket) -> empenhado, liquidado, pago, restos a pagar pagos
    guarda_org = ano >= ANO_MIN_MINISTERIOS
    for l in linhas:
        if guarda_org:
            sup = col(l, "Nome Órgão Superior", "Nome Orgao Superior")
            if sup:
                b = org[(sup, bucket(col(l, "Nome Grupo de Despesa"), col(l, "Modalidade da Despesa", "Nome Modalidade da Despesa"), col(l, "Nome Elemento de Despesa")))]
                b[0] += c.numero(col(l, "Valor Empenhado (R$)", "Valor Empenhado"))
                b[1] += c.numero(col(l, "Valor Liquidado (R$)", "Valor Liquidado"))
                b[2] += c.numero(col(l, "Valor Pago (R$)", "Valor Pago"))
                b[3] += c.numero(col(l, "Valor Restos a Pagar Pagos (R$)", "Valor Restos a Pagar Pagos"))
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
    con.execute("DELETE FROM despesa_orgao WHERE arquivo=?", (lote,))
    if guarda_org and org:
        con.executemany("INSERT INTO despesa_orgao (ano, mes, orgao, bucket, empenhado, liquidado, pago, rap_pago, arquivo) VALUES (?,?,?,?,?,?,?,?,?)",
                        [(ano, mes, o, bk, *v, lote) for (o, bk), v in org.items()])
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
            tem_pres = con.execute("SELECT 1 FROM orcamento_acao WHERE arquivo=? LIMIT 1", (lote,)).fetchone()
            # classificacao v2 (funcionamento x programas): meses carregados com a classificacao antiga sao baixados de novo
            tem_min = ano < ANO_MIN_MINISTERIOS or con.execute("SELECT 1 FROM despesa_orgao WHERE arquivo=? AND bucket IN ('pessoal_ativo','custeio','programas') LIMIT 1", (lote,)).fetchone()
            if ano < recarregar_desde and tem_pres and tem_min:
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
