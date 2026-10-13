"""Camara dos Deputados: deputados (API) e cota parlamentar CEAP (CSV anual oficial)."""
import io
import sys
import zipfile
from datetime import datetime

from . import common as c

API = "https://dadosabertos.camara.leg.br/api/v2"
COTAS_ZIP = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
LEGISLATURAS = [54, 55, 56, 57]
CARGO = "deputado_federal"


def bonito(t):
    t = (t or "").strip().rstrip(".")
    return t[:1].upper() + t[1:].lower() if t.isupper() else t


def garantir_mandato(con, pid, leg, uf, partido):
    con.execute("""INSERT OR IGNORE INTO mandato (pessoa_id, cargo, legislatura, uf, partido)
                   VALUES (?,?,?,?,?)""", (pid, CARGO, leg, uf, partido))


def carregar_deputados(con):
    total = 0
    for leg in LEGISLATURAS:
        pagina = 1
        while True:
            dados = c.get(f"{API}/deputados", {"idLegislatura": leg, "itens": 100, "pagina": pagina,
                                               "ordem": "ASC", "ordenarPor": "nome"},
                          ).json().get("dados", [])
            if not dados:
                break
            for d in dados:
                pid = c.pessoa_por_fonte(con, "camara", d["id"]) or \
                    c.criar_pessoa(con, "camara", d["id"], d["nome"], CARGO)
                garantir_mandato(con, pid, leg, d.get("siglaUf"), d.get("siglaPartido"))
                total += 1
            pagina += 1
        con.commit()
        print(f"  Camara, legislatura {leg}: ok")
    c.log(con, "camara", "deputados", None, total)
    print(f"Deputados: {total} mandatos")


def carregar_cota(con, ano):
    print(f"Camara: cota {ano}...")
    try:
        r = c.get(COTAS_ZIP.format(ano=ano), timeout=300)
    except Exception as e:  # ano ainda sem arquivo, ou fora do ar
        print(f"  AVISO: nao consegui baixar {ano}: {e}", file=sys.stderr)
        return False
    z = zipfile.ZipFile(io.BytesIO(r.content))
    colunas, linhas, col = c.ler_csv(z.open(z.namelist()[0]).read())
    lote = f"camara_ceap:{ano}"
    con.execute("DELETE FROM gasto WHERE arquivo=?", (lote,))
    ins = criados = lidas = sem_id = 0
    lote_linhas = []
    for l in linhas:
        lidas += 1
        id_dep = col(l, "ideCadastro") or col(l, "nuDeputadoId")
        if not id_dep:
            sem_id += 1
            continue
        pid = c.pessoa_por_fonte(con, "camara", id_dep)
        try:
            mes = int(col(l, "numMes") or 0)
            ano_l = int(col(l, "numAno") or ano)
        except ValueError:
            continue
        if pid is None:  # deputado fora das listas da API (ex.: suplente antigo): cria a partir da propria linha
            pid = c.criar_pessoa(con, "camara", id_dep, bonito(col(l, "txNomeParlamentar")) or f"Deputado {id_dep}", CARGO)
            criados += 1
        leg = int(col(l, "nuLegislatura") or c.legislatura_de(ano_l, mes))
        garantir_mandato(con, pid, leg, col(l, "sgUF") or None, col(l, "sgPartido") or None)
        lote_linhas.append((pid, "camara_ceap", ano_l, mes, col(l, "datEmissao")[:10],
                            bonito(col(l, "txtDescricao")) or "(sem tipo)", col(l, "txtFornecedor"),
                            col(l, "txtCNPJCPF"), col(l, "txtNumero"), None, None,
                            c.numero(col(l, "vlrLiquido")), col(l, "urlDocumento") or None, lote))
    con.executemany(
        """INSERT INTO gasto (pessoa_id, fonte, ano, mes, data, categoria, fornecedor, cnpj_cpf,
                              documento, descricao, unidade, valor, url, arquivo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        lote_linhas)
    ins = len(lote_linhas)
    c.log(con, "camara", "ceap", ano, ins)
    print(f"  {ano}: {ins} despesas ({lidas} linhas; {criados} deputados criados a partir da cota; {sem_id} sem id)")
    return True


def rodar(con, anos, so_gastos=False):
    if not so_gastos:
        carregar_deputados(con)
    for ano in anos:
        carregar_cota(con, ano)
