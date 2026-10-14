"""Emendas parlamentares (Portal da Transparencia): quanto cada parlamentar indicou, empenhou e pagou.

Emendas de bancada, comissao e relator nao tem autor individual: ficam com pessoa_id NULL e
aparecem em totais gerais. O autor so e vinculado a uma pessoa quando o nome (sem acento,
maiusculas) casa com UMA unica pessoa deputado/senador; nomes repetidos ficam sem vinculo.
Colunas escritas de memoria: ler_csv tolera variacoes e o log imprime as colunas reais.
"""
import csv
import io
import re
import sys
import zipfile

from . import common as c

URL = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
COLETIVAS = ("bancada", "comissao", "relator")


TITULOS = {"PR", "PASTOR", "DR", "DRA", "DEL", "DELEGADO", "DELEGADA", "CABO", "SARGENTO", "SGT", "CORONEL", "CEL",
           "PROF", "PROFESSOR", "PROFESSORA", "TENENTE", "MAJOR", "CAPITAO", "PADRE", "BISPO", "DOUTOR", "DOUTORA"}
LIGACOES = {"DE", "DA", "DO", "DAS", "DOS", "E"}


def chave(nome):
    """Nome em maiusculas, sem acento, sem pontuacao nem titulos (Pr., Dr., Pastor...)."""
    t = c.sem_acento(nome or "").upper().replace("'", "")
    t = "".join(ch if ch.isalnum() else " " for ch in t)
    return " ".join(w for w in t.split() if w not in TITULOS)


def _tokens(nome):
    return frozenset(w for w in chave(nome).split() if w not in LIGACOES)


def _indice_nomes(con):
    idx, toks = {}, {}
    for pid, nome in con.execute("SELECT id, nome FROM pessoa WHERE cargo IN ('deputado_federal','senador')"):
        idx.setdefault(chave(nome), []).append(pid)
        toks[pid] = _tokens(nome)
    return idx, toks


def _legislaturas(con):
    m = {}
    for pid, leg in con.execute("SELECT pessoa_id, legislatura FROM mandato WHERE cargo IN ('deputado_federal','senador')"):
        m.setdefault(pid, set()).add(leg)
    return m


def _norm(h):
    return c.sem_acento(h or "").lower().strip()


def _fluxo_csv(z, nome):
    """Abre um CSV grande do zip em fluxo (sem carregar tudo na memoria). Devolve (cabecalho, linhas)."""
    with z.open(nome) as f:
        amostra = f.read(65536)
    try:
        amostra.decode("utf-8")
        enc = "utf-8-sig"
    except UnicodeDecodeError as e:
        enc = "utf-8-sig" if e.start >= len(amostra) - 4 else "latin-1"
    primeira = amostra.split(b"\n", 1)[0]
    sep = ";" if primeira.count(b";") >= primeira.count(b",") else ","
    texto = io.TextIOWrapper(z.open(nome), encoding=enc, errors="replace", newline="")
    leitor = csv.reader(texto, delimiter=sep)
    return next(leitor), leitor


def _achar(cab, *padroes, exato=None):
    """Indice da primeira coluna cujo nome (sem acento, minusculo) contem todos os termos de algum padrao."""
    ncab = [_norm(h) for h in cab]
    if exato:
        for e in exato:
            if e in ncab:
                return ncab.index(e)
    for pad in padroes:
        for i, h in enumerate(ncab):
            if all(t in h for t in pad):
                return i
    return None


