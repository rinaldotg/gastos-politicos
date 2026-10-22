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
from itertools import chain, islice
import time
import zipfile
from collections import defaultdict
from datetime import date

from . import common as c
from .emendas import _achar, _fluxo_csv

CKAN = "https://dadosabertos.tse.jus.br/api/3/action/"
CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele/prestacao_contas/prestacao_de_contas_eleitorais_{tipo}_{ano}.zip"
ANOS_CAMPANHA = (2024, 2022, 2020, 2018)  # antes de 2018 o TSE usa outro formato e outro endereco
ANOS_ANUAL = tuple(range(date.today().year - 1, 2016, -1))
VERSAO = 2  # sobe quando a leitura muda: forca recarregar o que foi lido pela versao anterior
LIMITE_SEGUNDOS = 40 * 60
LIMIAR_RECEBEDOR_CAMPANHA = 5000  # campanha dos candidatos tem milhoes de linhas: guardamos recebedores com este total ou mais
MAX_RECEBEDORES_CAMPANHA = 5000   # por partido e eleicao
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
            achadas += [u for u, n in _recursos(q) if u.lower().endswith(".zip") and str(ano) in u and "eleitorais" not in u.lower()
                        and ("prestacao_contas_anual_partidaria_" + str(ano) in u.lower() or "fefc_fp" in u.lower())]
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
        if not ln.endswith(".csv") or "originario" in ln or "_nf_" in ln or "notafiscal" in ln or "extrato" in ln:
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


PREF_CAT = {"receita": ("ds_tp_fonte_recurso", "ds_fonte_receita", "ds_origem_receita", "ds_tp_origem_doacao", "ds_natureza_receita", "ds_especie_receita"),
            "despesa": ("tp_despesa", "ds_origem_despesa", "ds_tp_despesa", "ds_natureza_despesa", "ds_gasto")}
RE_FUNDO = re.compile(r"fundo partidario|fundo especial|fefc")


def _col_exata(cab, nomes):
    norm = [_norm_h(h) for h in cab]
    for n in nomes:
        if n in norm:
            return norm.index(n)
    return None


def _col_esfera(cab):
    for i, h in enumerate(cab):
        n = _norm_h(h)
        if n.startswith("ds_") and ("esfera" in n or "espera" in n) and "doador" not in n and "fornecedor" not in n:
            return i
    return None


PRIORIDADE_CAT = {"receita": ("fonte", "origem", "natureza", "especie", "tipo"),
                  "despesa": ("tp_despesa", "tipo", "gasto", "origem", "natureza", "especie", "fonte")}
EXCLUIR_CAT = ("fornecedor", "esfera", "documento", "municipio", "partidaria", "doador", "cargo", "candidato", "uf", "zona", "eleicao", "turno")


def _cat_adaptativa(cab, amostra, tipo):
    """Quando nenhum nome conhecido serve, escolhe entre as colunas descritivas (ds_/tp_) a que tem poucos valores distintos
    (uma categoria de verdade, e nao um texto livre) olhando as primeiras linhas."""
    cands = []
    for i, h in enumerate(cab):
        n = _norm_h(h)
        if n.startswith(("ds_", "tp_")) and not any(x in n for x in EXCLUIR_CAT):
            distintos = len({l[i].strip() for l in amostra if i < len(l) and l[i].strip()})
            if 1 <= distintos <= 300:
                prio = next((k for k, chave in enumerate(PRIORIDADE_CAT[tipo]) if chave in n), len(PRIORIDADE_CAT[tipo]))
                cands.append((prio, distintos, i))
    return min(cands)[2] if cands else None


def _norm_h(h):
    return re.sub(r"[^a-z0-9_]", "", c.sem_acento(h or "").lower().replace(" ", "_"))


class Acum:
    def __init__(self):
        self.rec = defaultdict(lambda: [0.0, 0])
        self.des = defaultdict(lambda: [0.0, 0])
        self.rcb = defaultdict(lambda: [0.0, 0])
        self.cand = defaultdict(lambda: [0.0, 0.0])
        self.linhas = 0
        self.rotulos = {}

    def canon(self, cat):
        """Une variacoes de caixa e acento ('FUNDO PARTIDARIO' = 'Fundo Partidário'), preferindo o rotulo que nao esta em maiusculas."""
        cat = (cat or "").strip()
        if not cat or cat.upper() in ("#NULO#", "#NULO", "#NE#"):
            return "Não informado"
        k = c.sem_acento(cat).lower()
        atual = self.rotulos.get(k)
        if atual is None or (atual.isupper() and not cat.isupper()):
            self.rotulos[k] = cat
        return k  # chave; o rotulo final e resolvido na gravacao

    def rotulo(self, k):
        return self.rotulos.get(k, k)


