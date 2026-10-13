"""Presidencia da Republica: cartao corporativo (CPGF) e viagens, do Portal da Transparencia.

Atencao ao que isto e: NAO e o gasto pessoal do presidente. Sao despesas pagas com cartao
corporativo e viagens (diarias e passagens) de orgaos da Presidencia da Republica, atribuidas
ao ocupante do cargo na data da despesa. Nomes de portadores e viajantes nao sao guardados.
"""
import io
import sys
import zipfile
from datetime import date, datetime

from . import common as c

BASE = "https://portaldatransparencia.gov.br/download-de-dados"
CARGO = "presidente"
ORGAO = "presidencia da republica"

# (chave, nome, partido, inicio, fim). Temer assume em 12/05/2016 (afastamento de Dilma).
PRESIDENTES = [
    ("dilma", "Dilma Rousseff", "PT", "2011-01-01", "2016-05-11"),
    ("temer", "Michel Temer", "MDB", "2016-05-12", "2018-12-31"),
    ("bolsonaro", "Jair Bolsonaro", "PL", "2019-01-01", "2022-12-31"),
    ("lula", "Luiz Inacio Lula da Silva", "PT", "2023-01-01", "9999-12-31"),
]
NOMES_BONITOS = {"Luiz Inacio Lula da Silva": "Luiz Inácio Lula da Silva"}


def garantir_presidentes(con):
    ids = []
    for chave, nome, partido, ini, fim in PRESIDENTES:
        nome = NOMES_BONITOS.get(nome, nome)
        pid = c.pessoa_por_fonte(con, "presidencia", chave) or c.criar_pessoa(con, "presidencia", chave, nome, CARGO)
        con.execute("""INSERT OR REPLACE INTO mandato (pessoa_id, cargo, legislatura, uf, partido, data_inicio, data_fim)
                       VALUES (?,?,?,?,?,?,?)""", (pid, CARGO, 0, None, partido, ini, fim))
        ids.append((pid, ini, fim))
    con.commit()
    return ids


def ocupante(ids, data_iso):
    for pid, ini, fim in ids:
        if ini <= data_iso <= fim:
            return pid
    return None


def eh_presidencia(texto):
    return ORGAO in c.sem_acento(texto)


def _zip_csv(resp, *, deve_conter, nao_conter=()):
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    for n in z.namelist():
        ln = n.lower()
        if deve_conter in ln and not any(x in ln for x in nao_conter):
            return z.open(n).read(), n
    raise ValueError(f"nenhum arquivo com '{deve_conter}' no zip: {z.namelist()}")


class Bloqueado(Exception):
    pass


def ja_carregado(con, lote):
    return con.execute("SELECT 1 FROM gasto WHERE arquivo=? LIMIT 1", (lote,)).fetchone() is not None


