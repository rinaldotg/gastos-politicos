"""Atuacao legislativa: projetos de autoria, quantos viraram norma e presenca em votacoes nominais.

Camara: arquivos abertos anuais (dadosabertos.camara.leg.br/arquivos): proposicoesAutores, proposicoes, votacoesVotos.
Senado: API de processos por autor (legis.senado.leg.br/dadosabertos/processo?codigoParlamentarAutor=).
Os leitores toleram variacoes de nome de coluna e registram as colunas encontradas no log.

Presenca = votacoes nominais em que votou / votacoes nominais ocorridas entre o primeiro e o ultimo voto dele no ano
(evita punir suplentes e quem assumiu ou saiu no meio do ano). Nao mede presenca em comissoes nem em sessoes sem votacao.
"""
import csv
import io
import re
import sys
import tempfile
from collections import defaultdict
from datetime import datetime

from . import common as c

ARQ = "https://dadosabertos.camara.leg.br/arquivos/{tipo}/csv/{tipo}-{ano}.csv"
SENADO = "https://legis.senado.leg.br/dadosabertos/processo"
TIPOS_PL = {"PL", "PLP", "PDL", "PLS", "PLV"}
ANO_MIN = 2015


def _norm(n):
    return re.sub(r"[^a-z0-9]", "", c.sem_acento(n))


def _mapa(campos):
    return {_norm(k): k for k in campos}


def _col(mapa, *opcoes):
    for o in opcoes:
        k = mapa.get(_norm(o))
        if k:
            return k
    return None


def _abrir(tipo, ano):
    """Baixa o CSV anual para arquivo temporario e devolve um leitor de dicts (latin-1 ou utf-8)."""
    r = c.get(ARQ.format(tipo=tipo, ano=ano), tentativas=2, timeout=300, stream=True)
    tmp = tempfile.TemporaryFile()
    for parte in r.iter_content(1 << 20):
        tmp.write(parte)
    tmp.seek(0)
    cab = tmp.read(4096)
    tmp.seek(0)
    enc = "utf-8-sig"
    try:
        cab.decode("utf-8")
    except UnicodeDecodeError:
        enc = "latin-1"
    txt = io.TextIOWrapper(tmp, encoding=enc, newline="")
    primeira = txt.readline()
    txt.seek(0)
    delim = ";" if primeira.count(";") >= primeira.count(",") else ","
    return csv.DictReader(txt, delimiter=delim)


def _ano_de(txt):
    m = re.search(r"(19|20)\d{2}", txt or "")
    return int(m.group(0)) if m else None


def camara_proposicoes(con, ano, ids):
    """ids: id da Camara -> pessoa_id. Devolve {pessoa_id: [proposicoes, pl, pec, normas]} das proposicoes apresentadas no ano."""
    aut = _abrir("proposicoesAutores", ano)
    m = _mapa(aut.fieldnames or [])
    print(f"  Colunas proposicoesAutores {ano}: {sorted(m.values())}")
    k_prop, k_dep = _col(m, "idProposicao"), _col(m, "idDeputadoAutor", "idAutor")
    k_ord, k_prn = _col(m, "ordemAssinatura"), _col(m, "proponente")
    if not (k_prop and k_dep):
        raise ValueError("colunas de autoria nao encontradas")
    autores = defaultdict(set)  # idProposicao -> {pessoa_id}
    for r in aut:
        pid = ids.get(str(r.get(k_dep) or "").strip().split(".")[0])
        if not pid:
            continue
        if k_prn and (r.get(k_prn) or "").strip() not in ("1", "True", "true", "Sim", "sim"):
            if not (k_ord and (r.get(k_ord) or "").strip() == "1"):
                continue
        elif not k_prn and k_ord and (r.get(k_ord) or "").strip() not in ("1", ""):
            continue
        autores[str(r[k_prop]).strip()].add(pid)
    prop = _abrir("proposicoes", ano)
    m = _mapa(prop.fieldnames or [])
    print(f"  Colunas proposicoes {ano}: {sorted(m.values())[:40]}")
    k_id, k_tipo = _col(m, "id", "idProposicao"), _col(m, "siglaTipo")
    k_sit = _col(m, "ultimoStatus_descricaoSituacao", "descricaoSituacao", "situacao")
    k_data = _col(m, "dataApresentacao")
    out = defaultdict(lambda: [0, 0, 0, 0])
    for r in prop:
        pids = autores.get(str(r.get(k_id) or "").strip())
        if not pids:
            continue
        tipo = (r.get(k_tipo) or "").strip().upper()
        if tipo not in TIPOS_PL and tipo != "PEC":
            continue
        norma = 1 if re.search(r"norma jur", c.sem_acento(r.get(k_sit) or "")) else 0
        for pid in pids:
            o = out[pid]
            o[0] += 1
            o[1] += 1 if tipo in TIPOS_PL else 0
            o[2] += 1 if tipo == "PEC" else 0
            o[3] += norma
    return out


