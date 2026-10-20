"""Gera o site estatico a partir dos CSVs do resumo (pipeline.verificar).

Uso: python site/build.py --resumo resumo --saida dist [--base-url https://rinaldotg.github.io/gastos-politicos]
"""
import argparse
import csv
import sys
import json
import re
import shutil
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.partidos import sigla as chave_partido  # noqa: E402
from pipeline.classe import BANCOS as BANCOS_CLASSE, PRIVADOS, ROTULO as ROTULO_CLASSE, classificar  # noqa: E402
from jinja2 import Environment, FileSystemLoader, select_autoescape

AQUI = Path(__file__).parent
# Valores legais por mes (2026), como documentados em conteudo/o_que_cobre.md. Sao limites, nao gasto efetivo.
CUSTO_MANDATO = {
    "deputado_federal": dict(subsidio=46366.19, gabinete=165806.07, moradia=4253.00),
    "senador": dict(subsidio=46366.19, gabinete=None, moradia=None),
}
UFS = {"AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
       "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
       "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
       "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins"}

CARGOS = {
    "deputado_federal": ("deputado", "Deputado federal", "Deputados federais"),
    "senador": ("senador", "Senador", "Senadores"),
    "presidente": ("presidente", "Presidente da República", "Presidentes"),
}
MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "em", "no", "na", "nos", "nas", "para", "ao", "com", "por"}
SIGILO = "Informações protegidas por sigilo"
FORA_DO_NUCLEO = ("VICE", "INTELIGENCIA", "EMPRESA BRASIL", "IMPRENSA NACIONAL", "INTERVENCAO", "SETORIAL")
MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def sem_acento(s):
    return "".join(ch for ch in unicodedata.normalize("NFD", s or "") if unicodedata.category(ch) != "Mn")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", sem_acento(s).lower()).strip("-")


def nome_bonito(n):
    n = (n or "").strip()
    if n.isupper() or n.islower():
        n = " ".join(p if i and p.lower() in MINUSCULAS else p[:1].upper() + p[1:].lower()
                     for i, p in enumerate(n.lower().split()))
    return n


def data_br(t):
    """Data da fonte (dd/mm/aaaa ou aaaa-mm-dd) em dd/mm/aaaa."""
    t = (t or "").strip()[:10]
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else t


