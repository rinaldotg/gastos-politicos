"""Utilitarios comuns: HTTP com repeticao, banco, leitura de CSV tolerante."""
import csv
import io
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; transparencia-gastos/1.0; +https://github.com)",
    "Accept": "application/json, text/csv, */*",
}
HEADERS_NAVEGADOR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/zip,application/octet-stream,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://portaldatransparencia.gov.br/download-de-dados",
}
ANO_INICIAL = 2014
PAUSA_PORTAL = 3  # segundos entre downloads do Portal da Transparencia (evita bloqueio por excesso de pedidos)
BLOQUEIO = (403, 405, 429)


def eh_portal(url):
    return "portaldatransparencia" in url or "cgu.gov.br" in url


def agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get(url, params=None, tentativas=4, timeout=120, stream=False, rapido=False):
    """GET com repeticao. Devolve a resposta; levanta a ultima excecao se esgotar."""
    ultimo = None
    portal = eh_portal(url)
    if portal:
        time.sleep(PAUSA_PORTAL)
        tentativas = 1 if rapido else max(tentativas, 4)  # rapido: tentar enderecos que podem nao existir
    for i in range(tentativas):
        try:
            r = requests.get(url, params=params, headers=HEADERS_NAVEGADOR if portal else HEADERS,
                             timeout=timeout, stream=stream)
            if r.status_code == 404:
                r.raise_for_status()  # 404 nao adianta repetir
            r.raise_for_status()
            return r
        except requests.HTTPError as e:
            ultimo = e
            if e.response is not None and e.response.status_code == 404:
                raise
        except requests.RequestException as e:
            ultimo = e
        if i < tentativas - 1:
            bloqueado = portal and getattr(getattr(ultimo, "response", None), "status_code", None) in BLOQUEIO
            time.sleep((30 * 3 ** i) if bloqueado else 2 ** i)  # bloqueio: espera 30s, 90s, 270s
            print(f"  nova tentativa {i + 1} ({ultimo})", file=sys.stderr)
    raise ultimo


def abrir_banco(caminho):
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.executescript((Path(__file__).parent / "schema.sql").read_text(encoding="utf-8"))
    # bancos criados por versoes antigas: acrescenta colunas novas
    existentes = {r[1] for r in con.execute("PRAGMA table_info(emenda)")}
    for coluna in ("programa", "acao", "localidade"):
        if coluna not in existentes:
            con.execute(f"ALTER TABLE emenda ADD COLUMN {coluna} TEXT")
    if "ano" not in {r[1] for r in con.execute("PRAGMA table_info(emenda_favorecido)")}:
        con.execute("ALTER TABLE emenda_favorecido ADD COLUMN ano INTEGER")
    if "publicacao" not in {r[1] for r in con.execute("PRAGMA table_info(emenda_convenio)")}:
        con.execute("ALTER TABLE emenda_convenio ADD COLUMN publicacao TEXT")
    con.commit()
    return con


def log(con, fonte, recurso, ano, n):
    con.execute("INSERT INTO coleta_log (fonte, recurso, ano, registros, coletado_em) VALUES (?,?,?,?,?)",
                (fonte, recurso, ano, n, agora()))
    con.commit()


def pessoa_por_fonte(con, fonte, id_externo):
    r = con.execute("SELECT pessoa_id FROM pessoa_fonte WHERE fonte=? AND id_externo=?",
                    (fonte, str(id_externo))).fetchone()
    return r[0] if r else None


def criar_pessoa(con, fonte, id_externo, nome, cargo):
    cur = con.execute("INSERT INTO pessoa (nome, cargo) VALUES (?,?)", (nome, cargo))
    pid = cur.lastrowid
    con.execute("INSERT INTO pessoa_fonte VALUES (?,?,?)", (pid, fonte, str(id_externo)))
    return pid


def sem_acento(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def decodificar(bruto):
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return bruto.decode(enc)
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1", errors="replace")


def ler_csv(bruto):
    """Devolve (colunas, linhas como dict, funcao col(linha, *opcoes)). Tolera separador,
    codificacao e variacoes de acento/caixa nos nomes das colunas."""
    texto = decodificar(bruto)
    primeira = texto.splitlines()[0] if texto else ""
    delim = ";" if primeira.count(";") >= primeira.count(",") else ","
    leitor = csv.DictReader(io.StringIO(texto), delimiter=delim, quotechar='"')
    leitor.fieldnames = [(c or "").strip().strip('"') for c in (leitor.fieldnames or [])]
    mapa = {sem_acento(c): c for c in leitor.fieldnames}

    def col(linha, *opcoes):
        for o in opcoes:
            c = mapa.get(sem_acento(o))
            if c is not None and linha.get(c) not in (None, ""):
                return linha[c].strip()
        return ""

    return leitor.fieldnames, leitor, col


def numero(txt):
    t = (txt or "").strip().replace("R$", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def data_iso(txt):
    """'dd/mm/aaaa' ou 'aaaa-mm-dd...' -> 'aaaa-mm-dd' (ou '')."""
    t = (txt or "").strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", t)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", t)
    return m.group(0) if m else ""


def legislatura_de(ano, mes):
    """Legislaturas comecam em 1o de fevereiro de 2011, 2015, 2019, 2023..."""
    return 54 + (ano - (1 if mes == 1 else 0) - 2011) // 4
