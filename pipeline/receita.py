"""Cadastro de CNPJ da Receita Federal (dados abertos): socios e enderecos das empresas pagas com a cota parlamentar,
e as outras empresas que tem o mesmo socio ou o mesmo endereco.

Sao dados publicos e comuns de se repetirem (contador, familia, predio comercial). Ter socio ou endereco em comum nao
indica irregularidade; o site so mostra o fato cadastral. Socio pessoa fisica e ligado por nome + digitos centrais do CPF
(a Receita publica o CPF mascarado), entao homonimos raros podem se misturar: a tela avisa.

Arquivos usados (mensais, ~8 GB): Socios0-9, Estabelecimentos0-9, Empresas0-9 e Municipios. Os zips sao lidos em
fluxo e apagados no fim. Passos: 1) socios das empresas pagas; 2) outras empresas desses socios; 3) enderecos das
empresas pagas; 4) outras empresas nesses enderecos; 5) razao social de todas as envolvidas."""
import csv
import io
import os
import re
import sys
import zipfile
from collections import defaultdict
from datetime import date

import requests

from . import common as c

TOKEN = "YggdBLfdninEJX9"  # compartilhamento publico (Nextcloud) dos dados abertos de CNPJ
MODELOS = [  # (modelo do endereco, autenticacao basica ou None)
    ("https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/{mes}/{arq}", None),
    ("https://arquivos.receitafederal.gov.br/public.php/webdav/{mes}/{arq}", (TOKEN, "")),
    ("https://arquivos.receitafederal.gov.br/index.php/s/" + TOKEN + "/download?path=%2F{mes}&files={arq}", None),
    ("https://dadosabertos.rfb.gov.br/CNPJ/dados_abertos_cnpj/{mes}/{arq}", None),
]
CABECALHO = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
             "Accept": "application/zip,application/octet-stream,*/*", "Accept-Language": "pt-BR,pt;q=0.9"}
MESES_ATRAS = 6
MIN_TOTAL = 30000      # so empresas que receberam ao menos isso (somando todos os parlamentares)
MAX_REL_SOCIO = 40     # outras empresas listadas por socio
MAX_REL_END = 25       # outras empresas listadas por endereco
QUALIFICACAO = {
    "05": "Administrador", "08": "Conselheiro de administração", "10": "Diretor", "16": "Presidente", "17": "Procurador",
    "22": "Sócio", "28": "Sócio-gerente", "31": "Sócio ostensivo", "34": "Tesoureiro", "47": "Sócio pessoa física",
    "48": "Sócio pessoa jurídica", "49": "Sócio-administrador", "52": "Sócio com capital", "53": "Sócio sem capital",
    "54": "Fundador", "65": "Titular pessoa física", "78": "Titular pessoa jurídica",
}
csv.field_size_limit(1 << 24)


def _dig(s):
    return re.sub(r"\D", "", s or "")


def _mes(hoje, k):
    a, m = hoje.year, hoje.month - k
    while m <= 0:
        m += 12
        a -= 1
    return f"{a}-{m:02d}"


def _existe(url, auth=None, relatar=False):
    try:
        r = requests.get(url, stream=True, timeout=60, headers=CABECALHO, auth=auth)
        tipo = r.headers.get("content-type", "")
        ok = r.status_code in (200, 206) and "text/html" not in tipo
        if relatar:
            print(f"    {r.status_code} {tipo[:40]} {url[:110]}", file=sys.stderr)
        r.close()
        return ok
    except requests.RequestException as e:
        if relatar:
            print(f"    erro {type(e).__name__}: {str(e)[:120]} {url[:110]}", file=sys.stderr)
        return False


def descobrir(modelos=None, hoje=None):
    """Acha o modelo de endereco e o mes mais recente publicado. Devolve ((modelo, auth), mes)."""
    hoje = hoje or date.today()
    for modelo, auth in modelos or MODELOS:
        for k in range(MESES_ATRAS):
            mes = _mes(hoje, k)
            if _existe(modelo.format(mes=mes, arq="Socios0.zip"), auth, relatar=(k < 2)):
                return (modelo, auth), mes
    return None, None


