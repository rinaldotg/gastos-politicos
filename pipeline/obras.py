"""Obras federais (Obras.gov.br, API aberta): situacao das obras cujo executor e um recebedor de emendas.

A API nao informa a emenda nem o convenio da obra: o elo com as emendas e o CNPJ do executor
(a prefeitura, o governo estadual ou a entidade que recebeu o dinheiro). Guardamos so as obras
cujo executor aparece como recebedor de emenda de algum parlamentar.
"""
import re
import sys
import time

from . import common as c

LIMITE_SEGUNDOS = 25 * 60  # tempo maximo da leitura; depois disso segue o resto da atualizacao
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
            c.get_paciente(URL, {"pagina": 0, "tamanhoDaPagina": t}, timeout=120).json()
            tam = t
            break
        except Exception as e:
            print(f"  tamanho de pagina {t} recusado: {e}", file=sys.stderr)
    if tam is None:
        print("  AVISO: nao consegui consultar a API do Obras.gov.br", file=sys.stderr)
        return 0
    linhas, pagina, falhas, vistas, chaves = [], 0, 0, 0, set()
    inicio = time.monotonic()
    completo = True
    while True:
        if time.monotonic() - inicio > LIMITE_SEGUNDOS:
            completo = False
            print(f"  AVISO: limite de {LIMITE_SEGUNDOS // 60} min atingido na pagina {pagina} ({vistas} projetos lidos)", file=sys.stderr)
            break
        try:
            j = c.get_paciente(URL, {"pagina": pagina, "tamanhoDaPagina": tam}, timeout=180).json()
        except Exception as e:
            falhas += 1
            print(f"  AVISO: pagina {pagina} das obras falhou: {e}", file=sys.stderr)
            if falhas >= 3:
                print("  AVISO: obras interrompidas; os dados anteriores foram mantidos", file=sys.stderr)
                return 0
            pagina += 1
            continue
        falhas = 0
        time.sleep(1.5)  # a API limita pedidos (429)
        itens, tp = _lista(j)
        if pagina == 0:
            extra = {k: v for k, v in j.items() if not isinstance(v, (list, dict))} if isinstance(j, dict) else {}
            print(f"  Campos das obras: {sorted(itens[0].keys()) if itens else []} (paginas: {tp}; resposta: {extra})")
        if not itens:
            break
        chave = tuple(str(p.get("idUnico")) for p in itens[:5])
        if chave in chaves:
            print("  AVISO: a API repetiu a mesma pagina; parando a leitura", file=sys.stderr)
            break
        chaves.add(chave)
        # totalPages informado pela API nao e confiavel (veio 1 com milhares de projetos): so paramos em pagina vazia/curta
        vistas += len(itens)
        for p in itens:
            linhas.extend(_linhas(p, docs))
        pagina += 1
        if len(itens) < tam and (tp is None or pagina >= tp):
            break
        if pagina > 5000:
            break
    if not completo and con.execute("SELECT 1 FROM obra LIMIT 1").fetchone():
        print("  AVISO: leitura incompleta; mantive as obras da atualizacao anterior", file=sys.stderr)
        return 0
    con.execute("DELETE FROM obra")
    con.executemany("""INSERT INTO obra (id_unico, nome, situacao, uf, especie, natureza, tipo, subtipo, valor, ini_prev, fim_prev,
                       ini_efetiva, fim_efetiva, data_situacao, executor_cnpj, executor_nome, repassador) VALUES
                       (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", linhas)
    c.log(con, "obrasgov", "obras", None, len(linhas))
    con.commit()
    print(f"Obras{'' if completo else ' (leitura parcial)'}: {vistas} projetos lidos; {len(linhas)} de executores que receberam emendas")
    return len(linhas)
