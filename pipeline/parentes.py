"""Empresas pagas com a cota em que consta como socio o proprio parlamentar ou um parente dele.

Fatos publicos, sem inferencia por sobrenome:
  - 'proprio': o nome civil do parlamentar (do registro de candidaturas do TSE) aparece como socio no cadastro de
    CNPJ da Receita. Se o TSE trouxer o CPF, o cruzamento usa nome + 6 digitos centrais do CPF (base 'cpf');
    sem CPF, so o nome completo (base 'nome').
  - parentes: relacoes de conjuge, pai, mae, filho(a) e irmao(a) declaradas no Wikidata (fonte publica e
    verificavel, com o item citado). O parente e procurado entre os socios pelo nome completo (base 'wikidata').
O parentesco nunca e deduzido por sobrenome. Precisa da etapa 'receita' ja rodada (usa rf_socio)."""
import json
import sys
import time
from collections import defaultdict

from . import common as c
from .doacoes import _baixar, _csvs, URL_CAND
from .receita import _dig, chave_socio

ANOS = (2022, 2018, 2014)
SPARQL = "https://query.wikidata.org/sparql"
CONSULTA = """SELECT ?p ?pLabel ?prop ?r ?rLabel WHERE {
  ?p wdt:P27 wd:Q155 ; wdt:P106 wd:Q82955 .
  VALUES ?prop { wdt:P26 wdt:P22 wdt:P25 wdt:P40 wdt:P3373 }
  ?p ?prop ?r .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "pt,en". }
}"""
# propriedade -> (rotulo de r visto por p, rotulo de p visto por r)
REL = {"P26": ("cônjuge", "cônjuge"), "P22": ("pai", "filho(a)"), "P25": ("mãe", "filho(a)"),
       "P40": ("filho(a)", "pai/mãe"), "P3373": ("irmão(ã)", "irmão(ã)")}
MAX_CHAVES_NOME = 3   # nome que bate com mais socios distintos que isso e comum demais: descarta


def _candidatos(ano):
    """Registro de candidaturas a deputado federal e senador: lista de dicts civil/urna/uf/cpf (sem acento)."""
    z = _baixar(URL_CAND.format(ano=ano))
    out = []
    if z is None:
        return out
    for n in _csvs(z, False):
        cab, leitor, col = c.ler_csv(z.read(n))
        for l in leitor:
            cargo = c.sem_acento(col(l, "DS_CARGO"))
            if "deputado federal" not in cargo and "senador" not in cargo:
                continue
            cpf = _dig(col(l, "NR_CPF_CANDIDATO"))
            out.append(dict(civil=c.sem_acento(col(l, "NM_CANDIDATO")), urna=c.sem_acento(col(l, "NM_URNA_CANDIDATO")),
                            uf=col(l, "SG_UF").upper(), cpf=cpf if len(cpf) == 11 and len(set(cpf)) > 2 else ""))
    return out


def _wikidata():
    """Lista de (qid_p, nome_p, prop, qid_r, nome_r). Falha de rede nao derruba a etapa."""
    for t in range(3):
        try:
            r = c.get(SPARQL, params={"query": CONSULTA, "format": "json"}, tentativas=1, timeout=170)
            linhas = r.json()["results"]["bindings"]
            out = []
            for b in linhas:
                p, rr = b["p"]["value"].rsplit("/", 1)[-1], b["r"]["value"].rsplit("/", 1)[-1]
                out.append((p, b["pLabel"]["value"], b["prop"]["value"].rsplit("/", 1)[-1], rr, b["rLabel"]["value"]))
            return out
        except Exception as e:
            print(f"  (Wikidata tentativa {t + 1}/3 falhou: {str(e)[:100]})", file=sys.stderr)
            time.sleep(20 * (t + 1))
    return None


def _pessoas(con):
    """(nome sem acento, uf) -> {pessoa_id}; id -> nome."""
    idx, nomes = defaultdict(set), {}
    for pid, nome, uf in con.execute(
            """SELECT p.id, p.nome, (SELECT uf FROM mandato m WHERE m.pessoa_id=p.id AND uf IS NOT NULL ORDER BY legislatura DESC LIMIT 1)
               FROM pessoa p WHERE p.cargo IN ('deputado_federal','senador')"""):
        nomes[pid] = nome
        if uf:
            idx[(c.sem_acento(nome), uf.upper())].add(pid)
    return idx, nomes


def _nomes_civis(idx, anos):
    """pessoa_id -> {nome civil: cpf6 ou ''} pelo registro de candidaturas (liga por nome de urna/civil + UF, so se unico)."""
    civis = defaultdict(dict)
    for ano in anos:
        for k in _candidatos(ano):
            ids = idx.get((k["urna"], k["uf"]), set()) | idx.get((k["civil"], k["uf"]), set())
            if len(ids) == 1 and k["civil"]:
                pid = next(iter(ids))
                civis[pid][k["civil"]] = k["cpf"][3:9] if k["cpf"] else civis[pid].get(k["civil"], "")
    return civis