def carregar_favorecidos(con, z):
    """Quem recebeu o dinheiro de cada emenda individual vinculada a um parlamentar."""
    nome = next((n for n in z.namelist() if "favorecido" in n.lower()), None)
    if not nome:
        print("  AVISO: o zip de emendas nao traz o arquivo por favorecido", file=sys.stderr)
        return 0
    cab, linhas = _fluxo_csv(z, nome)
    print(f"  Colunas de emendas por favorecido ({nome}): {cab}")
    i_cod = _achar(cab, ("codigo", "emenda"), exato=["codigo da emenda"])
    i_nome = _achar(cab, ("nome", "favorecido"), ("favorecido",), exato=["favorecido"])
    i_doc = _achar(cab, ("codigo", "favorecido"), ("cnpj",), ("cpf",), ("documento",))
    i_tipo = _achar(cab, ("tipo", "favorecido"))
    i_uf = _achar(cab, ("uf", "favorecido"), ("uf",))
    i_mun = _achar(cab, ("municipio", "favorecido"), ("municipio",))
    i_val = _achar(cab, ("valor", "recebido"), ("valor",))
    i_ano = _achar(cab, ("ano", "mes"), ("ano",))
    if i_cod is None or i_nome is None or i_val is None:
        print("  AVISO: colunas de favorecido nao reconhecidas; mande o log para ajustar", file=sys.stderr)
        return 0
    validos = {r[0] for r in con.execute("SELECT DISTINCT codigo FROM emenda WHERE pessoa_id IS NOT NULL AND codigo IS NOT NULL")}
    agg = {}

    def cel(l, i):
        return (l[i].strip() if i is not None and i < len(l) else "")
    for l in linhas:
        cod = cel(l, i_cod)
        if cod not in validos:
            continue
        m_ano = re.match(r"\s*(\d{4})", cel(l, i_ano))
        chave_ = (cod, cel(l, i_doc), cel(l, i_nome), int(m_ano.group(1)) if m_ano else 0)
        a = agg.get(chave_)
        if a is None:
            agg[chave_] = [cel(l, i_tipo), cel(l, i_uf), cel(l, i_mun), c.numero(cel(l, i_val)), 1]
        else:
            a[3] += c.numero(cel(l, i_val)); a[4] += 1
    con.execute("DELETE FROM emenda_favorecido")
    con.executemany("""INSERT INTO emenda_favorecido (codigo, favorecido, documento, tipo, uf, municipio, valor, n, ano)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    [(k[0], k[2] or None, k[1] or None, v[0] or None, v[1] or None, v[2] or None, v[3], v[4], k[3] or None)
                     for k, v in agg.items()])
    c.log(con, "portal", "emendas_favorecidos", None, len(agg))
    con.commit()
    print(f"Emendas: {len(agg)} favorecidos (por emenda) ligados a parlamentares")
    return len(agg)


def carregar_convenios(con, z):
    """Convenio de cada emenda (objeto, convenente, situacao, valores), quando a emenda virou convenio."""
    nome = next((n for n in z.namelist() if "convenio" in n.lower()), None)
    if not nome:
        print("  AVISO: o zip de emendas nao traz o arquivo de convenios", file=sys.stderr)
        return 0
    cab, linhas = _fluxo_csv(z, nome)
    print(f"  Colunas de convenios ({nome}): {cab}")
    i_cod = _achar(cab, ("codigo", "emenda"), exato=["codigo da emenda"])
    i_num = _achar(cab, ("numero", "convenio"), ("convenio",))
    i_conv = _achar(cab, ("convenente",), ("nome", "convenente"))
    i_obj = _achar(cab, ("objeto",))
    i_sit = _achar(cab, ("situacao",))
    i_val = _achar(cab, ("valor", "convenio"), ("valor", "original"), ("valor", "total"))
    i_lib = _achar(cab, ("valor", "liberado"), ("liberado",))
    i_ini = _achar(cab, ("inicio",))
    i_fim = _achar(cab, ("fim",))
    i_pub = _achar(cab, ("publicacao",))
    if i_cod is None or i_num is None:
        print("  AVISO: colunas de convenios nao reconhecidas; mande o log para ajustar", file=sys.stderr)
        return 0
    validos = {r[0] for r in con.execute("SELECT DISTINCT codigo FROM emenda WHERE pessoa_id IS NOT NULL AND codigo IS NOT NULL")}
    agg = {}

    def cel(l, i):
        return (l[i].strip() if i is not None and i < len(l) else "")
    for l in linhas:
        cod = cel(l, i_cod)
        if cod not in validos:
            continue
        agg[(cod, cel(l, i_num))] = (cel(l, i_conv), cel(l, i_obj), cel(l, i_sit), c.numero(cel(l, i_val)),
                                     c.numero(cel(l, i_lib)), cel(l, i_ini), cel(l, i_fim), cel(l, i_pub))
    con.execute("DELETE FROM emenda_convenio")
    con.executemany("""INSERT INTO emenda_convenio (codigo, numero, convenente, objeto, situacao, valor, liberado, inicio, fim, publicacao)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [(k[0], k[1] or None, v[0] or None, v[1] or None, v[2] or None, v[3], v[4], v[5] or None, v[6] or None, v[7] or None)
                     for k, v in agg.items()])
    c.log(con, "portal", "emendas_convenios", None, len(agg))
    con.commit()
    print(f"Emendas: {len(agg)} convenios ligados a emendas de parlamentares")
    return len(agg)


