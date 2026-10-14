"""Obras federais (Obras.gov.br, API aberta): situacao das obras cujo executor e um recebedor de emendas.

A API nao informa a emenda nem o convenio da obra: o elo com as emendas e o CNPJ do executor
(a prefeitura, o governo estadual ou a entidade que recebeu o dinheiro). Guardamos so as obras
cujo executor aparece como recebedor de emenda de algum parlamentar.
"""
import re
import sys

from . import common as c

URL = "https://api.obrasgov.gestao.gov.br/obrasgov/api/projeto-investimento"


def _cnpj(v):
    d = re.sub(r"\D", "", str(v or ""))
    return d.zfill(14) if 12 <= len(d) <= 14 else ""


def _lista(j):
    if isinstance(j, list):
        return j, None
    if isinstance(j, dict):
        itens = j.get("content")
        if itens is None:
            itens = next((v for v in j.values() if isinstance(v, list)), [])
        return itens, j.get("totalPages")
    return [], None


def _linhas(p, docs):
    out = []
    valor = sum(float(f.get("valorInvestimentoPrevisto") or 0) for f in (p.get("fontesDeRecurso") or []) if isinstance(f, dict))
    tipos = p.get("tipos") or []
    subs = p.get("subTipos") or []
    rep = (p.get("repassadores") or [{}])[0].get("nome") if p.get("repassadores") else None
    for e in p.get("executores") or []:
        cnpj = _cnpj(e.get("codigo"))
        if cnpj and cnpj in docs:
            out.append((p.get("idUnico"), (p.get("nome") or "").strip()[:300], p.get("situacao"), p.get("uf"), p.get("especie"),
                        p.get("natureza"), tipos[0].get("descricao") if tipos else None, subs[0].get("descricao") if subs else None,
                        valor, p.get("dataInicialPrevista"), p.get("dataFinalPrevista"), p.get("dataInicialEfetiva"),
                        p.get("dataFinalEfetiva"), p.get("dataSituacao"), cnpj, (e.get("nome") or "").strip(), rep))
    return out


def rodar(con, tamanhos=(100, 50, 20)):
    docs = {_cnpj(r[0]) for r in con.execute("SELECT DISTINCT documento FROM emenda_favorecido WHERE documento IS NOT NULL")}
    docs.discard("")
    if not docs:
        print("  AVISO: sem recebedores de emendas no banco; rode antes a etapa de emendas", file=sys.stderr)
        return 0
    tam = None
    for t in tamanhos:
        try:
            c.get(URL, {"pagina": 0, "tamanhoDaPagina": t}, tentativas=2, timeout=120).json()
            tam = t
            break
        except Exception as e:
            print(f"  tamanho de pagina {t} recusado: {e}", file=sys.stderr)
    if tam is None:
        print("  AVISO: nao consegui consultar a API do Obras.gov.br", file=sys.stderr)
        return 0
    linhas, pagina, total_paginas, falhas, vistas = [], 0, None, 0, 0
    while True:
        try:
            j = c.get(URL, {"pagina": pagina, "tamanhoDaPagina": tam}, tentativas=3, timeout=180).json()
        except Exception as e:
            falhas += 1
            print(f"  AVISO: pagina {pagina} das obras falhou: {e}", file=sys.stderr)
            if falhas >= 3:
                print("  AVISO: obras interrompidas; os dados anteriores foram mantidos", file=sys.stderr)
                return 0
            pagina += 1
            continue
        falhas = 0
        itens, tp = _lista(j)
        if pagina == 0:
            print(f"  Campos das obras: {sorted(itens[0].keys()) if itens else []} (paginas: {tp})")
        total_paginas = tp or total_paginas
        if not itens:
            break
        vistas += len(itens)
        for p in itens:
            linhas.extend(_linhas(p, docs))
        pagina += 1
        if total_paginas is not None and pagina >= total_paginas:
            break
        if pagina > 5000:
            break
    con.execute("DELETE FROM obra")
    con.executemany("""INSERT INTO obra (id_unico, nome, situacao, uf, especie, natureza, tipo, subtipo, valor, ini_prev, fim_prev,
                       ini_efetiva, fim_efetiva, data_situacao, executor_cnpj, executor_nome, repassador) VALUES
                       (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", linhas)
    c.log(con, "obrasgov", "obras", None, len(linhas))
    con.commit()
    print(f"Obras: {vistas} projetos lidos; {len(linhas)} de executores que receberam emendas")
    return len(linhas)
