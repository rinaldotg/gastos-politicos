"""Dinheiro que passa pelos partidos politicos, a partir dos dados abertos do TSE (dadosabertos.tse.jus.br):
  - prestacao de contas de CAMPANHA (orgaos partidarios e candidatos): receitas (fundo eleitoral, fundo partidario, doacoes),
    despesas por categoria e quem recebeu;
  - prestacao de contas ANUAL dos partidos: receitas, despesas por categoria (inclui pessoal) e quem recebeu.
Pessoas fisicas que receberam pagamentos nao sao identificadas: entram so como valor agregado (mesma regra dos assessores).
Os arquivos do TSE sao grandes e os nomes de colunas variam entre eleicoes; a leitura e tolerante, imprime as colunas reais no
log e segue com o que reconhecer. Cada (ano, base) carregado fica registrado em partido_carga e nao e baixado de novo
(a prestacao anual dos ultimos anos e recarregada, pois recebe retificacoes)."""
import io
import re
import sys
import tempfile
import time
import zipfile
from collections import defaultdict
from datetime import date

from . import common as c
from .emendas import _achar, _fluxo_csv

CKAN = "https://dadosabertos.tse.jus.br/api/3/action/"
CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_{tipo}_{ano}.zip"
ANOS_CAMPANHA = (2024, 2022, 2020, 2018, 2016, 2014)
ANOS_ANUAL = tuple(range(date.today().year - 1, 2013, -1))
LIMITE_SEGUNDOS = 40 * 60
TOP_RECEBEDORES = 40
TOP_CANDIDATOS = 40

RENOMEADOS = {"PMDB": "MDB", "PPS": "CIDADANIA", "PTN": "PODE", "PSDC": "DC", "PRB": "REPUBLICANOS", "PR": "PL", "PTDOB": "AVANTE",
              "PEN": "PATRIOTA", "PATRI": "PATRIOTA", "SD": "SOLIDARIEDADE", "PCDOB": "PCDOB", "PTC": "AGIR", "PMN": "MOBILIZA"}


def sigla(txt):
    """Chave estavel do partido: maiusculas, sem acento, espacos ou pontuacao, com os renomeados trocados pelo nome atual."""
    k = re.sub(r"[^A-Z0-9]", "", c.sem_acento(txt or "").upper())
    return RENOMEADOS.get(k, k)


def _json(url, params=None):
    return c.get(url, params=params, tentativas=2, timeout=60).json()


def _recursos(consulta):
    """Recursos (url, nome) de datasets do TSE que combinam com a consulta. Imprime os datasets achados."""
    try:
        res = _json(CKAN + "package_search", {"q": consulta, "rows": 40})["result"]["results"]
    except Exception as e:
        print(f"  AVISO: busca no catalogo do TSE falhou ({consulta}): {e}", file=sys.stderr)
        return []
    print(f"  Catalogo TSE '{consulta}': {[r.get('name') for r in res][:12]}")
    out = []
    for pacote in res:
        for rec in pacote.get("resources", []):
            out.append(((rec.get("url") or ""), (rec.get("name") or "")))
    return out


def _urls(ano, campanha):
    achadas = []
    if campanha:
        for q in (f"prestacao de contas eleitorais {ano}", f"prestacao-de-contas-eleitorais-{ano}"):
            achadas += [u for u, n in _recursos(q) if u.lower().endswith(".zip") and str(ano) in u and "eleitorais" in u.lower()]
            if achadas:
                break
        achadas += [CDN.format(tipo=t, ano=ano) for t in ("candidatos", "orgaos_partidarios")]
    else:
        for q in ("prestacao de contas anual partidaria", "prestacao de contas partidarias", "contas anuais partidos"):
            achadas += [u for u, n in _recursos(q) if u.lower().endswith(".zip") and str(ano) in u and "eleitorais" not in u.lower()]
            if achadas:
                break
    vistos, out = set(), []
    for u in achadas:
        if u not in vistos:
            vistos.add(u)
            out.append(u)
    return out


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