def carregar_situacao_convenios(con):
    """Situacao, valor liberado e vigencia dos convenios (cadastro geral de convenios do Portal), ligados pelo numero."""
    from datetime import date, timedelta
    BASE = "https://portaldatransparencia.gov.br/download-de-dados/convenios"
    hoje = date.today()
    candidatos = [(hoje - timedelta(days=d)).strftime("%Y%m%d") for d in range(0, 15)] + \
                 [hoje.strftime("%Y%m"), (hoje.replace(day=1) - timedelta(days=1)).strftime("%Y%m")]
    z = None
    for cand in candidatos:
        try:
            r = c.get(f"{BASE}/{cand}", timeout=600, rapido=True)
            z = zipfile.ZipFile(io.BytesIO(r.content))
            print(f"  Cadastro de convenios baixado ({cand})")
            break
        except Exception:
            continue
    if z is None:
        print("  AVISO: nao consegui baixar o cadastro geral de convenios (situacao dos convenios fica sem informacao)", file=sys.stderr)
        return 0
    nome = next((n for n in z.namelist() if "convenio" in n.lower() and not any(x in n.lower() for x in ("ordem", "ordens", "liberac"))), None)
    if not nome:
        print(f"  AVISO: cadastro de convenios sem arquivo principal: {z.namelist()}", file=sys.stderr)
        return 0
    cab, linhas = _fluxo_csv(z, nome)
    print(f"  Colunas do cadastro de convenios ({nome}): {cab}")
    i_num = _achar(cab, ("numero", "convenio"), exato=["numero convenio"])
    i_sit = _achar(cab, ("situacao",))
    i_lib = _achar(cab, ("valor", "liberado"), ("liberado",))
    i_ini = _achar(cab, ("inicio", "vigencia"), ("inicio",))
    i_fim = _achar(cab, ("fim", "vigencia"), ("fim",))
    if i_num is None or i_sit is None:
        print("  AVISO: colunas do cadastro de convenios nao reconhecidas; mande o log para ajustar", file=sys.stderr)
        return 0
    nossos = {r[0] for r in con.execute("SELECT DISTINCT numero FROM emenda_convenio WHERE numero IS NOT NULL")}

    def cel(l, i):
        return (l[i].strip() if i is not None and i < len(l) else "")
    dados = {}
    for l in linhas:
        n = cel(l, i_num)
        if n in nossos:
            dados[n] = (cel(l, i_sit), c.numero(cel(l, i_lib)), cel(l, i_ini), cel(l, i_fim))
    con.executemany("UPDATE emenda_convenio SET situacao=?, liberado=?, inicio=?, fim=? WHERE numero=?",
                    [(v[0] or None, v[1], v[2] or None, v[3] or None, k) for k, v in dados.items()])
    con.commit()
    print(f"Emendas: situacao de {len(dados)} de {len(nossos)} convenios")
    return len(dados)


