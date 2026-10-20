"""Piloto Sao Paulo: despesa PAGA dos municipios paulistas (TCE-SP, Portal da Transparencia Municipal, dados Audesp).

Por municipio e ano o TCE-SP publica um ZIP com um CSV (latin-1, separador ';') com uma linha por evento da despesa
(empenhado, liquidado, pago, anulacao). Contamos so o evento "Valor Pago". O arquivo traz funcao, programa, acao,
fonte de recurso (ex.: "TRANSFERENCIAS E CONVENIOS FEDERAIS-VINCULADOS"), fornecedor e historico. NAO traz o codigo da
emenda federal: a ligacao com a emenda e por texto do historico ("repasse de emenda parlamentar") e por fonte federal.
A capital paulista e fiscalizada pelo TCM-SP e nao esta neste portal.
"""
import csv
import io
import re
import sys
import tempfile
import time
import zipfile
from datetime import datetime

from . import common as c
from .classe import classificar

BASE = "https://transparencia.tce.sp.gov.br/sites/default/files/csv/despesas-{slug}-{ano}.zip"
PAGINA = "https://transparencia.tce.sp.gov.br/municipio/{slug}"
RE_EMENDA = re.compile(r"EMENDAS? PARLAMENTAR|EMENDA (IMPOSITIVA|INDIVIDUAL|DE BANCADA|ESPECIAL|PIX)|TRANSFERENCIA ESPECIAL|EMENDAS? (DO|DA) (DEPUTAD|SENAD|VEREAD)")
ALIAS = {"embu": "embu-das-artes"}  # nome no Portal da Transparencia federal x nome no TCE-SP
LISTA = "https://transparencia.tce.sp.gov.br/api/json/municipios"
ANO_MIN = 2024
N_MUNICIPIOS = 150  # os de maior valor de emendas primeiro; o que nao couber no tempo entra na rodada seguinte
LIMITE_SEGUNDOS = 40 * 60
RETER = 300  # pagamentos de fonte federal guardados por municipio e ano (alem dos que citam emenda)


def slug(nome):
    return re.sub(r"[^a-z0-9]+", "-", c.sem_acento(nome)).strip("-")


def grupo_fonte(f):
    f = c.sem_acento(f).upper()
    if "FEDERA" in f:
        return "federal"
    if "ESTADUA" in f:
        return "estadual"
    if "TESOURO" in f or "PROPRIOS" in f:
        return "proprio"
    return "outras"