def _membros(z, anual):
    """Escolhe os csv de cada (nivel, tipo): prefere o consolidado BRASIL; para despesas prefere as contratadas."""
    grupos = defaultdict(list)
    for n in z.namelist():
        ln = n.lower()
        if not ln.endswith(".csv") or "originario" in ln:
            continue
        tipo = "receita" if "receita" in ln else "despesa" if "despesa" in ln else None
        if tipo is None:
            continue
        nivel = "candidato" if "candidato" in ln else "orgao" if ("orgao" in ln or "partidari" in ln) and not anual else "anual" if anual else None
        if nivel:
            grupos[(nivel, tipo)].append(n)
    escolhidos = {}
    for chave, nomes in grupos.items():
        if chave[1] == "despesa":
            contrat = [n for n in nomes if "contratada" in n.lower()]
            nomes = contrat or nomes
        br = [n for n in nomes if n.lower().endswith("brasil.csv")]
        escolhidos[chave] = br or nomes
    return escolhidos


class Acum:
    def __init__(self):
        self.rec = defaultdict(lambda: [0.0, 0])
        self.des = defaultdict(lambda: [0.0, 0])
        self.rcb = defaultdict(lambda: [0.0, 0])
        self.cand = defaultdict(lambda: [0.0, 0.0])
        self.linhas = 0


def _processar(z, nomes, nivel, tipo, base, ano, ac):
    for nome in nomes:
        cab, leitor = _fluxo_csv(z, nome)
        print(f"  [{ano} {base} {tipo}] {nome}: colunas {cab}")
        i_sig = _achar(cab, ("sg", "partido"), ("sigla", "partido"), exato=["sg_partido"])
        if tipo == "receita":
            i_val = _achar(cab, ("vr", "receita"), ("valor", "receita"))
            i_cat = _achar(cab, ("fonte", "receita"), ("origem", "receita"), ("tipo", "receita"), ("especie", "receita"))
        else:
            i_val = _achar(cab, ("vr", "despesa"), ("valor", "despesa"))
            i_cat = _achar(cab, ("origem", "despesa"), ("tipo", "despesa"), ("natureza", "despesa"), ("especie", "despesa"))
        i_nom = _achar(cab, ("nm", "fornecedor"), ("nome", "fornecedor"), ("nm", "doador"), ("nome", "doador"))
        i_doc = _achar(cab, ("cnpj", "fornecedor"), ("cpf", "fornecedor"), ("cnpj", "doador"), ("cpf", "doador"))
        i_cnm = _achar(cab, ("nm", "candidato"), ("nome", "candidato"), exato=["nm_candidato"])
        i_car = _achar(cab, ("ds", "cargo"), ("cargo",))
        i_uf = _achar(cab, ("sg", "uf"), exato=["sg_uf"])
        i_cid = _achar(cab, ("sq", "candidato"), ("cpf", "candidato"))
        if i_sig is None or i_val is None:
            print(f"  AVISO: colunas de partido/valor nao reconhecidas em {nome}", file=sys.stderr)
            continue

        def cel(l, i):
            return l[i].strip() if i is not None and i < len(l) else ""
        n = 0
        for l in leitor:
            sg = sigla(cel(l, i_sig))
            if not sg or sg in ("SEMPARTIDO", "NA", "NAOINFORMADO"):
                continue
            v = c.numero(cel(l, i_val)) or 0.0
            cat = cel(l, i_cat) or "Sem categoria"
            n += 1
            if tipo == "receita":
                k = (ano, base, sg, cat)
                ac.rec[k][0] += v
                ac.rec[k][1] += 1
                if nivel == "candidato" and i_cnm is not None:
                    k2 = (ano, sg, cel(l, i_cid) or cel(l, i_cnm), cel(l, i_cnm), cel(l, i_car), cel(l, i_uf))
                    ac.cand[k2][1] += v
                    if "fundo especial" in c.sem_acento(cat).lower() or "fefc" in cat.lower():
                        ac.cand[k2][0] += v
            else:
                k = (ano, base, sg, cat)
                ac.des[k][0] += v
                ac.des[k][1] += 1
                doc = re.sub(r"\D", "", cel(l, i_doc))
                nm = cel(l, i_nom)
                if len(doc) == 14:
                    kk = (ano, base, sg, doc, nm.title()[:120] if nm else "", "PJ")
                else:
                    kk = (ano, base, sg, "", "Pessoas físicas (agregado, sem identificação)", "PF")
                ac.rcb[kk][0] += v
                ac.rcb[kk][1] += 1
        ac.linhas += n
        print(f"    {n} linhas lidas")


