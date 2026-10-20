"""Equipe dos gabinetes: nomes e cargos dos assessores de cada deputado (Camara) e senador (Senado).

Camara: arquivo aberto "funcionarios" (todos os funcionarios em atividade, com lotacao, cargo e data de nomeacao).
Senado: API administrativa de servidores ativos (a lotacao informa o gabinete do senador).
Sao listas do dia da coleta, sem historico. Nao guardamos remuneracao individual nem documentos pessoais.
Colunas escritas de memoria e toleradas por apelidos: o log imprime as reais e quantas lotacoes ficaram sem parlamentar.
"""
import json
import re
import sys
from collections import Counter, defaultdict

from . import common as c

CAMARA = ["https://dadosabertos.camara.leg.br/arquivos/funcionarios/csv/funcionarios.csv",
          "http://dadosabertos.camara.leg.br/arquivos/funcionarios/csv/funcionarios.csv"]
SENADO = ["https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/servidores/ativos/csv",
          "https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores?formato=csv",
          "https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores?formato=json"]
ALIAS = dict(
    nome=("nome", "servidor", "nome do funcionario", "nome do servidor", "nome_funcionario"),
    cargo=("cargo", "funcao", "cargo/funcao", "cargo ou funcao", "funcao ou cargo", "grupo funcional"),
    lotacao=("lotacao", "nome lotacao", "sigla lotacao", "unidade de lotacao", "lotacao atual", "orgao de lotacao", "unidade", "gabinete", "lotacao do servidor"),
    nomeacao=("data de nomeacao", "data nomeacao", "data_nomeacao", "nomeacao", "admissao", "data de admissao", "data de exercicio"),
)


def _chave(s):
    return re.sub(r"[^a-z0-9 ]+", " ", c.sem_acento(s or "").lower()).strip()


def _nome_norm(s):
    return " ".join(re.sub(r"[^A-Z ]+", " ", c.sem_acento(s or "").upper()).split())


def _ler(bruto):
    """CSV ou JSON -> lista de dicts com chaves normalizadas."""
    texto = c.decodificar(bruto).lstrip()
    if texto[:1] in "[{":
        j = json.loads(texto)
        if isinstance(j, dict):
            j = next((v for v in j.values() if isinstance(v, list)), [])
        return [{_chave(k): ("" if v is None else str(v)).strip() for k, v in d.items()} for d in j if isinstance(d, dict)]
    colunas, linhas, _ = c.ler_csv(bruto)
    return [{_chave(k): (v or "").strip() for k, v in l.items() if k} for l in linhas]


def _campo(l, nome):
    for a in ALIAS[nome]:
        if l.get(a):
            return l[a]
    return ""


def _baixar(urls):
    for u in urls:
        try:
            r = c.get(u, timeout=300, rapido=True)
            return _ler(r.content), u
        except Exception as e:
            print(f"  AVISO: {u}: {e}", file=sys.stderr)
    return [], None


def _indice(con, cargo):
    """nome normalizado -> pessoa_id. Homonimos: fica o que tem despesa registrada mais recente, se for um so; senao, de fora."""
    por_nome = defaultdict(set)
    for pid, nome in con.execute("SELECT id, nome FROM pessoa WHERE cargo=?", (cargo,)):
        por_nome[_nome_norm(nome)].add(pid)
    recente = dict(con.execute("SELECT pessoa_id, MAX(ano) FROM gasto GROUP BY pessoa_id").fetchall())
    indice = {}
    for k, ids in por_nome.items():
        if not k:
            continue
        if len(ids) == 1:
            indice[k] = next(iter(ids))
            continue
        pont = sorted(((recente.get(i) or 0, i) for i in ids), reverse=True)
        if pont[0][0] and pont[0][0] > pont[1][0]:
            indice[k] = pont[0][1]
    return indice


def _achar_parlamentar(resto, indice):
    resto = _nome_norm(resto)
    if resto in indice:
        return indice[resto]
    toks = set(resto.split())
    if len(toks) >= 2:
        for k, pid in indice.items():
            if set(k.split()) == toks:
                return pid
        # nome de urna dentro do nome da lotacao (ou o contrario), com ao menos dois nomes
        cands = [pid for k, pid in indice.items() if len(k.split()) >= 2 and (resto.startswith(k + " ") or k.startswith(resto + " ") or resto == k)]
        if len(cands) == 1:
            return cands[0]
    return None


PAD_CAMARA = re.compile(r"^GAB(?:INETE)?\s+(?:(?:DO|DA|DE)\s+)?(?:DEP(?:UTAD[OA])?\s+)?(?:EDP\s+)?(.+)$")
PAD_SENADO = re.compile(r"GAB(?:INETE)?\s+(?:(?:DO|DA)\s+)?(?:SEN(?:ADOR(?:A)?)?\s+)?(.+)$")


def _processar(con, linhas, cargo, padrao, fonte):
    indice = _indice(con, cargo)
    sem_par, saida, gabs = Counter(), [], set()
    for l in linhas:
        lot = _nome_norm(_campo(l, "lotacao"))
        if "GAB" not in lot:
            continue
        m = padrao.search(lot)
        if not m:
            continue
        resto = re.sub(r"^[A-Z0-9]{3,12}\s+(?=.*\bGABINETE\b)", "", m.group(1)).strip()
        pid = _achar_parlamentar(resto, indice)
        if pid is None:
            sem_par[lot] += 1
            continue
        nome = _campo(l, "nome")
        if not nome or _nome_norm(nome) == _nome_norm(resto):
            continue
        cargo_f = _campo(l, "cargo")
        saida.append((pid, nome.strip()[:120], cargo_f.strip()[:120], _campo(l, "lotacao")[:120], (c.data_iso(_campo(l, "nomeacao")) or _campo(l, "nomeacao"))[:10], fonte))
        gabs.add(pid)
    return saida, gabs, sem_par


def _gravar(con, saida, fonte):
    con.execute("DELETE FROM gabinete_pessoa WHERE fonte=?", (fonte,))
    con.executemany("INSERT INTO gabinete_pessoa (pessoa_id, nome, cargo, lotacao, nomeacao, fonte) VALUES (?,?,?,?,?,?)", saida)
    c.log(con, fonte, "gabinete", None, len(saida))
    con.commit()


def rodar(con):
    total = 0
    for rotulo, urls, cargo, padrao, fonte in (("Camara", CAMARA, "deputado_federal", PAD_CAMARA, "gab_camara"), ("Senado", SENADO, "senador", PAD_SENADO, "gab_senado")):
        linhas, url = _baixar(urls)
        if not linhas:
            print(f"  AVISO: lista de funcionarios do {rotulo} indisponivel; mantive a anterior", file=sys.stderr)
            continue
        print(f"  Colunas dos funcionarios do {rotulo}: {sorted(linhas[0].keys())} ({len(linhas)} linhas, {url})")
        saida, gabs, sem_par = _processar(con, linhas, cargo, padrao, fonte)
        if sem_par:
            print(f"  Lotacoes de gabinete sem parlamentar identificado ({len(sem_par)}): {sem_par.most_common(8)}", file=sys.stderr)
        if not saida:
            lots = Counter(_campo(l, "lotacao") for l in linhas).most_common(10)
            print(f"  AVISO: nenhum assessor identificado no {rotulo}; mantive a lista anterior. Lotacoes mais comuns: {lots}", file=sys.stderr)
            continue
        _gravar(con, saida, fonte)
        total += len(saida)
        print(f"Gabinete {rotulo}: {len(saida)} assessores em {len(gabs)} gabinetes")
    return total
