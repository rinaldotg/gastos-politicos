"""Gera o site estatico a partir dos CSVs do resumo (pipeline.verificar).

Uso: python site/build.py --resumo resumo --saida dist [--base-url https://rinaldotg.github.io/gastos-politicos]
"""
import argparse
import csv
import json
import re
import shutil
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

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
    favs = {}  # codigo -> favorecidos somando todos os anos (maiores primeiro)
    for cod_, rows_ in favs_raw.items():
        ag_ = {}
        for nome_, doc_, tipo_, loc_, valor_, ano_ in rows_:
            k_ = (doc_, nome_) if doc_ else ("", nome_)
            if k_ in ag_:
                ag_[k_][4] += valor_
            else:
                ag_[k_] = [nome_, doc_, tipo_, loc_, valor_]
        favs[cod_] = sorted(ag_.values(), key=lambda t: -t[4])
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

    (saida / "data" / "p").mkdir(parents=True)
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
        if orc_x:
            mx = max(o["total"] for o in orc_x) or 1
            for o in orc_x:
                o["largura"] = max(0, o["total"]) / mx * 100
        html = env.get_template("pessoa.html").render(
            **{**ctx_base, "raiz": "../../"}, titulo=f"{x['nome']}: gastos desde 2014", p=x, cargo_rotulo=CARGOS[x["cargo"]][1],
            linhas_ano=linhas_ano, total_geral=total_geral, fornecedores=forn_x, emendas=em, em_tot=em_tot, em_exec=em_exec, custo=CUSTO_MANDATO.get(x["cargo"]), ano_ref_cota=x["anos"].get(ano_ref, 0),
            em_pix=emendas_tipo[pid].get("pix", 0), em_def=emendas_tipo[pid].get("def", 0),
            em_funcao=[t for t in sorted(em_funcao[pid].items(), key=lambda t: -t[1]) if t[1] > 0][:6], sig=sig, orc=orc_x,
            uf_url=(f"estado/{x['uf'].lower()}/" if x["uf"] in UFS else ""), pos=posicao.get(pid) if x["cargo"] != "presidente" else None, tem_detalhe=bool(detalhe.get(pid)), desde=(min(anos[pid]) if anos[pid] else 2014), em_desde=(min(emendas[pid]) if emendas.get(pid) else 2014), ano_ref_total=x["anos"].get(ano_ref, 0), descricao=(
                f"{CARGOS[x['cargo']][1]} {x['nome']}: {brl_curto(total_geral)} em gastos desde 2014, por ano e por tipo de despesa."))
        escrever(f"{x['cod']}/{x['slug']}", html)
        dados = dict(id=pid, n=x["nome"], c=x["cod"], u=x["uf"], p=x["partido"], url=x["url"],
                     anos={str(y): [round(sum(anos[pid][y].values()), 2), meses[pid].get(y, 0),
                                    [[c, round(v, 2)] for c, v in sorted(anos[pid][y].items(), key=lambda t: -t[1])]]
                           for y in anos_ord},
                     em={str(y): [round(v, 2) for v in e] for y, e in em})
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
                i = info.setdefault(l[3], dict(p=pid_, ano=l[0], pix=l[1], num=l[2], dest=[], fn=l[5], emp=0, pago=0))
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
                i=[i["p"], i["ano"], i["pix"], i["num"], ", ".join(i["dest"][:4]), i["fn"], round(i["emp"]), round(i["pago"])],
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
                q[2].append([cod, i["ano"], i["pix"], valor, ano_p])
        (saida / "data" / "fe").mkdir(parents=True, exist_ok=True)
        (saida / "data" / "fr").mkdir(parents=True, exist_ok=True)
        (saida / "data" / "m").mkdir(parents=True, exist_ok=True)
        for k, v in sh_e.items():
            gravar(f"fe/{k}.json", v)
        rank_ano = defaultdict(dict)  # ano ("" = todos) -> doc -> [nome, doc, valor, parlamentares]
        for doc, r_ in rec.items():
            dig = re.sub(r"\D", "", doc)
            sh_r[int(dig) % N_R if dig else 0][doc] = dict(
                b=1 if dig in BANCOS else 0, n=r_["n"], t=r_["t"], l=r_["l"], p=sorted(r_["p"].values(), key=lambda t: -t[1]))
            if dig in BANCOS:
                continue
            por_ano = defaultdict(lambda: [0, set()])
            tot_ = [0, set()]
            for pid_, q in r_["p"].items():
                for _, _, _, v_, ap_ in q[2]:
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
        indice_m = []
        for sl, m_ in muni.items():
            por_ano = defaultdict(lambda: [0, set()])
            for pid_, ys in m_["p"].items():
                for ap_, (v_, cs_) in ys.items():
                    por_ano[ap_][0] += v_; por_ano[ap_][1].add(pid_)
                    por_ano[0][0] += v_; por_ano[0][1].add(pid_)
            rs = sorted(m_["r"].items(), key=lambda t: -sum(t[1].values()))
            gravar(f"m/{sl}.json", dict(
                n=m_["n"],
                p=sorted([[pid_, {str(ap_): [round(v_), len(cs_)] for ap_, (v_, cs_) in ys.items()}] for pid_, ys in m_["p"].items()],
                         key=lambda t: -sum(v[0] for v in t[1].values())),
                r=[[k[1], k[0], {str(ap_): round(v_) for ap_, v_ in ys.items()}] for k, ys in rs[:1500]], nr=len(rs)))
            indice_m.append([m_["n"], sl, {str(ap_): [round(v_), len(ps_)] for ap_, (v_, ps_) in por_ano.items()}])
        gravar("municipios.json", sorted(indice_m, key=lambda t: -t[2].get("0", [0])[0]))
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


    # ---- paginas de estado ----
    ufs_por_nome = {sem_acento(n).upper(): s_ for s_, n in UFS.items()}
    area_uf = defaultdict(lambda: defaultdict(lambda: dict(pago=0.0, emp=0.0, cods=set(), vagos=0.0, mun=defaultdict(float))))
    for r in edet:
        sig = ufs_por_nome.get(sem_acento(r.get("uf") or "").upper())
        if not sig:
            continue
        a_ = area_uf[sig][r.get("funcao") or "Área não informada"]
        a_["pago"] += f(r["pago"]); a_["emp"] += f(r["empenhado"]); a_["cods"].add(r.get("codigo"))
        mun_ = nome_bonito(r.get("municipio") or "")
        if sem_acento(mun_).lower() in ("multiplo", "sem informacao", ""):
            a_["vagos"] = a_.get("vagos", 0.0) + f(r["pago"])  # varios municipios ou nao informado
        else:
            a_["mun"][mun_] += f(r["pago"])
    for sig, nome_uf in UFS.items():
        pes = [x for x in lista if x["uf"] == sig and x["cargo"] in ("deputado_federal", "senador")]
        def linha_(x):
            return dict(x=x, gasto=x["anos"].get(ano_ref, 0), em_pago=sum(e[2] for e in emendas.get(x["id"], {}).values()))
        deps = sorted([linha_(x) for x in pes if x["cargo"] == "deputado_federal"], key=lambda t: -t["gasto"])
        sens = sorted([linha_(x) for x in pes if x["cargo"] == "senador"], key=lambda t: -t["gasto"])
        areas = sorted([(n_, dict(pago=v["pago"], emp=v["emp"], n=len(v["cods"]), vagos=v["vagos"], mun=sorted(v["mun"].items(), key=lambda t: -t[1])[:8]))
                        for n_, v in area_uf.get(sig, {}).items() if v["pago"] > 0], key=lambda t: -t[1]["pago"])
        escrever(f"estado/{sig.lower()}", env.get_template("estado.html").render(
            **{**ctx_base, "raiz": "../../"}, titulo=f"{nome_uf}: gastos da bancada e emendas recebidas", sig=sig, nome_uf=nome_uf,
            deps=deps, sens=sens, areas=areas, total_areas=sum(a_[1]["pago"] for a_ in areas),
            descricao=f"Deputados e senadores de {nome_uf}: quanto gastaram e quanto o estado recebeu em emendas, por área."))
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
    escrever("comparar", env.get_template("comparar.html").render(**{**ctx_base, "raiz": "../"}, titulo="Comparar gastos",
             descricao="Compare lado a lado os gastos de parlamentares e presidentes, ano a ano e por tipo de despesa."))
    escrever("sobre", env.get_template("sobre.html").render(**{**ctx_base, "raiz": "../"}, titulo="De onde vêm os dados e o que cada gasto cobre",
             descricao="Fontes, método e limites dos números: o que a cota parlamentar cobre e o que não está nos totais."))
    escrever("404.html", env.get_template("404.html").render(**ctx_base, titulo="Página não encontrada"))

    urls = ["", "glossario/", "comparar/", "emendas-pix/", "municipios/", "recebedores/", "novidades/", "sem-autor/", "sobre/"] + [f"estado/{s_.lower()}/" for s_ in UFS] + [x["url"] for x in lista]
    (saida / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n" if base_url else "User-agent: *\nAllow: /\n")
    if base_url:
        (saida / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"<url><loc>{base_url}/{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    print(f"Site gerado em {saida}: {len(lista)} paginas de pessoas; atualizado {atualizado_txt}")


if __name__ == "__main__":
    main()