def valor(t):
    try:
        return float((t or "0").replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def modalidade(t):
    t = c.sem_acento(t).upper()
    if "DISPENSA" in t or "INEXIG" in t:
        return "dispensa"
    if any(x in t for x in ("PREGAO", "CONCORRENCIA", "TOMADA", "CONVITE", "LEILAO", "RDC")):
        return "licitacao"
    return "outros"


def agregar(texto_csv):
    """Devolve (por_funcao, pagamentos, linhas, fornecedores): agregados de 'Valor Pago'."""
    leitor = csv.DictReader(io.StringIO(texto_csv), delimiter=";")
    por_funcao, pag, n, forn = {}, {}, 0, {}
    for r in leitor:
        n += 1
        if "PAGO" not in c.sem_acento(r.get("tp_despesa")).upper():
            continue
        v = valor(r.get("vl_despesa"))
        if not v:
            continue
        fonte = grupo_fonte(r.get("ds_fonte_recurso"))
        funcao = (r.get("ds_funcao_governo") or "Não informada").strip()
        k = (funcao, fonte)
        a = por_funcao.setdefault(k, [0.0, 0])
        a[0] += v; a[1] += 1
        hist = (r.get("historico_despesa") or "").strip()
        emenda = 1 if RE_EMENDA.search(c.sem_acento(hist).upper()) else 0
        ident = r.get("identificador_despesa") or ""
        doc = re.sub(r"\D", "", ident.split("-")[-1]) if "CNPJ" in ident else ""
        nome = (r.get("ds_despesa") or "").strip()
        mod = modalidade(r.get("ds_modalidade_lic"))
        classe = classificar(nome, doc) if doc else "pf"
        if classe in ("empresa", "entidade"):
            fo = forn.setdefault((doc, nome, classe), [0.0, 0.0, 0.0, 0])
            fo[0] += v
            fo[1] += v if fonte == "federal" else 0
            fo[2] += v if mod == "dispensa" else 0
            fo[3] += 1
        if fonte == "federal" or emenda:
            kk = (doc, nome, funcao, fonte, emenda, hist[:220], mod)
            b = pag.setdefault(kk, [0.0, 0])
            b[0] += v; b[1] += 1
    return por_funcao, pag, n, forn


def _baixar(url):
    r = c.get(url, tentativas=2, timeout=240, stream=True)
    with tempfile.TemporaryFile() as tmp:
        for parte in r.iter_content(1 << 20):
            tmp.write(parte)
        tmp.seek(0)
        with zipfile.ZipFile(tmp) as z:
            nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            return c.decodificar(z.read(nome))


def _slug_tce(nome):
    """Slug do municipio no TCE-SP quando difere do nome informado nas emendas."""
    sl = slug(nome)
    if sl in ALIAS:
        return ALIAS[sl]
    try:
        j = c.get(LISTA, tentativas=2, timeout=60).json()
        nomes = []
        for x in (j if isinstance(j, list) else j.get("municipios", [])):
            nomes.append(x if isinstance(x, str) else next((v for v in x.values() if isinstance(v, str)), ""))
        cand = [n for n in nomes if slug(n) == sl or slug(n).startswith(sl + "-")]
        if len(cand) == 1:
            return slug(cand[0])
        print(f"  AVISO: {nome}: {len(cand)} candidatos no TCE-SP ({', '.join(cand[:4])}); ignorado", file=sys.stderr)
    except Exception as e:
        print(f"  AVISO: lista de municipios do TCE-SP indisponivel: {e}", file=sys.stderr)
    return None


def escolher_municipios(con, n=N_MUNICIPIOS):
    linhas = con.execute("""SELECT municipio, SUM(valor) v FROM emenda_favorecido
                            WHERE uf='SP' AND municipio IS NOT NULL AND municipio<>'' GROUP BY municipio ORDER BY v DESC""").fetchall()
    vagos = ("multiplo", "sem informacao", "sao paulo")  # capital: TCM-SP
    out = []
    for m, _ in linhas:
        if c.sem_acento(m) in vagos:
            continue
        out.append(m)
        if len(out) >= n:
            break
    return out


def salvar(con, sl, ano, nome, por_funcao, pag, n, forn=None):
    con.execute("DELETE FROM tce_funcao WHERE slug=? AND ano=?", (sl, ano))
    con.execute("DELETE FROM tce_pagamento WHERE slug=? AND ano=?", (sl, ano))
    con.executemany("INSERT INTO tce_funcao VALUES (?,?,?,?,?,?)", [(sl, ano, f, fo, round(v, 2), q) for (f, fo), (v, q) in por_funcao.items()])
    itens = sorted(pag.items(), key=lambda t: -t[1][0])
    emen = [t for t in itens if t[0][4]][:RETER]
    resto = [t for t in itens if not t[0][4]][:RETER]
    con.executemany("INSERT INTO tce_pagamento (slug, ano, documento, fornecedor, funcao, fonte, emenda, historico, pago, n, modalidade) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [(sl, ano, k[0], k[1], k[2], k[3], k[4], k[5], round(v, 2), q, k[6]) for k, (v, q) in emen + resto])
    con.execute("DELETE FROM tce_fornecedor WHERE slug=? AND ano=?", (sl, ano))
    top = sorted((forn or {}).items(), key=lambda t: -t[1][0])[:200]
    con.executemany("INSERT INTO tce_fornecedor VALUES (?,?,?,?,?,?,?,?,?)",
                    [(sl, ano, k[0], k[1], k[2], round(v[0], 2), round(v[1], 2), round(v[2], 2), v[3]) for k, v in top])
    con.execute("INSERT OR REPLACE INTO tce_carga VALUES (?,?,?,?,?)", (sl, ano, nome, n, c.agora()))
    con.commit()


def rodar(con, municipios=None, desde=ANO_MIN, ate=None, baixar=_baixar):
    ate = ate or datetime.now().year
    municipios = municipios or escolher_municipios(con)
    if not municipios:
        print("  AVISO: sem municipios paulistas entre os recebedores de emendas; rode antes a etapa de emendas", file=sys.stderr)
        return 0
    feitos = {(r[0], r[1]) for r in con.execute("SELECT DISTINCT slug, ano FROM tce_fornecedor")}  # anos sem fornecedores (carga antiga) sao baixados de novo
    total = falhas = 0
    inicio = time.time()
    for nome in municipios:
        if time.time() - inicio > LIMITE_SEGUNDOS:
            print(f"  AVISO: tempo esgotado em {nome}; os demais municipios entram na proxima rodada", file=sys.stderr)
            break
        sl = slug(nome)      # chave no site (nome das emendas)
        sl_tce = sl          # endereco no TCE-SP
        corrigido = False
        for ano in range(desde, ate + 1):
            if (sl, ano) in feitos and ano < ate - 1:
                continue  # anos fechados ja carregados nao mudam
            try:
                texto = baixar(BASE.format(slug=sl_tce, ano=ano))
                if ano == desde and not total:
                    print(f"  Colunas do TCE-SP: {texto.splitlines()[0][:400]}")
                por_funcao, pag, n, forn = agregar(texto)
                if not n:
                    raise ValueError("arquivo sem linhas")
            except Exception as e:
                if "404" in str(e) and not corrigido:
                    corrigido = True
                    novo = _slug_tce(nome)
                    if novo and novo != sl_tce:
                        sl_tce = novo
                        try:
                            texto = baixar(BASE.format(slug=sl_tce, ano=ano))
                            por_funcao, pag, n, forn = agregar(texto)
                            salvar(con, sl, ano, nome, por_funcao, pag, n, forn)
                            total += 1
                            print(f"  TCE-SP {nome} ({sl_tce}) {ano}: {n} linhas")
                            continue
                        except Exception as e2:
                            e = e2
                falhas += 1
                print(f"  AVISO: TCE-SP {nome} {ano}: {e}", file=sys.stderr)
                if "404" in str(e):
                    break  # o municipio nao existe sob esse nome: nao insistir nos outros anos
                continue
            salvar(con, sl, ano, nome, por_funcao, pag, n, forn)
            total += 1
            print(f"  TCE-SP {nome} {ano}: {n} linhas")
    c.log(con, "tcesp", "despesas", None, total)
    con.commit()
    print(f"TCE-SP: {total} arquivos municipio/ano carregados ({falhas} falhas); municipios: {', '.join(municipios)}")
    return total