def _processar(z, nomes, nivel, tipo, base, ano, ac):
    for nome in nomes:
        cab, leitor = _fluxo_csv(z, nome)
        print(f"  [{ano} {base} {tipo}] {nome}: colunas {cab}")
        i_sig = _achar(cab, ("sg", "partido"), ("sigla", "partido"), exato=["sg_partido"])
        if tipo == "receita":
            i_val = _achar(cab, ("vr", "receita"), ("valor", "receita"))
            i_cat = _col_exata(cab, PREF_CAT["receita"])
            if i_cat is None:
                i_cat = _achar(cab, ("fonte", "receita"), ("origem", "receita"), ("tipo", "receita"), ("especie", "receita"))
        else:
            i_val = _achar(cab, ("vr", "despesa"), ("valor", "despesa"), ("vr", "gasto"), ("vr", "pagamento"))
            i_cat = _col_exata(cab, PREF_CAT["despesa"])
            if i_cat is None:
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
        amostra = list(islice(leitor, 20000))
        if i_cat is not None and _norm_h(cab[i_cat]).startswith(("cd_", "nr_", "sq_")):
            i_cat = None  # codigo, nao descricao
        if i_cat is None:
            i_cat = _cat_adaptativa(cab, amostra, tipo)
        i_esf = _col_esfera(cab) if nivel in ("orgao", "anual") else None
        i_fonte_d = _col_exata(cab, ("ds_fonte_despesa",)) if tipo == "despesa" and nivel == "anual" else None
        print(f"    categoria de {tipo}: {cab[i_cat] if i_cat is not None else 'nenhuma'}; valor: {cab[i_val]}; esfera: {cab[i_esf] if i_esf is not None else '-'}; fonte da despesa: {cab[i_fonte_d] if i_fonte_d is not None else '-'}")
        fundos_esf = defaultdict(lambda: [0.0, 0])
        leitor = chain(amostra, leitor)

        def cel(l, i):
            return l[i].strip() if i is not None and i < len(l) else ""
        n = 0
        for l in leitor:
            sg = sigla(cel(l, i_sig))
            if not sg or sg in ("SEMPARTIDO", "NA", "NAOINFORMADO"):
                continue
            v = c.numero(cel(l, i_val)) or 0.0
            cat = cel(l, i_cat) or "Sem categoria"
            if i_fonte_d is not None and cel(l, i_fonte_d):
                cat = f"{cat} ({cel(l, i_fonte_d)})"
            cat = ac.canon(cat)
            n += 1
            if tipo == "receita":
                k = (ano, base, sg, cat)
                if i_esf is not None and RE_FUNDO.search(cat):
                    # o fundo passa do diretorio nacional aos estaduais e municipais: contar so o nacional evita contar duas vezes
                    fe = fundos_esf[(k, c.sem_acento(cel(l, i_esf)).lower())]
                    fe[0] += v
                    fe[1] += 1
                else:
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
        if fundos_esf:
            tem_nac = any(e.startswith("nacional") for _, e in fundos_esf)
            for (k, e), (v, q) in fundos_esf.items():
                if not tem_nac or e.startswith("nacional"):
                    ac.rec[k][0] += v
                    ac.rec[k][1] += q
        ac.linhas += n
        print(f"    {n} linhas lidas")


MAX_CATEGORIAS = 80


def _limitar_categorias(d):
    """Linhas (ano, base, sigla, categoria, valor, n); passa de MAX_CATEGORIAS por partido, o resto vira 'Outras categorias'."""
    por = defaultdict(list)
    for k, v in d.items():
        por[k[:3]].append((k[3], v[0], v[1]))
    out = []
    for k, lst in por.items():
        lst.sort(key=lambda t: -abs(t[1]))
        for cat, val, n in lst[:MAX_CATEGORIAS]:
            out.append((*k, cat, round(val, 2), n))
        resto = lst[MAX_CATEGORIAS:]
        if resto:
            out.append((*k, f"Outras categorias ({len(resto)} tipos)", round(sum(t[1] for t in resto), 2), sum(t[2] for t in resto)))
    return out


def _resolver(ac, d):
    """Troca a chave de categoria (sem caixa nem acento) pelo rotulo legivel."""
    out = defaultdict(lambda: [0.0, 0])
    for k, v in d.items():
        kk = (*k[:3], ac.rotulo(k[3]))
        out[kk][0] += v[0]
        out[kk][1] += v[1]
    return out


def _gravar(con, ano, bases, ac):
    for b in bases:
        for t in ("partido_receita", "partido_despesa", "partido_recebedor"):
            con.execute(f"DELETE FROM {t} WHERE ano=? AND base=?", (ano, b))
    if "campanha_candidato" in bases:
        con.execute("DELETE FROM partido_candidato WHERE ano=?", (ano,))
    con.executemany("INSERT INTO partido_receita VALUES (?,?,?,?,?,?)", _limitar_categorias(_resolver(ac, ac.rec)))
    con.executemany("INSERT INTO partido_despesa VALUES (?,?,?,?,?,?)", _limitar_categorias(_resolver(ac, ac.des)))
    por = defaultdict(list)
    for k, v in ac.rcb.items():
        por[k[:3]].append((*k, round(v[0], 2), v[1]))
    linhas = []
    for k, lst in por.items():
        pj = sorted((x for x in lst if x[5] == "PJ"), key=lambda x: -x[6])
        if k[1] == "campanha_candidato":
            pj = [x for x in pj if x[6] >= LIMIAR_RECEBEDOR_CAMPANHA][:MAX_RECEBEDORES_CAMPANHA]
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
    for b in tuple(bases) + (f"v{VERSAO}",):
        con.execute("INSERT OR REPLACE INTO partido_carga VALUES (?,?,?,?)", (ano, b, ac.linhas, c.agora()))
        c.log(con, "partidos", b, ano, ac.linhas)
    con.commit()


