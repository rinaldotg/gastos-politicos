"""Doacoes de campanha a deputados federais e senadores feitas por empresas e socios das empresas pagas com a cota.

Fonte: prestacao de contas dos candidatos (TSE) das eleicoes de 2014, 2018 e 2022. Procura nas receitas:
  - doador pessoa juridica cujo CNPJ (8 primeiros digitos) e de uma empresa do cadastro da Receita (etapa 'receita');
  - doador pessoa fisica que e socio de uma dessas empresas (ligado por nome + digitos centrais do CPF, como na Receita).
Liga o candidato ao parlamentar do site por nome (urna ou civil) + UF, so quando unico. Doar a campanha e legal e publico:
o site so informa o fato. Precisa da etapa 'receita' ja rodada (usa rf_empresa e rf_socio)."""
import io
import sys
import tempfile
import zipfile
from collections import defaultdict

from . import common as c
from .receita import _dig, chave_socio

ANOS = (2022, 2018, 2014)
URLS_PRESTACAO = {
    2022: ["https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2022.zip"],
    2018: ["https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_2018.zip"],
    2014: ["https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_final_2014.zip",
           "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_contas_2014.zip"],
}
URL_CAND = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip"


def _baixar(url):
    try:
        r = c.get(url, tentativas=2, timeout=900, stream=True)
    except Exception as e:
        print(f"  (sem arquivo em {url}: {str(e)[:80]})")
        return None
    tmp = tempfile.TemporaryFile()
    for parte in r.iter_content(1 << 20):
        tmp.write(parte)
    tmp.seek(0)
    try:
        return zipfile.ZipFile(tmp)
    except zipfile.BadZipFile:
        return None


def _csvs(z, receitas):
    nomes = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))]
    if receitas:
        nomes = [n for n in nomes if "receita" in n.lower() and "originario" not in n.lower() and "candidato" in n.lower()]
    brasil = [n for n in nomes if "brasil" in n.lower()]
    return brasil or nomes


def _chaves_doadores(con):
    """Quem procurar: CNPJ basico das empresas e chaves dos socios (pessoa fisica) do cadastro da Receita."""
    emp = {r[0]: r[1] for r in con.execute("SELECT cnpj8, razao FROM rf_empresa")}
    soc = defaultdict(str)
    for chave, nome in con.execute("SELECT DISTINCT chave, nome FROM rf_socio WHERE chave LIKE 'pf:%'"):
        soc[chave] = nome
    return emp, soc


def _parlamentares(con):
    pess = defaultdict(set)
    for pid, nome, uf in con.execute(
            """SELECT p.id, p.nome, (SELECT uf FROM mandato m WHERE m.pessoa_id=p.id AND uf IS NOT NULL ORDER BY legislatura DESC LIMIT 1)
               FROM pessoa p WHERE p.cargo IN ('deputado_federal','senador')"""):
        if uf:
            pess[(c.sem_acento(nome), uf.upper())].add(pid)
    return pess


def _nomes_candidatos(ano):
    """(nome civil, uf) -> nomes de urna, pelo registro de candidaturas do mesmo ano (ajuda a achar o parlamentar)."""
    z = _baixar(URL_CAND.format(ano=ano))
    out = defaultdict(set)
    if z is None:
        return out
    for n in _csvs(z, False):
        cab, leitor, col = c.ler_csv(z.read(n))
        for l in leitor:
            civil, urna, uf = c.sem_acento(col(l, "NM_CANDIDATO")), c.sem_acento(col(l, "NM_URNA_CANDIDATO")), col(l, "SG_UF").upper()
            if civil and uf:
                out[(civil, uf)].add(urna)
    return out


def _ler_receitas(z, ano, emp, soc, pess, urnas):
    achados = defaultdict(float)   # (tipo, chave, doador, pid) -> valor
    cont = defaultdict(int)
    mostrar = True
    for n in _csvs(z, True):
        cab, leitor, col = c.ler_csv(z.read(n))
        if mostrar:
            print(f"  Colunas receitas {ano}: {cab[:45]}")
            mostrar = False
        for l in leitor:
            cargo = c.sem_acento(col(l, "DS_CARGO", "Cargo"))
            if "deputado federal" not in cargo and "senador" not in cargo:
                continue
            doc = _dig(col(l, "NR_CPF_CNPJ_DOADOR", "CPF/CNPJ do doador"))
            nome = col(l, "NM_DOADOR_RFB", "Nome do doador (Receita Federal)", "NM_DOADOR", "Nome do doador")
            tipo = chave = None
            if len(doc) == 14 and doc[:8] in emp:
                tipo, chave = "empresa", doc[:8]
            elif len(doc) == 11:
                for nm in (col(l, "NM_DOADOR_RFB", "Nome do doador (Receita Federal)"), col(l, "NM_DOADOR", "Nome do doador")):
                    k = chave_socio("2", nm, doc[3:9])
                    if k in soc:
                        tipo, chave = "socio", k
                        break
            if not tipo:
                continue
            uf = col(l, "SG_UF", "UF").upper()
            civil = c.sem_acento(col(l, "NM_CANDIDATO", "Nome candidato"))
            cand_nomes = {civil} | urnas.get((civil, uf), set())
            ids = set()
            for nm in cand_nomes:
                ids |= pess.get((nm, uf), set())
            if len(ids) != 1:
                continue
            pid = next(iter(ids))
            valor = c.numero(col(l, "VR_RECEITA", "Valor receita")) or 0.0
            achados[(tipo, chave, nome or (emp.get(chave) if tipo == "empresa" else soc.get(chave)) or "", pid, col(l, "SG_PARTIDO", "Sigla  Partido", "Sigla Partido"))] += valor
            cont[(tipo, chave, pid)] += 1
    return achados, cont


def rodar(con, anos=ANOS):
    emp, soc = _chaves_doadores(con)
    if not emp:
        print("  AVISO: sem cadastro da Receita no banco (rode a etapa 'receita' antes)", file=sys.stderr)
        return 0
    pess = _parlamentares(con)
    linhas = []
    for ano in anos:
        z = None
        for u in URLS_PRESTACAO.get(ano, []):
            z = _baixar(u)
            if z is not None:
                break
        if z is None:
            print(f"  AVISO: prestacao de contas {ano} indisponivel", file=sys.stderr)
            continue
        urnas = _nomes_candidatos(ano)
        achados, cont = _ler_receitas(z, ano, emp, soc, pess, urnas)
        for (tipo, chave, nome, pid, partido), v in achados.items():
            linhas.append((ano, tipo, chave, nome, pid, partido, round(v, 2), cont[(tipo, chave, pid)]))
        print(f"  Doacoes {ano}: {len(achados)} combinacoes doador x parlamentar")
    con.execute("DELETE FROM doacao_campanha")
    con.executemany("INSERT INTO doacao_campanha VALUES (?,?,?,?,?,?,?,?)", linhas)
    c.log(con, "tse_doacoes", "doacao_campanha", None, len(linhas))
    con.commit()
    print(f"Doacoes de campanha: {len(linhas)} registros")
    return len(linhas)