def _baixar(url, destino, auth=None):
    for t in range(3):
        try:
            with requests.get(url, stream=True, timeout=(30, 300), headers=CABECALHO, auth=auth) as r:
                r.raise_for_status()
                with open(destino, "wb") as f:
                    for pedaco in r.iter_content(1 << 20):
                        f.write(pedaco)
            return True
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return False
            print(f"  nova tentativa {t + 1} ({e})", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  nova tentativa {t + 1} ({e})", file=sys.stderr)
    return False


def baixar_tudo(pasta, fonte, mes):
    modelo, auth = fonte
    os.makedirs(pasta, exist_ok=True)
    for tipo in ("Socios", "Estabelecimentos", "Empresas"):
        n = 0
        for i in range(10):
            dest = os.path.join(pasta, f"{tipo}{i}.zip")
            if not os.path.exists(dest) and not _baixar(modelo.format(mes=mes, arq=f"{tipo}{i}.zip"), dest, auth):
                if os.path.exists(dest):
                    os.remove(dest)
                break
            n += 1
        print(f"  {tipo}: {n} arquivos")
    dest = os.path.join(pasta, "Municipios.zip")
    if not os.path.exists(dest):
        _baixar(modelo.format(mes=mes, arq="Municipios.zip"), dest, auth)


def _zips(pasta, tipo):
    return sorted(os.path.join(pasta, f) for f in os.listdir(pasta) if re.fullmatch(rf"{tipo}\d*\.zip", f))


def _linhas(caminho):
    with zipfile.ZipFile(caminho) as z:
        nome = z.namelist()[0]
        with z.open(nome) as f:
            yield from csv.reader(io.TextIOWrapper(f, encoding="latin-1", newline=""), delimiter=";", quotechar='"')


def _todas(pasta, tipo):
    for caminho in _zips(pasta, tipo):
        yield from _linhas(caminho)


def chave_socio(tipo, nome, doc):
    """Chave para ligar o mesmo socio em empresas diferentes. None se nao der para ligar com seguranca."""
    d = _dig(doc)
    if tipo == "1":
        return "pj:" + d[:8] if len(d) >= 8 and set(d[:8]) != {"0"} else None
    if tipo == "2":
        meio = d if len(d) == 6 else d[3:9] if len(d) == 11 else ""
        n = c.sem_acento(nome)
        if len(meio) == 6 and set(meio) != {"0"} and len(n.split()) >= 2:
            return f"pf:{meio}:{n}"
    return None


def chave_end(cep, numero, logradouro):
    num = re.sub(r"[^0-9A-Z]", "", (numero or "").upper())
    cep = _dig(cep)
    if len(cep) != 8 or not num or num in ("SN", "0", "00", "000"):
        return None
    return f"{cep}|{num}|{c.sem_acento(logradouro)}"


def alvos_do_banco(con, minimo=MIN_TOTAL):
    """cnpj basico (8) -> conjunto de CNPJs completos pagos com a cota."""
    alvos = defaultdict(set)
    q = """SELECT d, SUM(valor) FROM (SELECT valor, REPLACE(REPLACE(REPLACE(COALESCE(cnpj_cpf,''),'.',''),'/',''),'-','') d
           FROM gasto WHERE fonte NOT LIKE 'pres%') WHERE LENGTH(d)=14 GROUP BY d HAVING SUM(valor)>=?"""
    for d, _t in con.execute(q, (minimo,)):
        alvos[d[:8]].add(d)
    return alvos


def processar(con, pasta, alvos):
    # 1) socios das empresas pagas
    socios = defaultdict(list)       # cnpj8 -> [(tipo, nome, doc, qual, entrada, chave)]
    nomes_pf, pj_chaves, chaves = set(), set(), set()
    for l in _todas(pasta, "Socios"):
        if len(l) < 6:
            continue
        b = _dig(l[0])[:8]
        if b in alvos:
            k = chave_socio(l[1], l[2], l[3])
            socios[b].append((l[1], l[2], l[3], l[4], l[5], k))
            if k:
                chaves.add(k)
                (nomes_pf if k.startswith("pf:") else pj_chaves).add(l[2] if k.startswith("pf:") else k[3:])
    print(f"  Socios das empresas pagas: {sum(len(v) for v in socios.values())} registros, {len(chaves)} socios ligaveis")
    # 2) outras empresas dos mesmos socios
    rel_cnt = defaultdict(int)
    rel_lista = defaultdict(list)    # chave -> [cnpj8]
    socios_rel = defaultdict(list)
    for l in _todas(pasta, "Socios"):
        if len(l) < 6:
            continue
        if l[2] not in nomes_pf and not (l[1] == "1" and _dig(l[3])[:8] in pj_chaves):
            continue
        k = chave_socio(l[1], l[2], l[3])
        if k not in chaves:
            continue
        b = _dig(l[0])[:8]
        rel_cnt[k] += 1
        if len(rel_lista[k]) < MAX_REL_SOCIO and b not in rel_lista[k]:
            rel_lista[k].append(b)
            if b not in alvos:
                socios_rel[b].append((l[1], l[2], l[3], l[4], l[5], k))
    rel_b = {b for v in rel_lista.values() for b in v}
    # 3) enderecos das empresas pagas (e matriz delas)
    estab = {}                       # cnpj14 -> tupla
    end_alvos = defaultdict(set)     # chave_end -> {cnpj8}
    cepnum = set()

    def linha_estab(l):
        return (l[0] + l[1] + l[2], l[0], 1 if l[3] == "1" else 0, l[4], l[5], l[10], l[11],
                (l[13] + " " + l[14]).strip(), l[15], l[16], l[17], l[18], l[19], l[20])
    for l in _todas(pasta, "Estabelecimentos"):
        if len(l) < 21:
            continue
        b = l[0]
        if b in alvos and (l[3] == "1" or (l[0] + l[1] + l[2]) in alvos[b]):
            t = linha_estab(l)
            estab[t[0]] = t
            k = chave_end(t[11], t[8], t[7])
            if k:
                end_alvos[k].add(b)
                cepnum.add((_dig(t[11]), re.sub(r"[^0-9A-Z]", "", t[8].upper())))
    print(f"  Estabelecimentos das empresas pagas: {len(estab)}; enderecos ligaveis: {len(end_alvos)}")
    # 4) matriz das empresas de socio em comum + outras empresas nos mesmos enderecos
    end_cnt = defaultdict(int)
    end_lista = defaultdict(list)    # chave_end -> [cnpj14]
    for l in _todas(pasta, "Estabelecimentos"):
        if len(l) < 21:
            continue
        b = l[0]
        if b in rel_b and l[3] == "1" and (b + l[1] + l[2]) not in estab:
            t = linha_estab(l)
            estab[t[0]] = t
        num = re.sub(r"[^0-9A-Z]", "", l[15].upper())
        if (l[18], num) in cepnum and l[5] == "02":
            k = chave_end(l[18], l[15], (l[13] + " " + l[14]).strip())
            if k in end_alvos and b not in end_alvos[k]:
                end_cnt[k] += 1
                t = linha_estab(l)
                if len(end_lista[k]) < MAX_REL_END:
                    end_lista[k].append(t[0])
                    estab[t[0]] = t
    # 5) razao social
    precisa = set(alvos) | rel_b | {e[1] for e in estab.values()}
    empresas = {}
    for l in _todas(pasta, "Empresas"):
        if len(l) >= 6 and l[0] in precisa:
            empresas[l[0]] = (l[1], l[2], l[4], l[5])
    municipios = {}
    mz = os.path.join(pasta, "Municipios.zip")
    if os.path.exists(mz):
        municipios = {l[0]: l[1] for l in _linhas(mz) if len(l) >= 2}
    return dict(alvos=alvos, socios=socios, socios_rel=socios_rel, rel_cnt=rel_cnt, rel_lista=rel_lista, estab=estab,
                end_alvos=end_alvos, end_cnt=end_cnt, end_lista=end_lista, empresas=empresas, municipios=municipios)


def gravar(con, r):
    for t in ("rf_empresa", "rf_estab", "rf_socio", "rf_relacao"):
        con.execute(f"DELETE FROM {t}")
    emp = r["empresas"]
    con.executemany("INSERT OR REPLACE INTO rf_empresa VALUES (?,?,?,?,?,?)",
                    [(b, e[0], e[1], e[2], e[3], 1 if b in r["alvos"] else 0) for b, e in emp.items()])
    con.executemany("INSERT OR REPLACE INTO rf_estab VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8], t[9], t[10], _dig(t[11]), t[12],
                      r["municipios"].get(t[13], t[13]), chave_end(t[11], t[8], t[7])) for t in r["estab"].values()])
    linhas = []
    for src in (r["socios"], r["socios_rel"]):
        for b, lst in src.items():
            for tipo, nome, doc, qual, entrada, k in lst:
                linhas.append((b, tipo, nome, doc, QUALIFICACAO.get(qual.zfill(2), f"Qualificação {qual}"), entrada, k))
    con.executemany("INSERT INTO rf_socio VALUES (?,?,?,?,?,?,?)", linhas)
    rel = []
    for b, lst in r["socios"].items():
        for tipo, nome, doc, qual, entrada, k in lst:
            if k:
                for o in r["rel_lista"].get(k, []):
                    if o != b:
                        rel.append((b, "socio", k, o, None, r["rel_cnt"][k]))
    for k, alvos_b in r["end_alvos"].items():
        for o in r["end_lista"].get(k, []):
            for b in alvos_b:
                rel.append((b, "end", k, r["estab"][o][1], o, r["end_cnt"][k]))
    con.executemany("INSERT INTO rf_relacao VALUES (?,?,?,?,?,?)", rel)
    c.log(con, "receita", "cnpj_socios_enderecos", None, len(r["alvos"]))
    con.commit()
    return len(r["alvos"]), len(rel)