def _indice_socios(con):
    """nome sem acento -> [(cnpj8, nome, qualificacao, entrada, chave)] so de socios pessoa fisica ligaveis."""
    ix = defaultdict(list)
    for b8, nome, qual, ent, chave in con.execute("SELECT cnpj8, nome, qualificacao, entrada, chave FROM rf_socio WHERE chave LIKE 'pf:%'"):
        ix[c.sem_acento(nome)].append((b8, nome, qual, ent, chave))
    return ix


def _pagos(con):
    """cnpj8 -> total; (pessoa_id, cnpj8) -> total pago pela pessoa."""
    tot, por = defaultdict(float), defaultdict(float)
    q = """SELECT pessoa_id, REPLACE(REPLACE(REPLACE(COALESCE(cnpj_cpf,''),'.',''),'/',''),'-','') d, SUM(valor)
           FROM gasto WHERE fonte NOT LIKE 'pres%' GROUP BY pessoa_id, d HAVING LENGTH(d)=14"""
    for pid, d, v in con.execute(q):
        tot[d[:8]] += v
        por[(pid, d[:8])] += v
    return tot, por


def achar(con, anos=ANOS, civis=None, wiki="auto"):
    idx, nomes = _pessoas(con)
    if civis is None:
        civis = _nomes_civis(idx, anos)
    ix = _indice_socios(con)
    tot, por = _pagos(con)
    achados = {}   # (pid, relacao, parente, cnpj8, chave) -> linha

    def juntar(pid, relacao, parente, qid, base, socios, exige_cpf6=None):
        chaves = {s[4] for s in socios}
        if len(chaves) > MAX_CHAVES_NOME:
            return
        for b8, nome, qual, ent, chave in socios:
            if exige_cpf6 and not chave.startswith(f"pf:{exige_cpf6}:"):
                continue
            achados[(pid, relacao, parente, b8, chave)] = (pid, relacao, parente, qid, b8, nome, qual, ent, base,
                                                           round(por.get((pid, b8), 0), 2), round(tot.get(b8, 0), 2))
    # A) o proprio parlamentar como socio
    for pid, d in civis.items():
        for civil, cpf6 in d.items():
            if len(civil.split()) < 3 and not cpf6:
                continue
            socios = ix.get(civil, [])
            if cpf6:
                juntar(pid, "próprio", nomes[pid], "", "cpf", socios, exige_cpf6=cpf6)
            else:
                juntar(pid, "próprio", nomes[pid], "", "nome", socios)
    # B) parentes declarados no Wikidata
    linhas = _wikidata() if wiki == "auto" else wiki
    if linhas is None:
        print("  AVISO: Wikidata indisponivel; so a busca pelo proprio parlamentar foi feita", file=sys.stderr)
        linhas = []
    por_nome = defaultdict(set)
    for pid, d in civis.items():
        for civil in d:
            por_nome[civil].add(pid)
    for (_n, uf), ids in idx.items():
        for pid in ids:
            por_nome[_n].add(pid)
    qids_por_nome = defaultdict(set)
    for qp, nome_p, _prop, qr, nome_r in linhas:
        qids_por_nome[c.sem_acento(nome_p)].add(qp)

    def pessoa_de(qid, nome):
        k = c.sem_acento(nome)
        if len(k.split()) < 2 or len(qids_por_nome.get(k, {qid})) > 1:
            return None
        ids = por_nome.get(k, set())
        return next(iter(ids)) if len(ids) == 1 else None
    vistos = set()
    for qp, nome_p, prop, qr, nome_r in linhas:
        if prop not in REL or nome_r[:1] == "Q" or nome_p[:1] == "Q":   # sem rotulo em portugues/ingles
            continue
        for (q_pol, n_pol, q_par, n_par, rotulo) in ((qp, nome_p, qr, nome_r, REL[prop][0]), (qr, nome_r, qp, nome_p, REL[prop][1])):
            pid = pessoa_de(q_pol, n_pol)
            k_par = c.sem_acento(n_par)
            if pid is None or len(k_par.split()) < 2 or (pid, q_par, rotulo) in vistos or k_par == c.sem_acento(nomes[pid]):
                continue
            vistos.add((pid, q_par, rotulo))
            juntar(pid, rotulo, n_par, q_par, "wikidata", ix.get(k_par, []))
    return list(achados.values())


def rodar(con, anos=ANOS):
    if not con.execute("SELECT 1 FROM rf_socio LIMIT 1").fetchone():
        print("  AVISO: sem cadastro da Receita no banco (rode a etapa 'receita' antes)", file=sys.stderr)
        return 0
    linhas = achar(con, anos)
    con.execute("DELETE FROM parentesco_socio")
    con.executemany("INSERT INTO parentesco_socio VALUES (?,?,?,?,?,?,?,?,?,?,?)", linhas)
    c.log(con, "parentes", "parentesco_socio", None, len(linhas))
    con.commit()
    por_base = defaultdict(int)
    for l in linhas:
        por_base[l[8]] += 1
    print(f"Parentesco x socios: {len(linhas)} registros {dict(por_base)}")
    return len(linhas)