def carregar(con, desde):
    try:
        r = c.get(URL, timeout=600)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        nome = next(n for n in z.namelist()
                    if "emendas" in n.lower() and "favorecido" not in n.lower() and "convenio" not in n.lower())
        colunas, linhas, col = c.ler_csv(z.open(nome).read())
    except Exception as e:
        print(f"  AVISO: emendas indisponiveis: {e}", file=sys.stderr)
        return None
    print(f"  Colunas das emendas: {colunas}")
    idx, toks = _indice_nomes(con)
    legs = _legislaturas(con)
    sem = {}
    con.execute("DELETE FROM emenda")
    saida, sem_vinculo, ambiguos = [], 0, 0
    for l in linhas:
        try:
            ano = int(col(l, "Ano da Emenda") or 0)
        except ValueError:
            continue
        if ano < desde:
            continue
        tipo = col(l, "Tipo de Emenda") or "(sem tipo)"
        autor = col(l, "Nome do Autor da Emenda") or "(sem autor)"
        pid = None
        if not any(k in c.sem_acento(tipo).lower() for k in COLETIVAS):
            cands = idx.get(chave(autor), [])
            if not cands:  # nome civil completo x nome parlamentar: um contem o outro (>=2 palavras)
                ta = _tokens(autor)
                cands = [p for p, tp in toks.items() if len(tp) >= 2 and len(ta) >= 2 and (tp <= ta or ta <= tp)]
            if len(cands) > 1:  # mesmo nome em mais de uma pessoa: fica com quem tinha mandato na legislatura da emenda
                leg = c.legislatura_de(ano, 6)
                cands = [p for p in cands if leg in legs.get(p, ())] or cands
            if len(cands) == 1:
                pid = cands[0]
            elif len(cands) > 1:
                ambiguos += 1
            else:
                sem_vinculo += 1
                sem[autor] = sem.get(autor, 0) + 1
        saida.append((pid, autor, tipo, col(l, "Código da Emenda", "Codigo da Emenda"), ano,
                      col(l, "Número da emenda", "Numero da emenda"), col(l, "UF") or None,
                      col(l, "Município", "Municipio") or None, col(l, "Nome Função", "Nome Funcao") or None,
                      col(l, "Nome Subfunção", "Nome Subfuncao") or None,
                      col(l, "Nome Programa") or None, col(l, "Nome Ação", "Nome Acao") or None,
                      col(l, "Localidade de aplicação do recurso", "Localidade de aplicacao do recurso") or None,
                      c.numero(col(l, "Valor Empenhado")), c.numero(col(l, "Valor Liquidado")),
                      c.numero(col(l, "Valor Pago")), c.numero(col(l, "Valor Restos A Pagar Inscritos")),
                      c.numero(col(l, "Valor Restos A Pagar Cancelados")), c.numero(col(l, "Valor Restos A Pagar Pagos")), "emendas:unico"))
    con.executemany("""INSERT INTO emenda (pessoa_id, autor, tipo, codigo, ano, numero, uf, municipio, funcao,
                       subfuncao, programa, acao, localidade, empenhado, liquidado, pago,
                       rap_inscrito, rap_cancelado, rap_pago, arquivo)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", saida)
    c.log(con, "portal", "emendas", None, len(saida))
    con.commit()
    if sem:
        top = sorted(sem.items(), key=lambda x: -x[1])[:15]
        print("  Autores individuais sem correspondencia (15 mais frequentes):", top)
    print(f"Emendas: {len(saida)} linhas; autores individuais sem correspondencia: {sem_vinculo}; nomes ambiguos: {ambiguos}")
    try:
        carregar_favorecidos(con, z)
    except Exception as e:  # o restante das emendas ja esta salvo
        print(f"  AVISO: favorecidos das emendas falharam: {e}", file=sys.stderr)
    try:
        carregar_convenios(con, z)
    except Exception as e:
        print(f"  AVISO: convenios das emendas falharam: {e}", file=sys.stderr)
    try:
        carregar_situacao_convenios(con)
    except Exception as e:
        print(f"  AVISO: situacao dos convenios falhou: {e}", file=sys.stderr)
    return len(saida)


def rodar(con, desde):
    carregar(con, desde)