def _fefc(z, ano, ac):
    """Zip de distribuicao do FEFC (fefc_fp): quanto cada partido recebeu do Fundo Especial de Financiamento de Campanha na eleicao
    e quanto repassou a candidaturas femininas e masculinas. Base 'fundos_tse'. (O arquivo do Fundo Partidario so traz a divisao por genero.)"""
    n_lin = 0
    for nome in z.namelist():
        if not nome.lower().endswith(".csv") or "fefc_genero" not in nome.lower():
            continue
        cab, leitor = _fluxo_csv(z, nome)
        ix = {k: _col_exata(cab, (k,)) for k in ("aa_eleicao", "sg_partido", "ds_genero", "qt_candidato", "vr_partido_fefc", "vr_total_recebido_fefc")}
        if any(ix[k] is None for k in ("sg_partido", "vr_partido_fefc")):
            print(f"  AVISO: colunas do FEFC nao reconhecidas em {nome}: {cab}", file=sys.stderr)
            continue
        def cel(l, k):
            i = ix.get(k)
            return l[i].strip() if i is not None and i < len(l) else ""
        total = {}
        for l in leitor:
            if cel(l, "aa_eleicao") and cel(l, "aa_eleicao") != str(ano):
                continue
            sg = sigla(cel(l, "sg_partido"))
            if not sg:
                continue
            n_lin += 1
            total[sg] = c.numero(cel(l, "vr_partido_fefc"))
            gen = c.sem_acento(cel(l, "ds_genero")).lower()
            rot = "feminina" if gen.startswith("fem") else "masculina" if gen.startswith("masc") else "sem genero informado"
            k = (ano, "fundos_tse", sg, ac.canon(f"Repassado do FEFC a candidaturas de gênero {rot}"))
            ac.des[k][0] += c.numero(cel(l, "vr_total_recebido_fefc"))
            ac.des[k][1] += int(c.numero(cel(l, "qt_candidato")))
        for sg, v in total.items():
            k = (ano, "fundos_tse", sg, ac.canon("Fundo Especial de Financiamento de Campanha (FEFC) recebido pelo partido"))
            ac.rec[k][0] += v
            ac.rec[k][1] += 1
        print(f"  [fefc_fp] {nome}: {len(total)} partidos, {n_lin} linhas")
    ac.linhas += n_lin


def _ja_carregado(con, ano, base):
    return (con.execute("SELECT 1 FROM partido_carga WHERE ano=? AND base=? AND linhas>0", (ano, base)).fetchone() is not None
            and con.execute("SELECT 1 FROM partido_carga WHERE ano=? AND base=?", (ano, f"v{VERSAO}")).fetchone() is not None)


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
            ac_por = {b: Acum() for b in bases + (() if campanha else ("fundos_tse",))}
            achou = False
            for url in _urls(ano, campanha):
                z = _baixar(url)
                if z is None:
                    continue
                print(f"  {ano} {'campanha' if campanha else 'anual'}: {url} -> {len(z.namelist())} arquivos")
                if "fefc_fp" in url.lower():
                    _fefc(z, ano, ac_por["fundos_tse"])
                    achou = True
                    continue
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
                junto.rotulos.update(ac.rotulos)
                junto.linhas += ac.linhas
            if junto.linhas == 0:
                print(f"  AVISO: {ano}: arquivos lidos mas sem linhas aproveitaveis", file=sys.stderr)
                continue
            for nome_, rot_ in (("rec", "receitas"), ("des", "despesas")):
                tot_ = defaultdict(float)
                for k_, v_ in getattr(junto, nome_).items():
                    tot_[(k_[1], k_[3])] += v_[0]
                top_ = sorted(tot_.items(), key=lambda t: -abs(t[1]))[:6]
                print(f"  maiores categorias de {rot_} {ano}: {[(b_, cat_[:40], round(v_)) for (b_, cat_), v_ in top_]}")
            _gravar(con, ano, bases + (("fundos_tse",) if any(k[1] == "fundos_tse" for k in junto.rec) else ()), junto)
            feitos += 1
            print(f"  Partidos {ano} ({'campanha' if campanha else 'anual'}): {junto.linhas} linhas, {len({k[2] for k in junto.rec})} partidos")
    print(f"Partidos: {feitos} cargas novas")
    return feitos