def carregar_cpgf_mes(con, ids, ano, mes):
    lote = f"pres_cpgf:{ano}{mes:02d}"
    try:
        r = c.get(f"{BASE}/cpgf/{ano}{mes:02d}", timeout=300)
        bruto, nome = _zip_csv(r, deve_conter="cpgf")
    except Exception as e:
        print(f"  AVISO: CPGF {ano}-{mes:02d} indisponivel: {e}", file=sys.stderr)
        return None
    colunas, linhas, col = c.ler_csv(bruto)
    con.execute("DELETE FROM gasto WHERE arquivo=?", (lote,))
    saida, lidas, sem_dono = [], 0, 0
    for l in linhas:
        lidas += 1
        if not eh_presidencia(col(l, "NOME ÓRGÃO SUPERIOR", "NOME ORGAO SUPERIOR")):
            continue
        d = c.data_iso(col(l, "DATA TRANSAÇÃO", "DATA TRANSACAO")) or f"{ano}-{mes:02d}-01"
        pid = ocupante(ids, d)
        if int(d[:4]) < c.ANO_INICIAL:
            continue
        if pid is None:
            sem_dono += 1
            continue
        saida.append((pid, "pres_cpgf", int(d[:4]), int(d[5:7]), d,
                      col(l, "TRANSAÇÃO", "TRANSACAO") or "Cartão corporativo",
                      col(l, "NOME FAVORECIDO"), col(l, "CNPJ OU CPF FAVORECIDO"), None, None,
                      col(l, "NOME UNIDADE GESTORA"), c.numero(col(l, "VALOR TRANSAÇÃO", "VALOR TRANSACAO")), None, lote))
    con.executemany(
        """INSERT INTO gasto (pessoa_id, fonte, ano, mes, data, categoria, fornecedor, cnpj_cpf,
                              documento, descricao, unidade, valor, url, arquivo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", saida)
    con.commit()
    return len(saida), lidas, colunas


def carregar_viagens_ano(con, ids, ano):
    lote = f"pres_viagem:{ano}"
    try:
        r = c.get(f"{BASE}/viagens/{ano}", timeout=600)
        bruto, nome = _zip_csv(r, deve_conter="viagem", nao_conter=("passagem", "pagamento", "trecho"))
    except Exception as e:
        print(f"  AVISO: viagens {ano} indisponivel: {e}", file=sys.stderr)
        return None
    colunas, linhas, col = c.ler_csv(bruto)
    con.execute("DELETE FROM gasto WHERE arquivo=?", (lote,))
    saida, lidas = [], 0
    for l in linhas:
        lidas += 1
        if not eh_presidencia(col(l, "Nome do órgão superior", "Nome do orgao superior")):
            continue
        d = c.data_iso(col(l, "Período - Data de início", "Periodo - Data de inicio")) or f"{ano}-01-01"
        pid = ocupante(ids, d)
        if pid is None:
            continue
        cargo = col(l, "Descrição Função", "Descricao Funcao") or col(l, "Cargo") or "servidor"
        desc = f"{cargo.strip().title()} — {col(l, 'Destinos')} — {col(l, 'Motivo')}"[:260]
        unidade = col(l, "Nome órgão solicitante", "Nome orgao solicitante")
        doc = col(l, "Número da Proposta (PCDP)", "Numero da Proposta (PCDP)")
        for categoria, campo, sinal in (("Diárias", "Valor diárias", 1), ("Passagens", "Valor passagens", 1),
                                        ("Outros gastos de viagem", "Valor outros gastos", 1),
                                        ("Devolução de valores", "Valor devolução", -1)):
            v = c.numero(col(l, campo, campo.replace("á", "a").replace("ç", "c").replace("ã", "a"))) * sinal
            if v:
                saida.append((pid, "pres_viagem", int(d[:4]), int(d[5:7]), d, categoria, None, None, doc, desc, unidade, v, None, lote))
    con.executemany(
        """INSERT INTO gasto (pessoa_id, fonte, ano, mes, data, categoria, fornecedor, cnpj_cpf,
                              documento, descricao, unidade, valor, url, arquivo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", saida)
    con.commit()
    return len(saida), lidas, colunas


def rodar(con, anos, recarregar_desde=None):
    """Meses/anos ja carregados antes de `recarregar_desde` sao pulados (retomada e rotina mensal)."""
    ids = garantir_presidentes(con)
    hoje = date.today()
    recarregar_desde = recarregar_desde or hoje.year - 1
    falhas = 0
    for ano in anos:
        total = 0
        for mes in range(1, 13):
            if (ano, mes) > (hoje.year, hoje.month):
                break
            if ano < recarregar_desde and ja_carregado(con, f"pres_cpgf:{ano}{mes:02d}"):
                continue
            res = carregar_cpgf_mes(con, ids, ano, mes)
            if res:
                falhas = 0
                total += res[0]
                if ano == anos[0] and mes == 1:
                    print(f"  Colunas do CPGF: {res[2]}")
            else:
                falhas += 1
                if falhas >= 3:
                    print("\nPARADO: 3 downloads seguidos recusados pelo Portal (provavel bloqueio temporario).\n"
                          "Espere 1-2 horas e rode de novo o mesmo comando: o que ja foi baixado e pulado.", file=sys.stderr)
                    return
        c.log(con, "presidencia", "cpgf", ano, total)
        print(f"Presidencia: CPGF {ano}: {total} lancamentos da Presidencia")
        if ano < recarregar_desde and con.execute("SELECT 1 FROM gasto WHERE arquivo=? LIMIT 1", (f"pres_viagem:{ano}",)).fetchone():
            continue
        res = carregar_viagens_ano(con, ids, ano)
        if res:
            if ano == anos[0]:
                print(f"  Colunas de viagens: {res[2]}")
            c.log(con, "presidencia", "viagens", ano, res[0])
            print(f"Presidencia: viagens {ano}: {res[0]} lancamentos ({res[1]} viagens no total do pais)")
