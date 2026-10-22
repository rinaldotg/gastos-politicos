"""Candidaturas das eleicoes gerais (registro no TSE) ligadas aos parlamentares ja cadastrados.

Fonte: consulta_cand_{ano}.zip dos dados abertos do TSE (um CSV por UF e um BRASIL). Liga por nome (de urna ou civil) + UF,
so quando a ligacao e unica nos dois lados; homonimos ficam de fora. Nao guarda CPF.
Colunas esperadas (o log imprime as reais): DS_CARGO, SG_UF, SG_PARTIDO, NM_CANDIDATO, NM_URNA_CANDIDATO, NR_CANDIDATO,
DS_SITUACAO_CANDIDATURA, DS_DETALHE_SITUACAO_CAND.
"""
import io
import sys
import tempfile
import zipfile
from collections import defaultdict

from . import common as c

ANO = 2026
URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip"
ORDEM_SITUACAO = ("deferido", "aguardando", "deferido com recurso", "indeferido", "renuncia", "cancelado")


def _baixar(url):
    try:
        r = c.get(url, tentativas=2, timeout=600, stream=True)
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
        print(f"  AVISO: {url} nao e um zip valido", file=sys.stderr)
        return None


def _linhas(z):
    nomes = [n for n in z.namelist() if n.lower().endswith(".csv")]
    brasil = [n for n in nomes if "brasil" in n.lower()]
    for n in (brasil or nomes):
        cab, leitor, col = c.ler_csv(z.read(n))
        yield cab, leitor, col


def _rank(situacao):
    s = c.sem_acento(situacao)
    for i, k in enumerate(ORDEM_SITUACAO):
        if s.startswith(k):
            return i
    return len(ORDEM_SITUACAO)


def _candidatos(z):
    cands = defaultdict(list)  # (nome, uf) -> registros
    mostrar = True
    for cab, leitor, col in _linhas(z):
        if mostrar:
            print("  Colunas candidaturas:", cab[:40])
            mostrar = False
        for l in leitor:
            cargo = col(l, "DS_CARGO")
            uf = col(l, "SG_UF").upper()
            if not cargo:
                continue
            reg = dict(cargo=cargo.title(), uf=uf, partido=col(l, "SG_PARTIDO"), numero=col(l, "NR_CANDIDATO"),
                       situacao=col(l, "DS_DETALHE_SITUACAO_CAND") or col(l, "DS_SITUACAO_CANDIDATURA"),
                       urna=col(l, "NM_URNA_CANDIDATO"))
            for n in {c.sem_acento(col(l, "NM_URNA_CANDIDATO")), c.sem_acento(col(l, "NM_CANDIDATO"))}:
                if n:
                    cands[(n, uf)].append(reg)
    return cands


def rodar(con, ano=ANO):
    z = _baixar(URL.format(ano=ano))
    if z is None:
        print(f"  AVISO: candidaturas {ano} indisponiveis (ainda nao publicadas?)", file=sys.stderr)
        return 0
    cands = _candidatos(z)
    pess = defaultdict(set)  # (nome, uf) -> pessoa_ids
    for pid, nome, uf in con.execute(
            """SELECT p.id, p.nome, (SELECT uf FROM mandato m WHERE m.pessoa_id=p.id AND uf IS NOT NULL ORDER BY legislatura DESC LIMIT 1)
               FROM pessoa p WHERE p.cargo IN ('deputado_federal','senador')"""):
        if uf:
            pess[(c.sem_acento(nome), uf.upper())].add(pid)
    linhas, amb = [], 0
    for k, ids in pess.items():
        regs = cands.get(k)
        if not regs:
            continue
        if len(ids) != 1:  # dois parlamentares com o mesmo nome e UF
            amb += 1
            continue
        pid = next(iter(ids))
        por_cargo = defaultdict(list)
        for r in regs:
            por_cargo[r["cargo"]].append(r)
        for cargo, rs in por_cargo.items():
            if len({r["numero"] for r in rs}) > 1:  # homonimos no TSE: mesmo nome, UF e cargo com numeros diferentes
                amb += 1
                continue
            r = min(rs, key=lambda x: _rank(x["situacao"]))
            linhas.append((pid, ano, cargo, r["partido"], r["numero"], r["urna"], r["situacao"]))
    con.execute("DELETE FROM candidatura WHERE ano=?", (ano,))
    con.executemany("INSERT INTO candidatura (pessoa_id, ano, cargo, partido, numero, nome_urna, situacao) VALUES (?,?,?,?,?,?,?)", linhas)
    c.log(con, "tse_cand", "candidaturas", ano, len(linhas))
    con.commit()
    print(f"Candidaturas {ano}: {len(linhas)} parlamentares com registro ({amb} ambiguos ignorados)")
    return len(linhas)