def _gravar(con, ano, bases, ac):
    for b in bases:
        for t in ("partido_receita", "partido_despesa", "partido_recebedor"):
            con.execute(f"DELETE FROM {t} WHERE ano=? AND base=?", (ano, b))
    if "campanha_candidato" in bases:
        con.execute("DELETE FROM partido_candidato WHERE ano=?", (ano,))
    con.executemany("INSERT INTO partido_receita VALUES (?,?,?,?,?,?)", [(*k, round(v[0], 2), v[1]) for k, v in ac.rec.items()])
    con.executemany("INSERT INTO partido_despesa VALUES (?,?,?,?,?,?)", [(*k, round(v[0], 2), v[1]) for k, v in ac.des.items()])
    por = defaultdict(list)
    for k, v in ac.rcb.items():
        por[k[:3]].append((*k, round(v[0], 2), v[1]))
    linhas = []
    for k, lst in por.items():
        pj = sorted((x for x in lst if x[5] == "PJ"), key=lambda x: -x[6])[:TOP_RECEBEDORES]
        linhas += pj + [x for x in lst if x[5] == "PF"]
    con.executemany("INSERT INTO partido_recebedor VALUES (?,?,?,?,?,?,?,?)", linhas)
    pc = defaultdict(list)
    for k, v in ac.cand.items():
        if v[0] > 0:
            pc[k[1]].append((k[0], k[1], k[3].title(), k[4].title(), k[5], round(v[0], 2), round(v[1], 2)))
    cl = []
    for lst in pc.values():
        cl += sorted(lst, key=lambda x: -x[5])[:TOP_CANDIDATOS]
    con.executemany("INSERT INTO partido_candidato VALUES (?,?,?,?,?,?,?)", cl)
    for b in bases:
        con.execute("INSERT OR REPLACE INTO partido_carga VALUES (?,?,?,?)", (ano, b, ac.linhas, c.agora()))
        c.log(con, "partidos", b, ano, ac.linhas)
    con.commit()


def _ja_carregado(con, ano, base):
    return con.execute("SELECT 1 FROM partido_carga WHERE ano=? AND base=? AND linhas>0", (ano, base)).fetchone() is not None


def rodar(con, recarregar=False):
    ini = time.time()
    hoje = date.today().year
    feitos = 0
    for ano in sorted(set(ANOS_CAMPANHA) | set(ANOS_ANUAL), reverse=True):
        for campanha in (True, False):
            if campanha and ano not in ANOS_CAMPANHA or not campanha and ano not in ANOS_ANUAL:
                continue
            bases = ("campanha_orgao", "campanha_candidato") if campanha else ("anual",)
            if not recarregar and all(_ja_carregado(con, ano, b) for b in bases) and (campanha or ano < hoje - 2):
                continue
            if time.time() - ini > LIMITE_SEGUNDOS:
                print("  AVISO: tempo do passo esgotado; o restante fica para a proxima atualizacao", file=sys.stderr)
                return feitos
            ac_por = {b: Acum() for b in bases}
            achou = False
            for url in _urls(ano, campanha):
                z = _baixar(url)
                if z is None:
                    continue
                print(f"  {ano} {'campanha' if campanha else 'anual'}: {url} -> {len(z.namelist())} arquivos")
                for (nivel, tipo), nomes in _membros(z, not campanha).items():
                    base = "anual" if not campanha else ("campanha_candidato" if nivel == "candidato" else "campanha_orgao")
                    _processar(z, nomes, nivel, tipo, base, ano, ac_por[base])
                    achou = True
            if not achou:
                print(f"  AVISO: nenhum arquivo do TSE para {ano} ({'campanha' if campanha else 'anual'})", file=sys.stderr)
                continue
            # junta os acumuladores da mesma carga para gravar de uma vez
            junto = Acum()
            for b, ac in ac_por.items():
                for nome in ("rec", "des", "rcb", "cand"):
                    getattr(junto, nome).update(getattr(ac, nome))
                junto.linhas += ac.linhas
            if junto.linhas == 0:
                print(f"  AVISO: {ano}: arquivos lidos mas sem linhas aproveitaveis", file=sys.stderr)
                continue
            _gravar(con, ano, bases, junto)
            feitos += 1
            print(f"  Partidos {ano} ({'campanha' if campanha else 'anual'}): {junto.linhas} linhas, {len({k[2] for k in junto.rec})} partidos")
    print(f"Partidos: {feitos} cargas novas")
    return feitos