def ler(resumo, nome):
    with open(Path(resumo) / f"{nome}.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def brl(v, casas=0):
    s = f"{abs(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if v < 0 else "") + "R$ " + s


def brl_curto(v):
    a = abs(v)
    sinal = "−" if v < 0 else ""
    if a >= 1e12:
        return f"{sinal}R$ {a / 1e12:.2f} tri".replace(".", ",")
    if a >= 1e9:
        return f"{sinal}R$ {a / 1e9:.1f} bi".replace(".", ",")
    if a >= 1e6:
        return f"{sinal}R$ {a / 1e6:.1f} mi".replace(".", ",")
    if a >= 1e3:
        return f"{sinal}R$ {a / 1e3:.0f} mil"
    return brl(v)


def grupo_unidade(u):
    up = sem_acento(u).upper()
    return "fora" if any(k in up for k in FORA_DO_NUCLEO) else "nucleo"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resumo", default="resumo")
    ap.add_argument("--saida", default="dist")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--anterior", default="", help="snapshot.json da atualizacao anterior (para a pagina de novidades)")
    a = ap.parse_args()
    saida = Path(a.saida)
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    shutil.copytree(AQUI / "static", saida / "static")

    pessoas = {int(r["id"]): r for r in ler(a.resumo, "pessoa")}
    gac = ler(a.resumo, "gasto_ano_categoria")
    mensal = ler(a.resumo, "gasto_mensal")
    try:
        mes_cat = ler(a.resumo, "gasto_mes_categoria")
    except FileNotFoundError:
        mes_cat = []
    atu = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0, 0, 0]))  # pid -> ano -> [proposicoes, pl, pec, normas, votos, janela]
    try:
        for r in ler(a.resumo, "atuacao"):
            t_ = atu[int(r["pessoa_id"])][int(f(r["ano"]))]
            for k_, nome_ in enumerate(("proposicoes", "pl", "pec", "normas", "votos", "votacoes_janela")):
                t_[k_] += int(f(r.get(nome_)))
    except FileNotFoundError:
        pass
    tc = defaultdict(lambda: dict(f={}, p={}))  # slug do municipio no site -> ano -> dados do TCE-SP (piloto Sao Paulo)
    try:
        for r in ler(a.resumo, "tce_funcao"):
            y = tc[r["slug"] + "-sp"]["f"].setdefault(str(int(f(r["ano"]))), {}).setdefault(r["funcao"], dict(proprio=0, federal=0, estadual=0, outras=0))
            y[r["fonte"]] = round(f(r["pago"]))
        for r in ler(a.resumo, "tce_pagamento"):
            tc[r["slug"] + "-sp"]["p"].setdefault(str(int(f(r["ano"]))), []).append(
                [r["documento"], r["fornecedor"], r["funcao"], r["fonte"], int(f(r["emenda"])), r["historico"], round(f(r["pago"])), int(f(r["n"])), r.get("modalidade") or ""])
    except FileNotFoundError:
        pass
    tcf = defaultdict(lambda: defaultdict(list))  # slug-sp -> ano -> [doc, nome, classe, pago, federal, dispensa, n]
    try:
        for r in ler(a.resumo, "tce_fornecedor"):
            tcf[r["slug"] + "-sp"][str(int(f(r["ano"])))].append([r["documento"], r["fornecedor"], r["classe"], round(f(r["pago"])), round(f(r["pago_federal"])), round(f(r["pago_dispensa"])), int(f(r["n"]))])
    except FileNotFoundError:
        pass
    pm = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))  # pid -> ano -> mes -> categoria -> total
    for r in mes_cat:
        if f(r["total"]) != 0 and r.get("mes"):
            pm[int(r["pessoa_id"])][str(int(f(r["ano"])))][str(int(f(r["mes"])))][r["categoria"] or "(sem tipo)"] = round(f(r["total"]), 2)
    forn = ler(a.resumo, "top_fornecedores")
    unid = ler(a.resumo, "presidencia_unidades")
    emag = ler(a.resumo, "emenda_agregado")
    efun = ler(a.resumo, "emenda_funcao")
    orc = ler(a.resumo, "orcamento_acao")
    mand = ler(a.resumo, "mandato")
    logc = ler(a.resumo, "coleta_log")
    try:
        edet = ler(a.resumo, "emenda_detalhe")
    except FileNotFoundError:
        edet = []
    favs_raw = defaultdict(list)  # codigo -> [nome, doc, tipo, local, valor, ano do pagamento]
    try:
        for r in ler(a.resumo, "emenda_favorecido"):
            doc = (r.get("documento") or "").strip()
            digitos = re.sub(r"\D", "", doc)
            pf = bool(doc) and ("*" in doc or len(digitos) <= 11)  # CPF: pessoa fisica, nome nao e exibido
            favs_raw[r["codigo"]].append([("Pessoa física (nome omitido)" if pf else nome_bonito(r.get("favorecido") or "Não informado")),
                                          "" if pf else doc, (r.get("tipo") or ""),
                                          (f'{nome_bonito(r["municipio"])}/{r["uf"]}' if r.get("municipio") and r.get("uf") else (r.get("uf") or "")),
                                          round(f(r["valor"])), int(f(r.get("ano") or 0))])
    except FileNotFoundError:
        pass
    sanc = defaultdict(list)  # cnpj (14 digitos) -> [cadastro, categoria, inicio, fim, orgao]
    try:
        for r in ler(a.resumo, "sancao"):
            sanc[re.sub(r"\D", "", r["documento"]).zfill(14)].append([r["cadastro"], (r.get("categoria") or "").strip(), data_br(r.get("inicio")), data_br(r.get("fim")), (r.get("orgao") or "").strip()])
    except FileNotFoundError:
        pass
    favs = {}  # codigo -> favorecidos somando todos os anos (maiores primeiro)
    for cod_, rows_ in favs_raw.items():
        ag_ = {}
        for nome_, doc_, tipo_, loc_, valor_, ano_ in rows_:
            k_ = (doc_, nome_) if doc_ else ("", nome_)
            if k_ in ag_:
                ag_[k_][4] += valor_
            else:
                ag_[k_] = [nome_, doc_, tipo_, loc_, valor_]
        favs[cod_] = sorted(([*v_, classificar(v_[0], v_[1]), 1 if sanc.get(re.sub(r"\D", "", v_[1]).zfill(14)) else 0] for v_ in ag_.values()), key=lambda t: -t[4])
    obras_cnpj = defaultdict(list)  # cnpj (14 digitos) -> obras do Obras.gov.br cujo executor e esse recebedor
    try:
        for r in ler(a.resumo, "obra"):
            dg = re.sub(r"\D", "", r.get("executor_cnpj") or "").zfill(14)
            obras_cnpj[dg].append([r.get("id_unico") or "", (r.get("nome") or "").strip(), (r.get("situacao") or "").strip() or "Situação não informada",
                                   (r.get("tipo") or "").strip(), round(f(r.get("valor"))), data_br(r.get("fim_prev")),
                                   data_br(r.get("ini_efetiva")), data_br(r.get("fim_efetiva"))])
    except FileNotFoundError:
        pass
    populacao = {}
    try:
        for r in ler(a.resumo, "municipio_pop"):
            populacao[slugify(f'{r["nome"]}-{r["uf"]}')] = int(f(r["populacao"]))
    except FileNotFoundError:
        pass
    convenios = defaultdict(list)
    try:
        for r in ler(a.resumo, "emenda_convenio"):
            convenios[r["codigo"]].append([r.get("numero") or "", nome_bonito(r.get("convenente") or ""), (r.get("objeto") or "").strip(),
                                           (r.get("situacao") or "").strip(), round(f(r.get("valor"))), round(f(r.get("liberado"))),
                                           data_br(r.get("inicio")), data_br(r.get("fim")), data_br(r.get("publicacao"))])
    except FileNotFoundError:
        pass

    atualizado = max((r["coletado_em"] for r in logc), default="")[:10]
    atualizado_txt = ""
    if atualizado:
        d = datetime.fromisoformat(atualizado)
        atualizado_txt = f"{d.day} de {MESES_PT[d.month - 1]} de {d.year}"

    # ---- agregacao por pessoa ----
    anos = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # pid -> ano -> cat -> total
    fontes_ano = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # pid -> ano -> fonte -> total
    ids_pres = {pid for pid, p in pessoas.items() if p["cargo"] == "presidente"}
    for r in gac:
        pid = int(r["pessoa_id"])
        if pid in ids_pres:
            continue  # presidente vem de presidencia_unidades (filtrado por orgao)
        anos[pid][int(r["ano"])][r["categoria"] or "(sem tipo)"] += f(r["total"])
        fontes_ano[pid][int(r["ano"])][r["fonte"]] += f(r["total"])
    fora = defaultdict(lambda: defaultdict(float))  # presidente: total fora do nucleo, por ano
    unidades_ano = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for r in unid:
        pid, ano = int(r["pessoa_id"]), int(r["ano"])
        if grupo_unidade(r["unidade"]) == "fora":
            fora[pid][ano] += f(r["total"])
            continue
        anos[pid][ano][r["categoria"] or "(sem tipo)"] += f(r["total"])
        fontes_ano[pid][ano][r["fonte"]] += f(r["total"])
        unidades_ano[pid][ano][r["unidade"] or "(sem unidade)"] += f(r["total"])
    meses = defaultdict(lambda: defaultdict(int))
    for r in mensal:
        if f(r["total"]) != 0:
            meses[int(r["pessoa_id"])][int(r["ano"])] += 1
    forn_doc = defaultdict(list)  # pid -> (fornecedor, total, documento)
    for r in forn:
        forn_doc[int(r["pessoa_id"])].append((r["fornecedor"], f(r["total"]), re.sub(r"\D", "", r.get("cnpj_cpf") or "")))
    fornec = defaultdict(list)
    for r in forn:
        fornec[int(r["pessoa_id"])].append((r["fornecedor"], f(r["total"]), int(r["n"])))
    emendas = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))
    emendas_tipo = defaultdict(lambda: defaultdict(float))
    for r in emag:
        if not r["pessoa_id"]:
            continue
        pid, ano = int(float(r["pessoa_id"])), int(r["ano"])
        e = emendas[pid][ano]
        e[0] += f(r["empenhado"]); e[1] += f(r["liquidado"]); e[2] += f(r["pago"])
        emendas_tipo[pid]["pix" if "Especiais" in r["tipo"] else "def"] += f(r["pago"])
    rap = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))  # pid -> ano -> [inscritos, cancelados, pagos]
    for r in emag:
        if r["pessoa_id"]:
            e = rap[int(float(r["pessoa_id"]))][int(r["ano"])]
            e[0] += f(r.get("rap_inscrito")); e[1] += f(r.get("rap_cancelado")); e[2] += f(r.get("rap_pago"))
    pix = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))  # pid -> ano -> [empenhado, pago]
    for r in emag:
        if r["pessoa_id"] and "Especiais" in r["tipo"]:
            e = pix[int(float(r["pessoa_id"]))][int(r["ano"])]
            e[0] += f(r["empenhado"]); e[1] += f(r["pago"])
    detalhe = defaultdict(list)
    for r in edet:
        if not r["pessoa_id"]:
            continue
        loc = f'{r["municipio"]}/{r["uf"]}' if r.get("municipio") and r.get("uf") else (r.get("localidade") or r.get("uf") or "")
        detalhe[int(float(r["pessoa_id"]))].append([
            int(r["ano"]), 1 if "Especiais" in r["tipo"] else 0, r.get("numero") or "", r.get("codigo") or "", loc,
            r.get("funcao") or "", r.get("subfuncao") or "", r.get("programa") or "", r.get("acao") or "",
            round(f(r["empenhado"])), round(f(r["liquidado"])), round(f(r["pago"]))])
    em_funcao = defaultdict(lambda: defaultdict(float))
    for r in efun:
        if r["pessoa_id"]:
            em_funcao[int(float(r["pessoa_id"]))][r["funcao"] or "Não informada"] += f(r["pago"])
    orcamento = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # pid -> ano -> programa -> pago
    orc_orgao = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for r in orc:
        pid, ano = int(r["pessoa_id"]), int(r["ano"])
        prog = r["programa"] or "(sem programa)"
        if r["orgao"] and grupo_unidade(r["orgao"]) == "fora":
            continue  # Vice-Presidencia, EBC, Imprensa Nacional: fora do total do presidente
        pago = f(r.get("pago") or list(r.values())[-1])
        orcamento[pid][ano][prog] += pago
        if r["orgao"] and not prog.upper().startswith("OPERACOES ESPECIAIS"):
            orc_orgao[pid][ano][r["orgao"]] += pago
    legis = defaultdict(set)
    for r in mand:
        legis[int(r["pessoa_id"])].add(int(r["legislatura"]))

    # ---- pessoas publicaveis ----
    lista, usados = [], set()
    for pid, p in sorted(pessoas.items()):
        if not anos.get(pid) and pid not in emendas:
            continue
        cod = CARGOS[p["cargo"]][0]
        nome = nome_bonito(p["nome"])
        base = slugify(nome + ("-" + p["uf"] if p["uf"] else ""))
        slug = base
        if (cod, slug) in usados:
            slug = f"{base}-{pid}"
        usados.add((cod, slug))
        tot_ano = {ano: sum(c.values()) for ano, c in anos[pid].items()}
        ext = (p.get("id_externo") or "").strip()
        oficial = (f"https://www.camara.leg.br/deputados/{ext}" if p["cargo"] == "deputado_federal" else
                   f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{ext}" if p["cargo"] == "senador" else "") if ext else ""
        lista.append(dict(id=pid, oficial=oficial, nome=nome, cargo=p["cargo"], cod=cod, slug=slug, uf=p["uf"], partido=p["partido"],
                          url=f"{cod}/{slug}/", anos=tot_ano, legis=sorted(legis.get(pid, ()))))
    por_id = {x["id"]: x for x in lista}

    ano_atual = max((a_ for x in lista for a_ in x["anos"]), default=datetime.now().year)
    ano_ref = ano_atual - 1  # ultimo ano completo
    # ranking por cargo/ano
    ranking = {}
    posicao = {}
    for cargo in CARGOS:
        ranking[cargo] = {}
        for ano in range(2014, ano_atual + 1):
            linhas = [(x["anos"][ano], x) for x in lista if x["cargo"] == cargo and x["anos"].get(ano, 0) > 0]
            linhas.sort(key=lambda t: -t[0])
            ranking[cargo][ano] = [[x["nome"], x["url"], x["uf"] or "", x["partido"] or "", round(v), meses[x["id"]].get(ano, 0)]
                                   for v, x in linhas]
            if ano == ano_ref:
                for i, (v, x) in enumerate(linhas, 1):
                    posicao[x["id"]] = (i, len(linhas))

    # ---- templates ----
    env = Environment(loader=FileSystemLoader(AQUI / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["brl"] = brl
    env.filters["curto"] = brl_curto
    env.filters["brl2"] = lambda v: "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    env.filters["milhar"] = lambda v: f"{int(v):,}".replace(",", ".")
    env.filters["pct"] = lambda v: f"{v * 100:.0f}%".replace(".", ",")
    base_url = a.base_url.rstrip("/")
    ctx_base = dict(atualizado=atualizado_txt, ano_atual=ano_atual, ano_ref=ano_ref, base_url=base_url, raiz="")

    def escrever(rel, html):
        dest = saida / rel / "index.html" if not rel.endswith(".html") else saida / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")

    # ---- quem recebeu o dinheiro das emendas de cada parlamentar: publico x privado ----
    cod_pid = {l_[3]: pid_ for pid_, ls_ in detalhe.items() for l_ in ls_ if l_[3]}
    destino = {}
    for cod_, rows_ in favs_raw.items():
        pid_ = cod_pid.get(cod_)
        if pid_ is None:
            continue
        d_ = destino.setdefault(pid_, dict(g=defaultdict(float), r={}))
        for nome_, doc_, tipo_, loc_, valor_, ano_ in rows_:
            cl_ = classificar(nome_, doc_) if doc_ else "pf"
            d_["g"][cl_] += valor_
            if cl_ in PRIVADOS:
                k_ = re.sub(r"\D", "", doc_)
                x_ = d_["r"].setdefault(k_, [nome_, doc_, cl_, 0, set()])
                x_[3] += valor_; x_[4].add(cod_)
    for pid_, d_ in destino.items():
        tot_ = sum(v_ for k_, v_ in d_["g"].items() if k_ != "banco")
        priv_ = sum(d_["g"].get(k_, 0) for k_ in PRIVADOS)
        d_["total"] = tot_
        d_["privado"] = priv_
        d_["pct"] = priv_ / tot_ * 100 if tot_ > 0 else None
        d_["top"] = sorted(([x_[0], x_[1], x_[2], x_[3], len(x_[4]), sanc.get(re.sub(r"\D", "", x_[1]).zfill(14), [])] for x_ in d_["r"].values()), key=lambda t: -t[3])[:10]
        d_["grupos"] = [(ROTULO_CLASSE[k_], v_, v_ / tot_ * 100 if tot_ > 0 else 0) for k_, v_ in sorted(d_["g"].items(), key=lambda t: -t[1]) if k_ != "banco" and v_ > 0]

    # ---- indicadores comparaveis (periodo da legislatura atual) e pares ----
    PERIODO = 2023
    cl_pa = {}
    def classe_pa(nome_, doc_):
        k_ = (nome_, doc_)
        if k_ not in cl_pa:
            cl_pa[k_] = classificar(nome_, doc_) if doc_ else "pf"
        return cl_pa[k_]
    priv_pa = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))  # pid -> ano de pagamento -> [privado, total sem bancos]
    for cod_, rows_ in favs_raw.items():
        pid_ = cod_pid.get(cod_)
        if pid_ is None:
            continue
        for nome_, doc_, tipo_, loc_, valor_, ano_p in rows_:
            cl_ = classe_pa(nome_, doc_)
            if cl_ == "banco":
                continue
            z_ = priv_pa[pid_][ano_p]
            z_[1] += valor_
            if cl_ in PRIVADOS:
                z_[0] += valor_

    def calcular_stats(no_periodo, minimo_priv):
        st_ = {}
        for x in lista:
            if x["cargo"] == "presidente":
                continue
            pid_ = x["id"]
            meses_p = sum(n_ for y_, n_ in meses[pid_].items() if no_periodo(y_))
            cota_p = sum(sum(anos[pid_][y_].values()) for y_ in anos[pid_] if no_periodo(y_))
            e_ = [sum(v_[i_] for y_, v_ in emendas.get(pid_, {}).items() if no_periodo(y_)) for i_ in range(3)]
            t_ = [sum(v_[i_] for y_, v_ in atu.get(pid_, {}).items() if no_periodo(y_)) for i_ in range(6)]
            tem_atu = any(no_periodo(y_) for y_ in atu.get(pid_, {}))
            pv_ = [sum(v_[0] for y_, v_ in priv_pa[pid_].items() if no_periodo(y_)), sum(v_[1] for y_, v_ in priv_pa[pid_].items() if no_periodo(y_))] if pid_ in priv_pa else [0, 0]
            st_[pid_] = dict(
                meses=meses_p, cota=round(cota_p),
                cota_mes=(cota_p / meses_p) if meses_p >= 3 else None,
                em_emp=round(e_[0]), em_pago=round(e_[2]), em_pct=(e_[2] / e_[0] * 100) if e_[0] > 0 else None,
                proj=(t_[1] + t_[2]) if tem_atu else None, pec=t_[2] if tem_atu else None, leis=t_[3] if tem_atu else None,
                presenca=(min(100.0, t_[4] / t_[5] * 100) if t_[5] > 0 else None), votos=t_[4],
                priv_pct=(pv_[0] / pv_[1] * 100 if pv_[1] >= minimo_priv else None))
        return st_
    stats = calcular_stats(lambda y_: y_ >= PERIODO, 1000000)
    CURTO = {"cota_mes": "Cota por mês", "em_pct": "Emendas pagas", "presenca": "Presença", "proj": "Projetos", "leis": "Viraram norma", "priv_pct": "Emendas a privados"}
    INDICADORES = [  # chave, rotulo, menor_e_melhor, formato
        ("cota_mes", "Cota parlamentar por mês de mandato", True, "brl"),
        ("em_pct", "Emendas pagas (% do empenhado)", False, "pct"),
        ("presenca", "Presença em votações nominais", False, "pct"),
        ("proj", "Projetos de lei e PEC de sua autoria", False, "int"),
        ("leis", "Projetos de sua autoria que viraram norma", False, "int"),
        ("priv_pct", "Emendas pagas direto a empresas e entidades privadas (%)", None, "pct"),
    ]

    def mediana_(v_):
        v_ = sorted(v_)
        return (v_[len(v_) // 2] if len(v_) % 2 else (v_[len(v_) // 2 - 1] + v_[len(v_) // 2]) / 2) if v_ else None

    def painel_de(x):
        if x["id"] not in stats:
            return None
        pares = [y for y in lista if y["cargo"] == x["cargo"] and y["uf"] == x["uf"] and y["id"] in stats]
        escopo = f"mesmo cargo no estado ({x['uf']})"
        if len(pares) < 5:
            pares = [y for y in lista if y["cargo"] == x["cargo"] and y["id"] in stats]
            escopo = "mesmo cargo no país"
        linhas_ = []
        for k_, rot_, menor_, fmt_ in INDICADORES:
            v_ = stats[x["id"]].get(k_)
            vs_ = [stats[y["id"]][k_] for y in pares if stats[y["id"]].get(k_) is not None]
            if v_ is None or len(vs_) < 3:
                linhas_.append(dict(rot=rot_, fmt=fmt_, v=v_, mediana=None, pos=None, n=len(vs_), menor=menor_))
                continue
            melhores_ = sum(1 for w_ in vs_ if (w_ < v_ if menor_ else w_ > v_))  # menor_ None: sem juizo, ordena do maior para o menor
            linhas_.append(dict(rot=rot_, fmt=fmt_, v=v_, mediana=mediana_(vs_), pos=melhores_ + 1, n=len(vs_), menor=menor_))
        return dict(linhas=linhas_, escopo=escopo, n=len(pares), meses=stats[x["id"]]["meses"], periodo=PERIODO)

    (saida / "data" / "p").mkdir(parents=True)
    def linhas_pares(st_):
        return [[x["id"], x["nome"], x["url"], x["uf"] or "", x["partido"] or "", x["cod"]] + [
            (round(st_[x["id"]][k_], 1) if st_[x["id"]].get(k_) is not None else None) for k_, _, _, _ in INDICADORES] + [st_[x["id"]]["meses"]]
            for x in lista if x["id"] in st_ and st_[x["id"]]["meses"] >= 3]
    ind_json = [[k_, r_, m_, f_, CURTO.get(k_, r_)] for k_, r_, m_, f_ in INDICADORES]
    def gravar_pares(nome_, st_, rotulo_):
        (saida / "data" / nome_).write_text(json.dumps(dict(periodo=rotulo_, ind=ind_json, linhas=linhas_pares(st_)), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    gravar_pares("pares.json", stats, f"desde {PERIODO}")
    anos_pares = sorted({y_ for x in lista if x["cargo"] != "presidente" for y_ in meses[x["id"]] if y_ >= 2015}, reverse=True)
    for y_ in anos_pares:
        gravar_pares(f"pares-{y_}.json", calcular_stats(lambda a_, y_=y_: a_ == y_, 200000), f"em {y_}")
    forn_a = defaultdict(lambda: defaultdict(list))  # pid -> ano -> [[fornecedor, total, n]]
    try:
        for r_ in ler(a.resumo, "fornecedor_ano_pessoa"):
            forn_a[int(r_["pessoa_id"])][str(int(f(r_["ano"])))].append([r_["fornecedor"], round(f(r_["total"])), int(f(r_["n"]))])
    except FileNotFoundError:
        pass
    equipe = defaultdict(list)  # pessoa_id -> [[nome, cargo, nomeacao]]
    try:
        for r_ in ler(a.resumo, "gabinete_pessoa"):
            equipe[int(r_["pessoa_id"])].append([nome_bonito(r_["nome"]), (r_.get("cargo") or "").strip(), data_br(r_.get("nomeacao"))])
    except FileNotFoundError:
        pass
    pres_datas = {int(r["pessoa_id"]): (r["data_inicio"], r["data_fim"]) for r in mand if r["cargo"] == "presidente"}
    pres_resumo = []
    for x in lista:
        pid = x["id"]
        profundidade = 2
        anos_ord = sorted(anos[pid], reverse=True)
        max_ano = max((sum(anos[pid][y].values()) for y in anos_ord), default=1) or 1
        linhas_ano = []
        for y in anos_ord:
            cats = sorted(anos[pid][y].items(), key=lambda t: -t[1])
            tot = sum(c for _, c in cats)
            linhas_ano.append(dict(ano=y, total=tot, largura=max(0, tot) / max_ano * 100, meses=meses[pid].get(y, 0),
                                   parcial=(y == ano_atual), cats=[(c, v, (v / tot if tot > 0 else 0)) for c, v in cats],
                                   fora=fora[pid].get(y, 0) if x["cargo"] == "presidente" else 0))
        total_geral = sum(l["total"] for l in linhas_ano)
        mand_x = None
        if x["cargo"] == "presidente":
            ini_, fim_ = pres_datas.get(pid, ("2014-01-01", "9999-12-31"))
            ini_ef, fim_ef = max(ini_, "2014-01-01"), min(fim_, atualizado or "9999-12-31")
            n_m = max(1, (int(fim_ef[:4]) - int(ini_ef[:4])) * 12 + int(fim_ef[5:7]) - int(ini_ef[5:7]) + 1)
            cats_m = defaultdict(float)
            for y_ in anos[pid]:
                for c_, v_ in anos[pid][y_].items():
                    cats_m[c_] += v_
            cats_m = sorted(cats_m.items(), key=lambda t: -t[1])
            mand_x = dict(ini=ini_ef, fim=fim_ef if fim_ < "9999" else None, ini_real=ini_, aberto=fim_ >= "9999", meses=n_m, total=total_geral,
                          por_mes=total_geral / n_m, recorte=ini_ < "2014-01-01",
                          cats=[(c_, v_, (v_ / total_geral if total_geral > 0 else 0)) for c_, v_ in cats_m])
            pres_resumo.append(dict(x=x, **mand_x))
        forn_x = sorted(fornec.get(pid, []), key=lambda t: -t[1])[:15]
        em = sorted(emendas.get(pid, {}).items(), reverse=True)
        em_tot = [sum(e[i] for _, e in em) for i in range(3)]
        em_exec = None
        if em and em_tot[0] > 0:
            corte = ano_atual - 2  # emendas de ate dois anos atras ja tiveram tempo de ser executadas
            antigas = [e for a_, e in em if a_ <= corte]
            ra = rap.get(pid, {})
            em_exec = dict(pct=em_tot[2] / em_tot[0], corte=corte,
                           emp_ant=sum(e[0] for e in antigas), pago_ant=sum(e[2] for e in antigas),
                           rap_i=sum(v[0] for v in ra.values()), rap_c=sum(v[1] for v in ra.values()), rap_p=sum(v[2] for v in ra.values()))
            em_exec["pct_ant"] = (em_exec["pago_ant"] / em_exec["emp_ant"]) if em_exec["emp_ant"] > 0 else None
        sig = None
        if x["cargo"] == "presidente":
            cartao = sum(fontes_ano[pid][y].get("pres_cpgf", 0) for y in fontes_ano[pid])
            sg = sum(anos[pid][y].get(SIGILO, 0) for y in anos[pid])
            sig = dict(cartao=cartao, sigilo=sg, parte=(sg / cartao if cartao else 0),
                       viagens=sum(fontes_ano[pid][y].get("pres_viagem", 0) for y in fontes_ano[pid]))
        orc_x = []
        if x["cargo"] == "presidente":
            for y in sorted(orcamento[pid], reverse=True):
                progs = sorted(orcamento[pid][y].items(), key=lambda t: -t[1])
                financeiras = [(p_, v) for p_, v in progs if p_.upper().startswith("OPERACOES ESPECIAIS")]
                normais = [(p_, v) for p_, v in progs if not p_.upper().startswith("OPERACOES ESPECIAIS")]
                orgs = [(nome_bonito(g_), v) for g_, v in sorted(orc_orgao[pid][y].items(), key=lambda t: -t[1])[:8] if v > 0]
                if len(orgs) < 2:
                    orgs = []
                normais = [(nome_bonito(p_), v) for p_, v in normais if v > 0]
                orc_x.append(dict(ano=y, total=sum(v for _, v in normais), programas=normais[:12],
                                  financeiras=sum(v for _, v in financeiras), financeiras_det=financeiras[:5], orgaos=orgs))
        orc_tot = None
        if orc_x:
            pg_ = defaultdict(float)
            for o in orc_x:
                for prog_, v_ in o["programas"]:
                    pg_[prog_] += v_
            orc_tot = dict(total=sum(o["total"] for o in orc_x), programas=sorted(pg_.items(), key=lambda t: -t[1])[:15],
                           financeiras=sum(o["financeiras"] for o in orc_x))
        if orc_x:
            mx = max(o["total"] for o in orc_x) or 1
            for o in orc_x:
                o["largura"] = max(0, o["total"]) / mx * 100
        tem_mes = bool(pm.get(pid)) and x["cargo"] != "presidente"
        if tem_mes:
            (saida / "data" / "pm").mkdir(parents=True, exist_ok=True)
            (saida / "data" / "pm" / f"{pid}.json").write_text(json.dumps(pm[pid], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        html = env.get_template("pessoa.html").render(painel=painel_de(x), destino=destino.get(pid), tem_mes=tem_mes, anos_mes=sorted(pm[pid], reverse=True) if tem_mes else [],
            **{**ctx_base, "raiz": "../../"}, titulo=f"{x['nome']}: gastos desde 2014", p=x, cargo_rotulo=CARGOS[x["cargo"]][1],
            linhas_ano=linhas_ano, total_geral=total_geral, fornecedores=forn_x, emendas=em, em_tot=em_tot, em_exec=em_exec, custo=CUSTO_MANDATO.get(x["cargo"]), ano_ref_cota=x["anos"].get(ano_ref, 0),
            em_pix=emendas_tipo[pid].get("pix", 0), em_def=emendas_tipo[pid].get("def", 0),
            em_funcao=[t for t in sorted(em_funcao[pid].items(), key=lambda t: -t[1]) if t[1] > 0][:6], sig=sig, orc=orc_x, orc_tot=orc_tot, mand=mand_x, forn_anos=json.dumps(forn_a.get(pid, {}), separators=(",", ":"), ensure_ascii=False), equipe=sorted(equipe.get(pid, []), key=lambda t: (t[1], t[0])),
            custo_anos=json.dumps({str(y_): [meses[pid].get(y_, 0), round(sum(anos[pid][y_].values()))] for y_ in anos[pid] if y_ >= 2015}, separators=(",", ":")),
            uf_url=(f"estado/{x['uf'].lower()}/" if x["uf"] in UFS else ""), pos=posicao.get(pid) if x["cargo"] != "presidente" else None, tem_detalhe=bool(detalhe.get(pid)), desde=(min(anos[pid]) if anos[pid] else 2014), em_desde=(min(emendas[pid]) if emendas.get(pid) else 2014), ano_ref_total=x["anos"].get(ano_ref, 0), descricao=(
                f"{CARGOS[x['cargo']][1]} {x['nome']}: {brl_curto(total_geral)} em gastos desde 2014, por ano e por tipo de despesa."))
        escrever(f"{x['cod']}/{x['slug']}", html)
        dados = dict(id=pid, n=x["nome"], c=x["cod"], u=x["uf"], p=x["partido"], url=x["url"],
                     anos={str(y): [round(sum(anos[pid][y].values()), 2), meses[pid].get(y, 0),
                                    [[c, round(v, 2)] for c, v in sorted(anos[pid][y].items(), key=lambda t: -t[1])]]
                           for y in anos_ord},
                     em={str(y): [round(v, 2) for v in e] for y, e in em},
                     **({"m": [mand_x["meses"], mand_x["ini"], mand_x["fim"] or ""]} if mand_x else {}))
        (saida / "data" / "p" / f"{pid}.json").write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    if detalhe:
        (saida / "data" / "e").mkdir(parents=True)
        for x in lista:
            linhas = sorted(detalhe.get(x["id"], []), key=lambda t: (-t[11], -t[9]))
            if linhas:
                codigos = {l[3] for l in linhas if l[3]}
                payload = {"r": linhas, "f": {c_: [favs[c_][:3], len(favs[c_])] for c_ in codigos if c_ in favs}}
                (saida / "data" / "e" / f"{x['id']}.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if detalhe and favs:
        # codigo -> informacoes da emenda (somando as linhas) e autor
        info = {}
        for pid_, ls in detalhe.items():
            for l in ls:
                if not l[3]:
                    continue
                i = info.setdefault(l[3], dict(p=pid_, ano=l[0], pix=l[1], num=l[2], dest=[], fn=l[5], prog=l[7], acao=l[8], emp=0, pago=0))
                i["emp"] += l[9]; i["pago"] += l[11]
                if l[4] and l[4] not in i["dest"]:
                    i["dest"].append(l[4])
        N_E, N_R = 120, 200
        # bancos publicos que operam repasses: nao sao destino final do dinheiro, ficam fora de rankings e totais por municipio
        BANCOS = {"00000000000191", "00360305000104", "07237373000120", "04902979000144"}
        gravar = lambda rel, obj: (saida / "data" / rel).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        sh_e, sh_r = defaultdict(dict), defaultdict(dict)
        rec = {}   # documento -> dados
        muni = {}  # slug -> dados do municipio do recebedor
        anos_pag = set()
        for cod, rows_ in favs_raw.items():
            i = info.get(cod)
            if not i:
                continue
            sh_e[int(cod) % N_E if cod.isdigit() else 0][cod] = dict(
                i=[i["p"], i["ano"], i["pix"], i["num"], ", ".join(i["dest"][:4]), i["fn"], round(i["emp"]), round(i["pago"]), i["prog"], i["acao"]],
                f=favs[cod], c=convenios.get(cod, []))
            for nome, doc, tipo, loc, valor, ano_p in rows_:
                anos_pag.add(ano_p)
                dig = re.sub(r"\D", "", doc)
                if "/" in loc and dig not in BANCOS:
                    m_ = muni.setdefault(slugify(loc.replace("/", "-")), dict(n=loc, p={}, r={}))
                    q_ = m_["p"].setdefault(i["p"], {})
                    y_ = q_.setdefault(ano_p, [0, set()])
                    y_[0] += valor; y_[1].add(cod)
                    k_ = (doc, nome) if doc else ("", nome)
                    m_["r"].setdefault(k_, {})
                    m_["r"][k_][ano_p] = m_["r"][k_].get(ano_p, 0) + valor
                if not doc:
                    continue
                r_ = rec.setdefault(doc, dict(n=nome, t=tipo, l=loc, p={}))
                if "/" in loc:
                    r_["l"] = loc
                q = r_["p"].setdefault(i["p"], [i["p"], 0, []])
                q[1] += valor
                q[2].append([cod, i["ano"], i["pix"], valor, ano_p, i["fn"]])
        (saida / "data" / "fe").mkdir(parents=True, exist_ok=True)
        (saida / "data" / "fr").mkdir(parents=True, exist_ok=True)
        (saida / "data" / "m").mkdir(parents=True, exist_ok=True)
        for k, v in sh_e.items():
            gravar(f"fe/{k}.json", v)
        rank_ano = defaultdict(dict)  # ano ("" = todos) -> doc -> [nome, doc, valor, parlamentares]
        for doc, r_ in rec.items():
            dig = re.sub(r"\D", "", doc)
            obs_ = sorted(obras_cnpj.get(dig.zfill(14), []), key=lambda t: (t[2] != "Paralisada", -t[4]))
            cont_ = {}
            for o_ in obs_:
                cont_[o_[2]] = cont_.get(o_[2], 0) + 1
            sh_r[int(dig) % N_R if dig else 0][doc] = dict(
                ob=[cont_, obs_[:40]], b=1 if dig in BANCOS else 0, g=classificar(r_["n"], doc), s=sanc.get(dig.zfill(14), []), n=r_["n"], t=r_["t"], l=r_["l"], p=sorted(r_["p"].values(), key=lambda t: -t[1]))
            if dig in BANCOS:
                continue
            por_ano = defaultdict(lambda: [0, set()])
            tot_ = [0, set()]
            for pid_, q in r_["p"].items():
                for _, _, _, v_, ap_, _ in q[2]:
                    por_ano[ap_][0] += v_; por_ano[ap_][1].add(pid_)
                    tot_[0] += v_; tot_[1].add(pid_)
            rank_ano[""][doc] = [r_["n"], doc, tot_[0], len(tot_[1])]
            for ap_, (v_, ps_) in por_ano.items():
                if ap_:
                    rank_ano[str(ap_)][doc] = [r_["n"], doc, v_, len(ps_)]
        for k, v in sh_r.items():
            gravar(f"fr/{k}.json", v)
        rank_json = {}
        for ap_, d_ in rank_ano.items():
            lst_ = list(d_.values())
            rank_json[ap_] = dict(v=sorted(lst_, key=lambda t: -t[2])[:150],
                                  q=sorted([t for t in lst_ if t[3] > 1], key=lambda t: (-t[3], -t[2]))[:150])
        gravar("rec-rank.json", rank_json)
        gravar("rec-busca.json", [[r_["n"], doc, round(sum(q[1] for q in r_["p"].values()))]
                                  for doc, r_ in sorted(rec.items(), key=lambda t: -sum(q[1] for q in t[1]["p"].values()))])
        cl_cache = {}
        def cl_de(nome_, doc_):
            k_ = (nome_, doc_)
            if k_ not in cl_cache:
                cl_cache[k_] = classificar(nome_, doc_) if doc_ else "pf"
            return cl_cache[k_]

        def priv_ano(ano_f):
            """Recebedores privados e parlamentares, no ano de pagamento ano_f (None = todos os anos)."""
            rec_l = []
            for doc_, r_ in rec.items():
                if cl_de(r_["n"], doc_) not in PRIVADOS:
                    continue
                tot_, ps_, ult_ = 0, set(), 0
                for pid_, q_ in r_["p"].items():
                    for e_ in q_[2]:
                        if ano_f and e_[4] != ano_f:
                            continue
                        tot_ += e_[3]; ps_.add(pid_); ult_ = max(ult_, e_[4] or 0)
                if not ps_:
                    continue
                rec_l.append([r_["n"], doc_, cl_de(r_["n"], doc_), round(tot_), len(ps_), r_["l"], sanc.get(re.sub(r"\D", "", doc_).zfill(14), []), [ult_]])
            gp_ = defaultdict(lambda: defaultdict(float))
            tot_priv_ = tot_geral_ = 0
            for cod_, rows_ in favs_raw.items():
                pid_ = cod_pid.get(cod_)
                for nome_, doc_, tipo_, loc_, valor_, ano_p in rows_:
                    if ano_f and ano_p != ano_f:
                        continue
                    cl_ = cl_de(nome_, doc_)
                    if cl_ == "banco":
                        continue
                    tot_geral_ += valor_
                    if cl_ in PRIVADOS:
                        tot_priv_ += valor_
                    if pid_ is not None:
                        gp_[pid_][cl_] += valor_
            minimo_ = 1000000 if not ano_f else 200000
            parl_l = []
            for x in lista:
                g_ = gp_.get(x["id"])
                if not g_ or x["cargo"] == "presidente":
                    continue
                t_ = sum(g_.values())
                if t_ < minimo_:
                    continue
                pr_ = sum(g_.get(k_, 0) for k_ in PRIVADOS)
                parl_l.append([x["nome"], x["url"], x["uf"] or "", x["partido"] or "", x["cod"], round(pr_), round(t_), round(pr_ / t_ * 100, 1)])
            return dict(rec=sorted(rec_l, key=lambda t: -t[3])[:400], parl=sorted(parl_l, key=lambda t: -t[5])[:600],
                        total_priv=round(tot_priv_), total=round(tot_geral_), ano=ano_f or 0)
        gravar("privados.json", priv_ano(None))
        anos_priv = sorted({a_ for a_ in anos_pag if a_}, reverse=True)
        for a_ in anos_priv:
            gravar(f"privados-{a_}.json", priv_ano(a_))
        obras_muni = defaultdict(list)
        for doc, r_ in rec.items():
            dg_ = re.sub(r"\D", "", doc)
            if "/" in r_["l"] and dg_ not in BANCOS and obras_cnpj.get(dg_.zfill(14)):
                for o_ in obras_cnpj[dg_.zfill(14)]:
                    obras_muni[slugify(r_["l"].replace("/", "-"))].append(o_ + [r_["n"]])
        indice_m = []
        for sl, m_ in muni.items():
            por_ano = defaultdict(lambda: [0, set()])
            for pid_, ys in m_["p"].items():
                for ap_, (v_, cs_) in ys.items():
                    por_ano[ap_][0] += v_; por_ano[ap_][1].add(pid_)
                    por_ano[0][0] += v_; por_ano[0][1].add(pid_)
            rs = sorted(m_["r"].items(), key=lambda t: -sum(t[1].values()))
            om_ = sorted(obras_muni.get(sl, []), key=lambda t: (t[2] != "Paralisada", t[2] != "Em execução", -t[4]))
            cm_ = {}
            for o_ in om_:
                cm_[o_[2]] = cm_.get(o_[2], 0) + 1
            gravar(f"m/{sl}.json", dict(
                pop=populacao.get(sl), ob=[cm_, om_[:40]], n=m_["n"],
                tc=({a_: dict(f=[[fn_] + [v_.get(k_, 0) for k_ in ("proprio", "federal", "estadual", "outras")] for fn_, v_ in
                                 sorted(d_.items(), key=lambda t: -sum(t[1].values()))],
                              p=sorted(tc[sl]["p"].get(a_, []), key=lambda t: (-t[4], -t[6]))[:120],
                              r=sorted(([*t_[:6], sanc.get(t_[0].zfill(14), [])[:1]] for t_ in tcf[sl].get(a_, [])), key=lambda t: -t[3])[:60])
                     for a_, d_ in tc[sl]["f"].items()} if sl in tc else None),
                p=sorted([[pid_, {str(ap_): [round(v_), len(cs_)] for ap_, (v_, cs_) in ys.items()}] for pid_, ys in m_["p"].items()],
                         key=lambda t: -sum(v[0] for v in t[1].values())),
                r=[[k[1], k[0], {str(ap_): round(v_) for ap_, v_ in ys.items()}] for k, ys in rs[:1500]], nr=len(rs)))
            indice_m.append([m_["n"], sl, {str(ap_): [round(v_), len(ps_)] for ap_, (v_, ps_) in por_ano.items()}, populacao.get(sl)])
        gravar("municipios.json", sorted(indice_m, key=lambda t: -t[2].get("0", [0])[0]))
        gravar("tce-lista.json", {sl_: sorted(tc[sl_]["f"]) for sl_ in tc if sl_ in muni and tc[sl_]["f"]})
        anos_lista = sorted((a_ for a_ in anos_pag if a_), reverse=True)
        for pagina, titulo_, desc_ in (("municipio", "Emendas recebidas por município", "Quanto cada município recebeu em emendas parlamentares, de quais parlamentares e para quais recebedores."),
                                       ("municipios", "Municípios", "Busque seu município e veja quanto recebeu em emendas parlamentares e de quem."),
                                       ("recebedores", "Quem mais recebe emendas", "Busque empresas, prefeituras e entidades por nome ou CNPJ e veja de quais parlamentares receberam emendas."),
                                       ("emenda", "Quem recebeu a emenda", "Todos os recebedores de uma emenda parlamentar, com valores."),
                                       ("recebedor", "Quem recebeu emendas", "Todos os parlamentares que destinaram emendas a um mesmo recebedor.")):
            escrever(pagina, env.get_template(pagina + ".html").render(**{**ctx_base, "raiz": "../"}, titulo=titulo_, descricao=desc_,
                     n_e=N_E, n_r=N_R, anos_pag=anos_lista))
    pix_lista = [[x["nome"], x["url"], x["cod"], x["uf"] or "", x["partido"] or "",
                  {str(y): [round(v[0]), round(v[1])] for y, v in sorted(pix[x["id"]].items())}] for x in lista if x["id"] in pix]
    (saida / "data" / "pix.json").write_text(json.dumps(pix_lista, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    escrever("emendas-pix", env.get_template("pix.html").render(**{**ctx_base, "raiz": "../"}, titulo="Quem mais usa emendas Pix",
             descricao="Ranking de deputados e senadores por valor de emendas Pix (transferências especiais) indicadas e pagas.",
             anos=sorted({int(y) for t in pix_lista for y in t[5]}, reverse=True)))
    busca = [dict(n=x["nome"], a=slugify(x["nome"]).replace("-", " "), c=x["cod"], u=x["uf"] or "", p=x["partido"] or "",
                  url=x["url"], id=x["id"]) for x in lista]
    (saida / "data" / "busca.json").write_text(json.dumps(busca, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (saida / "data" / "ranking.json").write_text(json.dumps(ranking, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


    # ---- emendas sem autor identificado ----
    try:
        sa = ler(a.resumo, "emenda_sem_autor")
    except FileNotFoundError:
        sa = []
    def cat_sa(tipo, sem_info):
        t = sem_acento(tipo).lower()
        if "relator" in t:
            return "Emendas de relator (RP 9)"
        if "bancada" in t:
            return "Emendas de bancada estadual"
        if "comiss" in t:
            return "Emendas de comissão"
        return "Individuais sem autor informado na fonte" if sem_info == "1" else "Individuais com nome que o site não conseguiu ligar a um parlamentar"
    cats_sa = {}
    for r in sa:
        c_ = cats_sa.setdefault(cat_sa(r["tipo"], r["sem_info"]), dict(n=0, emp=0.0, pago=0.0, anos={}))
        c_["n"] += int(f(r["n"])); c_["emp"] += f(r["empenhado"]); c_["pago"] += f(r["pago"])
        y_ = c_["anos"].setdefault(int(f(r["ano"])), [0, 0.0, 0.0])
        y_[0] += int(f(r["n"])); y_[1] += f(r["empenhado"]); y_[2] += f(r["pago"])
    cats_sa = sorted(cats_sa.items(), key=lambda t: -t[1]["pago"])
    try:
        nomes_sa = [(r["autor"], int(f(r["n"])), f(r["pago"])) for r in ler(a.resumo, "emenda_sem_vinculo")
                    if sem_acento(r["autor"]).lower().startswith("sem informa") is False and "bancada" not in sem_acento(r["tipo"]).lower()
                    and "comiss" not in sem_acento(r["tipo"]).lower() and "relator" not in sem_acento(r["tipo"]).lower()][:30]
    except FileNotFoundError:
        nomes_sa = []
    escrever("sem-autor", env.get_template("sem_autor.html").render(**{**ctx_base, "raiz": "../"}, titulo="Emendas sem autor identificado",
             descricao="Emendas que o site não consegue atribuir a um parlamentar, por quê, e quanto dinheiro representam.", cats=cats_sa, nomes=nomes_sa))

    escrever("pares", env.get_template("pares.html").render(**{**ctx_base, "raiz": "../"}, titulo="Comparar parlamentares entre pares",
             descricao="Custo, execução de emendas e atuação legislativa de cada parlamentar, lado a lado com os pares.", ufs=sorted(UFS.items()), anos=anos_pares, periodo=PERIODO))

    escrever("privados", env.get_template("privados.html").render(**{**ctx_base, "raiz": "../"}, titulo="Emendas para empresas e entidades privadas",
             descricao="Quanto das emendas foi pago direto a empresas e entidades privadas, quem recebeu e de quais parlamentares.", ufs=sorted(UFS.items()), anos=anos_priv))

    # ---- custo dos ministerios por ano (execucao da despesa por orgao superior) ----
    def tipo_orgao(n_):
        k_ = sem_acento(n_).lower()
        if k_.startswith("ministerio publico"):
            return "poderes"
        if k_.startswith("ministerio"):
            return "ministerio"
        if k_.startswith("presidencia"):
            return "presidencia"
        if re.search(r"encargos|transferencias a estados|reserva de contingencia|operacoes oficiais", k_):
            return "encargos"
        if re.search(r"camara|senado|tribunal|justica|conselho nacional|defensoria|congresso", k_):
            return "poderes"
        return "outros"
    min_anos, min_orgaos = [], {}
    FUNC_ = ("pessoal_ativo", "custeio", "pessoal")  # "pessoal" e o bucket da classificacao antiga
    try:
        for r_ in ler(a.resumo, "despesa_orgao"):
            ano_, org_, bk_ = int(r_["ano"]), r_["orgao"], r_["bucket"]
            v_ = f(r_["pago"]) + f(r_["rap_pago"])
            d_ = min_orgaos.setdefault(org_, dict(tipo=tipo_orgao(org_), anos={}, comp={}, div={}, inat={}, prog={}))
            if bk_ == "divida":
                d_["div"][ano_] = d_["div"].get(ano_, 0) + v_
            elif bk_ in FUNC_:
                d_["anos"][ano_] = d_["anos"].get(ano_, 0) + v_
            elif bk_ == "inativos":
                d_["inat"][ano_] = d_["inat"].get(ano_, 0) + v_
            else:
                d_["prog"][ano_] = d_["prog"].get(ano_, 0) + v_
            d_["comp"].setdefault(ano_, {})
            d_["comp"][ano_][bk_] = d_["comp"][ano_].get(bk_, 0) + v_
        mm_ = ler(a.resumo, "despesa_orgao_meses")
        meses_ = {int(r_["ano"]): int(r_["ate_mes"]) for r_ in mm_}
        faltam_ = {int(r_["ano"]): int(r_["ate_mes"]) - int(r_["meses"]) for r_ in mm_ if int(r_["ate_mes"]) - int(r_["meses"]) > 0}
        min_anos = sorted(meses_)
    except (FileNotFoundError, KeyError, ValueError):
        meses_, faltam_ = {}, {}
    if min_anos:
        fechados_ = [y_ for y_ in min_anos if meses_.get(y_, 12) >= 12]
        ult_ = fechados_[-1] if fechados_ else min_anos[-1]
        mins = sorted([(n_, d_) for n_, d_ in min_orgaos.items() if d_["tipo"] == "ministerio"], key=lambda t: -t[1]["anos"].get(ult_, 0))
        tot_min = {y_: sum(d_["anos"].get(y_, 0) for _, d_ in mins) for y_ in min_anos}
        todo_min = {y_: sum(d_["anos"].get(y_, 0) + d_["inat"].get(y_, 0) + d_["prog"].get(y_, 0) for _, d_ in mins) for y_ in min_anos}
        outros_ = {}
        for rot_, tp_ in (("Presidência da República", "presidencia"), ("Encargos e transferências gerais da União", "encargos"), ("Poderes e órgãos de controle (Legislativo, Judiciário, MP, Defensoria)", "poderes"), ("Outros órgãos do Executivo", "outros")):
            outros_[rot_] = {y_: sum(d_["anos"].get(y_, 0) for d_ in min_orgaos.values() if d_["tipo"] == tp_) for y_ in min_anos}
        linhas_min = []
        for n_, d_ in mins:
            cp_ = d_["comp"].get(ult_, {})
            fun_ = d_["anos"].get(ult_, 0)
            todo_ = fun_ + d_["inat"].get(ult_, 0) + d_["prog"].get(ult_, 0)
            linhas_min.append(dict(nome=n_, anos=[d_["anos"].get(y_, 0) for y_ in min_anos], func=fun_, todo=todo_,
                                   pct=(fun_ / todo_ * 100 if todo_ else 0),
                                   pessoal=cp_.get("pessoal_ativo", cp_.get("pessoal", 0)), custeio=cp_.get("custeio", 0),
                                   inat=d_["inat"].get(ult_, 0), prog=d_["prog"].get(ult_, 0)))
        csv_min = "ministerio," + ",".join(str(y_) for y_ in min_anos) + "\n" + "\n".join(
            '"' + l_["nome"].replace('"', "") + '",' + ",".join(f"{v_:.2f}" for v_ in l_["anos"]) for l_ in linhas_min) + \
            "\nTOTAL custo de funcionamento," + ",".join(f"{tot_min[y_]:.2f}" for y_ in min_anos) + "\n"
        (saida / "data").mkdir(parents=True, exist_ok=True)
        (saida / "data" / "ministerios.csv").write_text(csv_min, encoding="utf-8")
    else:
        linhas_min, tot_min, todo_min, outros_, ult_ = [], {}, {}, {}, None
    escrever("ministerios", env.get_template("ministerios.html").render(**{**ctx_base, "raiz": "../"}, titulo="Quanto custa manter cada ministério",
             descricao="Custo de funcionamento de cada ministério por ano (pessoal e despesas de custeio) e o total de todos os ministérios.",
             anos=min_anos, linhas=linhas_min, total=tot_min, todo=todo_min, outros=outros_, parcial={y_: meses_.get(y_, 12) for y_ in min_anos if meses_.get(y_, 12) < 12}, faltam=faltam_, ult=ult_))

    # ---- pontos de atencao: padroes factuais nos dados publicos (nao afirmam irregularidade) ----
    NORMAL = re.compile(r"AEREA|AIRLINES|\bGOL\b|\bTAM\b|AZUL|LATAM|CORREIOS|TELEFONICA|\bCLARO\b|\bVIVO\b|\bTIM\b|LOCALIZA|MOVIDA|UNIDAS|HOTEL|ENERGIA|COMPANHIA|PETROBRAS|POSTO|IPIRANGA|SHELL", re.I)
    forn_ano = defaultdict(list)  # (pid, ano) -> [(fornecedor, total, documento)] so pessoas juridicas
    try:
        for r_ in ler(a.resumo, "top_fornecedores_ano"):
            forn_ano[(int(r_["pessoa_id"]), int(r_["ano"]))].append((r_["fornecedor"], f(r_["total"]), re.sub(r"\D", "", r_.get("cnpj_cpf") or "")))
    except FileNotFoundError:
        pass
    at_obras = []
    try:
        for doc_, r_ in rec.items():
            dg_ = re.sub(r"\D", "", doc_).zfill(14)
            if dg_ in BANCOS:
                continue
            for o_ in obras_cnpj.get(dg_, []):
                if o_[2] == "Paralisada":
                    at_obras.append([o_[1], r_["n"], r_["l"], o_[3], o_[4], o_[5], re.sub(r"\D", "", doc_)])
        at_obras = sorted(at_obras, key=lambda t: -t[4])[:40]
    except NameError:
        pass

    def visao_atencao(ano_f):
        """Pontos de atencao num ano (None = todos os anos). Ano de pagamento nas emendas e do gasto na cota; do pagamento da prefeitura no TCE."""
        v_ = dict(ano=str(ano_f or ""), recebedores=[], fornecedores=[], sancionados=[], dispensas=[])
        try:
            v_["recebedores"] = [t for t in rank_json.get(str(ano_f or ""), {}).get("q", []) if re.sub(r"\D", "", t[1]).zfill(14) not in BANCOS][:30]
            for doc_, r_ in rec.items():
                dg_ = re.sub(r"\D", "", doc_).zfill(14)
                if not sanc.get(dg_) or dg_ in BANCOS:
                    continue
                tot_, ps_ = 0, set()
                for pid_, q_ in r_["p"].items():
                    for e_ in q_[2]:
                        if ano_f and e_[4] != ano_f:
                            continue
                        tot_ += e_[3]; ps_.add(pid_)
                if ps_:
                    v_["sancionados"].append([r_["n"], re.sub(r"\D", "", doc_), classificar(r_["n"], doc_), round(tot_), len(ps_), sanc[dg_][0]])
            v_["sancionados"] = sorted(v_["sancionados"], key=lambda t: -t[3])[:40]
            agg_ = {}
            for sl_, anos_ in tcf.items():
                for a_, lst_ in anos_.items():
                    if ano_f and a_ != str(ano_f):
                        continue
                    for doc_, nome_, cl_, pago_, fed_, disp_, n_ in lst_:
                        z_ = agg_.setdefault((sl_, doc_), [nome_, 0, 0, 0])
                        z_[1] += pago_; z_[2] += disp_; z_[3] += n_
            minimo_ = 1000000 if not ano_f else 500000
            v_["dispensas"] = sorted(([muni.get(sl_, {}).get("n", sl_), z_[0], doc_, z_[1], z_[2] / z_[1] * 100, z_[3]] for (sl_, doc_), z_ in agg_.items()
                                      if z_[1] >= minimo_ and z_[2] / z_[1] >= 0.8), key=lambda t: -t[3])[:30]
        except NameError:
            pass
        for x in lista:
            if x["cargo"] == "presidente":
                continue
            if ano_f:
                tot_ = x["anos"].get(ano_f, 0)
                cand_ = forn_ano.get((x["id"], ano_f), [])
                minimo_ = 100000
            else:
                tot_ = sum(x["anos"].values())
                cand_ = sorted(forn_doc.get(x["id"], []), key=lambda t: -t[1])[:3]
                minimo_ = 200000
            if tot_ < minimo_:
                continue
            for nome_, vf_, doc_ in sorted(cand_, key=lambda t: -t[1])[:3]:
                if len(doc_) == 14 and vf_ / tot_ >= 0.25 and not NORMAL.search(sem_acento(nome_)):
                    v_["fornecedores"].append([x["nome"], x["url"], x["uf"] or "", x["partido"] or "", nome_, doc_, round(vf_), vf_ / tot_])
                    break
        v_["fornecedores"] = sorted(v_["fornecedores"], key=lambda t: -t[6])[:40]
        return v_
    anos_at = sorted({y_ for x in lista for y_ in x["anos"] if y_ >= 2015} | {a_ for a_ in locals().get("anos_pag", set()) if a_ and a_ >= 2015}, reverse=True)
    visoes_at = [visao_atencao(None)] + [visao_atencao(y_) for y_ in anos_at]
    escrever("atencao", env.get_template("atencao.html").render(**{**ctx_base, "raiz": "../"}, titulo="Pontos de atenção",
             descricao="Padrões nos dados públicos que valem uma pergunta ao responsável. Não indicam irregularidade.",
             obras=at_obras, visoes=visoes_at, anos_at=anos_at))

    # ---- novidades: compara com a atualizacao anterior ----
    snap = dict(data=atualizado, ano=ano_atual,
                pessoas={str(x["id"]): [round(sum(anos[x["id"]].get(ano_atual, {}).values())),
                                        round(sum(e[2] for e in emendas.get(x["id"], {}).values()))] for x in lista},
                n_emendas=len(edet), n_recebedores=len(rec) if (detalhe and favs) else 0,
                pago_emendas=round(sum(e[2] for pe in emendas.values() for e in pe.values())))
    (saida / "data" / "snapshot.json").write_text(json.dumps(snap, separators=(",", ":")), encoding="utf-8")
    ant = None
    if a.anterior and Path(a.anterior).exists():
        try:
            ant = json.loads(Path(a.anterior).read_text(encoding="utf-8"))
        except ValueError:
            ant = None
    mov_gasto, mov_emenda = [], []
    if ant:
        for x in lista:
            novo = snap["pessoas"][str(x["id"])]; velho = ant.get("pessoas", {}).get(str(x["id"]), [0, 0])
            if ant.get("ano") == snap["ano"] and novo[0] - velho[0] > 0 and x["cargo"] != "presidente":
                mov_gasto.append((x, novo[0] - velho[0]))
            if novo[1] - velho[1] > 0:
                mov_emenda.append((x, novo[1] - velho[1]))
        mov_gasto = sorted(mov_gasto, key=lambda t: -t[1])[:15]
        mov_emenda = sorted(mov_emenda, key=lambda t: -t[1])[:15]
    escrever("novidades", env.get_template("novidades.html").render(**{**ctx_base, "raiz": "../"}, titulo="O que mudou desde a última atualização",
             descricao="Novidades de cada atualização mensal: quem mais gastou e quem mais teve emendas pagas desde a atualização anterior.",
             snap=snap, ant=ant, ant_data=data_br((ant or {}).get('data')), mov_gasto=mov_gasto, mov_emenda=mov_emenda,
             d_emendas=snap["n_emendas"] - (ant or {}).get("n_emendas", 0), d_receb=snap["n_recebedores"] - (ant or {}).get("n_recebedores", 0),
             d_pago=snap["pago_emendas"] - (ant or {}).get("pago_emendas", 0)))


    # ---- paginas de estado (filtro por ano feito no navegador) ----
    ufs_por_nome = {sem_acento(n).upper(): s_ for s_, n in UFS.items()}
    area_uf = defaultdict(lambda: defaultdict(lambda: dict(pago=0.0, emp=0.0, cods=set(), vagos=0.0, mun=defaultdict(float))))  # (uf) -> (ano|"", area)
    for r in edet:
        sig = ufs_por_nome.get(sem_acento(r.get("uf") or "").upper())
        if not sig:
            continue
        mun_ = nome_bonito(r.get("municipio") or "")
        vago_ = sem_acento(mun_).lower() in ("multiplo", "sem informacao", "")
        for chave_ano in (str(int(f(r["ano"]))), ""):
            a_ = area_uf[sig][(chave_ano, r.get("funcao") or "Área não informada")]
            a_["pago"] += f(r["pago"]); a_["emp"] += f(r["empenhado"]); a_["cods"].add(r.get("codigo"))
            if vago_:
                a_["vagos"] += f(r["pago"])
            else:
                a_["mun"][mun_] += f(r["pago"])
    for sig, nome_uf in UFS.items():
        pes = [x for x in lista if x["uf"] == sig and x["cargo"] in ("deputado_federal", "senador")]
        pessoas_js = [[x["nome"], x["url"], x["partido"] or "", "d" if x["cargo"] == "deputado_federal" else "s",
                       {str(a_): round(v_) for a_, v_ in x["anos"].items()},
                       {str(a_): round(e_[2]) for a_, e_ in emendas.get(x["id"], {}).items()}] for x in pes]
        areas_js = {}
        for (ano_k, area_k), v in area_uf.get(sig, {}).items():
            if v["pago"] > 0:
                areas_js.setdefault(ano_k, []).append([area_k, round(v["pago"]), round(v["emp"]), len(v["cods"]),
                                                       [[m_, round(p_)] for m_, p_ in sorted(v["mun"].items(), key=lambda t: -t[1])[:8]], round(v["vagos"])])
        for lst_ in areas_js.values():
            lst_.sort(key=lambda t: -t[1])
        anos_uf = sorted({int(a_) for t in pessoas_js for a_ in list(t[4]) + list(t[5])} | {int(k) for k in areas_js if k}, reverse=True)
        escrever(f"estado/{sig.lower()}", env.get_template("estado.html").render(
            **{**ctx_base, "raiz": "../../"}, titulo=f"{nome_uf}: gastos da bancada e emendas recebidas", sig=sig, nome_uf=nome_uf,
            dados_json=json.dumps(dict(p=pessoas_js, a=areas_js), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"), anos_uf=anos_uf,
            descricao=f"Deputados e senadores de {nome_uf}: quanto gastaram e quanto o estado recebeu em emendas, por área e por ano."))
    escrever("glossario", env.get_template("glossario.html").render(**{**ctx_base, "raiz": "../"}, titulo="Glossário",
             descricao="O que significam empenhado, liquidado, pago, restos a pagar, emenda Pix, convênio, cota parlamentar e outros termos."))
    if base_url:
        (saida / "feed.xml").write_text('''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Gastos Públicos: atualizações</title><link>{b}/</link>
<description>Aviso de cada atualização mensal dos dados de gastos de parlamentares e da Presidência.</description><language>pt-BR</language>
<item><title>Atualização de {d}</title><link>{b}/novidades/</link><guid isPermaLink="false">atualizacao-{iso}</guid>
<description>Dados atualizados em {d}. Veja o que mudou desde a atualização anterior.</description></item>
</channel></rss>
'''.format(b=base_url, d=atualizado_txt, iso=atualizado), encoding="utf-8")

    resumo_home = {}
    for cargo in CARGOS:
        xs = [x for x in lista if x["cargo"] == cargo]
        resumo_home[cargo] = dict(n=len(xs), total_ref=sum(x["anos"].get(ano_ref, 0) for x in xs), cod=CARGOS[cargo][0],
                                  rotulo=CARGOS[cargo][2])
    escrever("index.html", env.get_template("home.html").render(**ctx_base, titulo="Gastos dos parlamentares e da Presidência",
             resumo=resumo_home, descricao="Quanto deputados federais, senadores e a Presidência da República gastaram desde 2014, com o quê e com quem. Busque e compare.",
             presidentes=[x for x in lista if x["cargo"] == "presidente"], ufs=sorted(UFS.items(), key=lambda t: t[1])))
    escrever("presidentes", env.get_template("presidentes.html").render(**{**ctx_base, "raiz": "../"}, titulo="Presidentes: gasto no mandato inteiro",
             descricao="Despesas da Presidência (cartão corporativo e viagens) em cada mandato, em valor total e por mês, para comparar presidentes.",
             presidentes=sorted(pres_resumo, key=lambda r: r["ini"])))
    # ---- partidos: bancada (dados da Camara e do Senado) + dinheiro do partido (TSE) ----
    def lerc(nome_):
        try:
            return ler(a.resumo, nome_)
        except FileNotFoundError:
            return []
    RE_FP, RE_FEFC = re.compile(r"fundo partid"), re.compile(r"fundo especial|fefc")
    RE_PESSOAL = re.compile(r"pessoal|salari|folha|remunerac|encargos (trabalh|social)|ferias|13o|rescis")
    norm_ = lambda t_: sem_acento(t_ or "").lower()
    tse = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: dict(rec=[], des=[], rcb=[]))))  # chave -> ano -> base -> listas
    for r_ in lerc("partido_receita"):
        tse[r_["sigla"]][int(r_["ano"])][r_["base"]]["rec"].append([r_["fonte"], round(f(r_["valor"])), int(f(r_["n"]))])
    for r_ in lerc("partido_despesa"):
        tse[r_["sigla"]][int(r_["ano"])][r_["base"]]["des"].append([r_["categoria"], round(f(r_["valor"])), int(f(r_["n"]))])
    for r_ in lerc("partido_recebedor"):
        tse[r_["sigla"]][int(r_["ano"])][r_["base"]]["rcb"].append([r_["nome"], r_["documento"], r_["classe"], round(f(r_["valor"])), int(f(r_["n"]))])
    cand_t = defaultdict(lambda: defaultdict(list))
    for r_ in lerc("partido_candidato"):
        cand_t[r_["sigla"]][int(r_["ano"])].append([r_["candidato"], r_["cargo"], r_["uf"], round(f(r_["fefc"])), round(f(r_["total"]))])
    parl_part, rot_part = defaultdict(list), {}
    for x_ in lista:
        if x_["cargo"] in ("deputado_federal", "senador") and x_["partido"] and (x_["anos"].get(ano_atual) or x_["anos"].get(ano_ref)):
            k_ = chave_partido(x_["partido"])
            parl_part[k_].append(x_)
            rot_part.setdefault(k_, x_["partido"])
    chaves_ = sorted(set(parl_part) | set(tse))
    for k_ in chaves_:
        rot_part.setdefault(k_, k_)
    slug_part, usados_p = {}, set()
    for k_ in chaves_:
        sl_ = slugify(rot_part[k_]) or k_.lower()
        slug_part[k_] = sl_ if sl_ not in usados_p else f"{sl_}-{k_.lower()}"
        usados_p.add(slug_part[k_])
    mediana_ = lambda v_: (sorted(v_)[len(v_) // 2] if len(v_) % 2 else (sorted(v_)[len(v_) // 2 - 1] + sorted(v_)[len(v_) // 2]) / 2) if v_ else None

    def soma_fonte(lst_, rx_):
        return sum(v_ for fo_, v_, _ in lst_ if rx_.search(norm_(fo_)))
    anos_part = sorted({y_ for k_ in chaves_ for y_ in tse[k_]} | {y_ for k_ in parl_part for x_ in parl_part[k_] for y_ in x_["anos"] if y_ >= 2014}, reverse=True)
    idx_part = {str(y_): [] for y_ in anos_part}
    for k_ in chaves_:
        for y_ in anos_part:
            ps_ = [x_ for x_ in parl_part.get(k_, []) if x_["anos"].get(y_)]
            cotas_ = [x_["anos"][y_] for x_ in ps_]
            em_ = sum(emendas[x_["id"]][y_][2] for x_ in ps_ if y_ in emendas.get(x_["id"], {}))
            T_ = tse.get(k_, {}).get(y_, {})
            fp_ = soma_fonte(T_.get("anual", {}).get("rec", []), RE_FP) or None
            fefc_ = soma_fonte(T_.get("campanha_orgao", {}).get("rec", []), RE_FEFC) or None
            ra_ = sum(v_ for _, v_, _ in T_.get("anual", {}).get("rec", [])) or None
            pe_ = sum(v_ for ct_, v_, _ in T_.get("anual", {}).get("des", []) if RE_PESSOAL.search(norm_(ct_))) or None
            if not ps_ and not (fp_ or fefc_ or ra_ or pe_):
                continue
            idx_part[str(y_)].append([slug_part[k_], rot_part[k_], sum(1 for x_ in ps_ if x_["cargo"] == "deputado_federal"), sum(1 for x_ in ps_ if x_["cargo"] == "senador"),
                                      round(mediana_(cotas_)) if cotas_ else None, round(em_) if em_ else None, round(fp_) if fp_ else None, round(fefc_) if fefc_ else None,
                                      round(ra_) if ra_ else None, round(pe_) if pe_ else None])
    anos_part = [y_ for y_ in anos_part if idx_part[str(y_)]]
    (saida / "data").mkdir(parents=True, exist_ok=True)
    (saida / "data" / "partidos.json").write_text(json.dumps(dict(anos=anos_part, ref=ano_ref, linhas=idx_part), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tem_tse = bool(tse)
    escrever("partidos", env.get_template("partidos.html").render(**{**ctx_base, "raiz": "../"}, titulo="Partidos: bancada e dinheiro que passa por eles",
             descricao="Bancada, cota e emendas de cada partido e, com os dados do TSE, fundo partidário, fundo eleitoral, campanhas, quem recebeu e gastos com pessoal.", anos=anos_part, tem_tse=tem_tse, ref=ano_ref))
    for k_ in chaves_:
        sl_ = slug_part[k_]
        T_ = tse.get(k_, {})
        d_ = dict(anos={str(y_): {b_: dict(rec=sorted(v_["rec"], key=lambda t_: -t_[1])[:30], des=sorted(v_["des"], key=lambda t_: -t_[1])[:30],
                                          nrcb=sum(1 for t_ in v_["rcb"] if t_[2] == "PJ")) for b_, v_ in bs_.items()} for y_, bs_ in T_.items()},
                  cand={str(y_): sorted(v_, key=lambda t_: -t_[3])[:40] for y_, v_ in cand_t.get(k_, {}).items()})
        for y_, bs_ in T_.items():
            for b_, v_ in bs_.items():
                pj_ = sorted(([t_[0], t_[1], t_[3], t_[4]] for t_ in v_["rcb"] if t_[2] == "PJ"), key=lambda t_: -t_[2])
                pf_ = [sum(t_[3] for t_ in v_["rcb"] if t_[2] == "PF"), sum(t_[4] for t_ in v_["rcb"] if t_[2] == "PF")]
                if pj_ or pf_[0]:
                    (saida / "data" / f"partido-{sl_}").mkdir(parents=True, exist_ok=True)
                    (saida / "data" / f"partido-{sl_}" / f"{y_}-{b_}.json").write_text(json.dumps(dict(r=pj_, pf=pf_), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        if T_:
            (saida / "data" / f"partido-{sl_}.json").write_text(json.dumps(d_, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        ps_ = sorted(parl_part.get(k_, []), key=lambda x_: x_["nome"])
        linhas_p = [dict(nome=x_["nome"], url=x_["url"], cod=x_["cod"], uf=x_["uf"] or "", cota=x_["anos"].get(ano_ref, 0), em=sum(e_[2] for e_ in emendas.get(x_["id"], {}).values())) for x_ in ps_]
        cotas_ = [l_["cota"] for l_ in linhas_p if l_["cota"]]
        escrever(f"partido/{sl_}", env.get_template("partido.html").render(**{**ctx_base, "raiz": "../../"}, titulo=f"{rot_part[k_]}: bancada e dinheiro do partido",
                 descricao=f"Parlamentares do {rot_part[k_]} e dinheiro que passa pelo partido: fundos, campanhas, quem recebeu e gastos com pessoal.",
                 nome=rot_part[k_], slug=sl_, linhas=linhas_p, n_dep=sum(1 for l_ in linhas_p if l_["cod"] == "deputado"), n_sen=sum(1 for l_ in linhas_p if l_["cod"] == "senador"),
                 cota_med=mediana_(cotas_), em_tot=sum(l_["em"] for l_ in linhas_p), tem_tse=bool(T_), ref=ano_ref))
    partidos_urls = ["partidos/"] + [f"partido/{slug_part[k_]}/" for k_ in chaves_]

    escrever("comparar", env.get_template("comparar.html").render(**{**ctx_base, "raiz": "../"}, titulo="Comparar gastos",
             descricao="Compare lado a lado os gastos de parlamentares e presidentes, ano a ano e por tipo de despesa."))
    escrever("sobre", env.get_template("sobre.html").render(**{**ctx_base, "raiz": "../"}, titulo="De onde vêm os dados e o que cada gasto cobre",
             descricao="Fontes, método e limites dos números: o que a cota parlamentar cobre e o que não está nos totais."))
    escrever("404.html", env.get_template("404.html").render(**ctx_base, titulo="Página não encontrada"))

    urls = ["", "glossario/", "comparar/", "presidentes/", "emendas-pix/", "municipios/", "recebedores/", "novidades/", "sem-autor/", "atencao/", "ministerios/", "pares/", "privados/", "partidos/", "sobre/"] + partidos_urls + [f"estado/{s_.lower()}/" for s_ in UFS] + [x["url"] for x in lista]
    (saida / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n" if base_url else "User-agent: *\nAllow: /\n")
    if base_url:
        (saida / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"<url><loc>{base_url}/{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    print(f"Site gerado em {saida}: {len(lista)} paginas de pessoas; atualizado {atualizado_txt}")


if __name__ == "__main__":
    main()