def camara_votos(ano, ids):
    """Devolve {pessoa_id: [votos, votacoes_na_janela]}."""
    rd = _abrir("votacoesVotos", ano)
    m = _mapa(rd.fieldnames or [])
    print(f"  Colunas votacoesVotos {ano}: {sorted(m.values())}")
    k_v, k_d = _col(m, "idVotacao"), _col(m, "deputado_id", "idDeputado", "ideCadastro")
    k_t = _col(m, "dataHoraVoto", "dataRegistroVoto", "dataVoto", "data")
    if not (k_v and k_d):
        raise ValueError("colunas de votos nao encontradas")
    data_vot = {}
    por = defaultdict(lambda: [set(), "9999", ""])
    for r in rd:
        v = str(r[k_v]).strip()
        d = (r.get(k_t) or "")[:10] if k_t else ""
        if v not in data_vot or (d and d < data_vot[v]):
            data_vot[v] = d or data_vot.get(v, "")
        pid = ids.get(str(r.get(k_d) or "").strip().split(".")[0])
        if pid:
            a = por[pid]
            a[0].add(v)
            if d:
                a[1] = min(a[1], d); a[2] = max(a[2], d)
    datas = sorted(d for d in data_vot.values() if d)
    out = {}
    for pid, (vs, d0, d1) in por.items():
        janela = sum(1 for d in datas if d0 <= d <= d1) if d1 else len(data_vot)
        out[pid] = [len(vs), max(janela, len(vs))]
    return out


def _salvar(con, fonte, ano, props, votos):
    pids = set(props) | set(votos)
    con.execute("DELETE FROM atuacao WHERE fonte=? AND ano=?", (fonte, ano))
    for pid in pids:
        p = props.get(pid, [0, 0, 0, 0])
        v = votos.get(pid, [None, None])
        con.execute("INSERT INTO atuacao VALUES (?,?,?,?,?,?,?,?,?)", (pid, ano, fonte, p[0], p[1], p[2], p[3], v[0], v[1]))
    con.execute("INSERT OR REPLACE INTO atuacao_carga VALUES (?,?,?,?)", (fonte, ano, len(pids), c.agora()))
    con.commit()


def rodar_camara(con, ate):
    ids = {r[0]: r[1] for r in con.execute("SELECT id_externo, pessoa_id FROM pessoa_fonte WHERE fonte='camara'")}
    feitos = {r[0] for r in con.execute("SELECT ano FROM atuacao_carga WHERE fonte='camara'")}
    total = 0
    for ano in range(ANO_MIN, ate + 1):
        if ano in feitos and ano < ate - 1:
            continue
        try:
            props = camara_proposicoes(con, ano, ids)
        except Exception as e:
            print(f"  AVISO: proposicoes da Camara {ano}: {e}", file=sys.stderr)
            props = {}
        try:
            votos = camara_votos(ano, ids)
        except Exception as e:
            print(f"  AVISO: votacoes da Camara {ano}: {e}", file=sys.stderr)
            votos = {}
        if props or votos:
            _salvar(con, "camara", ano, props, votos)
            total += 1
            print(f"  Camara {ano}: {len(props)} deputados com proposicoes; {len(votos)} com votos")
    return total


def _lista(j):
    if isinstance(j, list):
        return j
    if isinstance(j, dict):
        for v in j.values():
            if isinstance(v, list):
                return v
    return []


def rodar_senado(con, ate):
    cods = con.execute("SELECT id_externo, pessoa_id FROM pessoa_fonte WHERE fonte='senado'").fetchall()
    por = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))  # pessoa -> ano -> [...]
    falhas = 0
    for i, (cod, pid) in enumerate(cods):
        try:
            j = c.get_paciente(SENADO, {"codigoParlamentarAutor": cod}, timeout=90, esperas=(20, 60)).json()
        except Exception as e:
            falhas += 1
            if falhas <= 3:
                print(f"  AVISO: Senado codigo {cod}: {e}", file=sys.stderr)
            if falhas >= 10 and not por:
                break
            continue
        if i == 0:
            it = _lista(j)
            print(f"  Campos do processo no Senado: {sorted(it[0].keys()) if it and isinstance(it[0], dict) else it[:1]}")
        for x in _lista(j):
            ident = (x.get("identificacao") or "").strip().upper()
            tipo = ident.split(" ")[0] if ident else ""
            ano = _ano_de(x.get("dataApresentacao"))
            if not ano or ano < ANO_MIN or (tipo not in TIPOS_PL and tipo != "PEC"):
                continue
            o = por[pid][ano]
            o[0] += 1
            o[1] += 1 if tipo in TIPOS_PL else 0
            o[2] += 1 if tipo == "PEC" else 0
            o[3] += 1 if (x.get("normaGerada") or "").strip() else 0
    anos = sorted({a for d in por.values() for a in d})
    for ano in anos:
        _salvar(con, "senado", ano, {pid: d[ano] for pid, d in por.items() if ano in d}, {})
    print(f"  Senado: {len(por)} senadores com proposicoes ({falhas} falhas)")
    return len(anos)


def rodar(con, ate=None):
    ate = ate or datetime.now().year
    n = rodar_camara(con, ate) + rodar_senado(con, ate)
    c.log(con, "atuacao", "proposicoes_votos", None, n)
    print(f"Atuacao legislativa: {n} cargas (Camara/Senado por ano)")
    return n