def rodar(con, pasta="data/rfb", url_modelo=None, minimo=MIN_TOTAL, baixar=True, apagar=True):
    alvos = alvos_do_banco(con, minimo)
    if not alvos:
        print("  AVISO: sem fornecedores com CNPJ no banco; rode antes a coleta da Camara e do Senado", file=sys.stderr)
        return 0
    print(f"  Receita: {len(alvos)} empresas pagas a procurar")
    if baixar:
        fonte, mes = descobrir([(url_modelo, None)] if url_modelo else None)
        if not fonte:
            print("  AVISO: nao achei os arquivos de CNPJ da Receita. Informe o endereco no campo 'rfb_url' do workflow "
                  "(com {mes} e {arq}).", file=sys.stderr)
            return 0
        print(f"  Receita: usando {mes} ({fonte[0].split('{')[0]}...)")
        baixar_tudo(pasta, fonte, mes)
    if not _zips(pasta, "Socios") or not _zips(pasta, "Estabelecimentos") or not _zips(pasta, "Empresas"):
        print("  AVISO: faltam arquivos da Receita em " + pasta, file=sys.stderr)
        return 0
    r = processar(con, pasta, alvos)
    n, nrel = gravar(con, r)
    print(f"Receita: {n} empresas com cadastro, {nrel} relacoes (socio/endereco)")
    if apagar and baixar:
        for f in os.listdir(pasta):
            if f.endswith(".zip"):
                os.remove(os.path.join(pasta, f))
    return n
