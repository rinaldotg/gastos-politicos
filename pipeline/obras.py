"""Obras federais (Obras.gov.br, API aberta): situacao das obras cujo executor e um recebedor de emendas.

A API nao informa a emenda nem o convenio da obra: o elo com as emendas e o CNPJ do executor
(a prefeitura, o governo estadual ou a entidade que recebeu o dinheiro). Guardamos so as obras
cujo executor aparece como recebedor de emenda de algum parlamentar.
"""
import re
import sys
import time

from . import common as c

SITUACOES = ["Paralisada", "Inacabada", "Em execução", "Concluída", "Cadastrada", "Cancelada"]
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
    inicio = time.monotonic()
    linhas, vistas = [], 0
    ids_lidos, tipos_completos = set(), []

    def ler(situacao):
        """Le todas as paginas (opcionalmente so de uma situacao). Devolve (completo, filtro_valido)."""
        nonlocal vistas
        pagina, falhas, chaves = 0, 0, set()
        while True:
            if time.monotonic() - inicio > LIMITE_SEGUNDOS:
                print(f"  AVISO: limite de {LIMITE_SEGUNDOS // 60} min atingido ({situacao or 'todas'}, pagina {pagina}; {vistas} projetos lidos)", file=sys.stderr)
                return False, True
            params = {"pagina": pagina, "tamanhoDaPagina": tam}
            if situacao:
                params["situacao"] = situacao
            try:
                j = c.get_paciente(URL, params, timeout=180).json()
            except Exception as e:
                falhas += 1
                print(f"  AVISO: pagina {pagina} das obras ({situacao or 'todas'}) falhou: {e}", file=sys.stderr)
                if falhas >= 3:
                    return False, True
                pagina += 1
                continue
            falhas = 0
            time.sleep(1.5)  # a API limita pedidos (429)
            itens, tp = _lista(j)
            if pagina == 0:
                if situacao and itens and any((p.get("situacao") or "") != situacao for p in itens):
                    print(f"  AVISO: a API ignorou o filtro situacao={situacao}", file=sys.stderr)
                    return False, False
                extra = {k: v for k, v in j.items() if not isinstance(v, (list, dict))} if isinstance(j, dict) else {}
                print(f"  Obras ({situacao or 'todas'}): campos {sorted(itens[0].keys()) if itens else []} (resposta: {extra})")
            if not itens:
                return True, True
            chave = tuple(str(p.get("idUnico")) for p in itens[:5])
            if chave in chaves:
                print("  AVISO: a API repetiu a mesma pagina; parando a leitura", file=sys.stderr)
                return True, True
            chaves.add(chave)
            # totalPages informado pela API nao e confiavel: so paramos em pagina vazia/curta
            vistas += len(itens)
            for p in itens:
                ids_lidos.add(p.get("idUnico"))
                linhas.extend(_linhas(p, docs))
            pagina += 1
            if len(itens) < tam and (tp is None or pagina >= tp):
                return True, True
            if pagina > 5000:
                return True, True

    completo = True
    # situacoes que mais interessam primeiro: se o tempo acabar, o que importa ja foi lido
    for sit in SITUACOES:
        ok, filtro_valido = ler(sit)
        if not filtro_valido:
            ok = ler(None)[0]
            completo = ok
            break
        if ok:
            tipos_completos.append(sit)
        else:
            completo = False
            break
    if not linhas and not completo and con.execute("SELECT 1 FROM obra LIMIT 1").fetchone():
        print("  AVISO: nenhuma obra lida; mantive as obras da atualizacao anterior", file=sys.stderr)
        return 0
    if completo:
        con.execute("DELETE FROM obra")
    elif ids_lidos:
        con.executemany("DELETE FROM obra WHERE id_unico=?", [(i_,) for i_ in ids_lidos])
    con.executemany("""INSERT INTO obra (id_unico, nome, situacao, uf, especie, natureza, tipo, subtipo, valor, ini_prev, fim_prev,
                       ini_efetiva, fim_efetiva, data_situacao, executor_cnpj, executor_nome, repassador) VALUES
                       (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", linhas)
    c.log(con, "obrasgov", "obras", None, len(linhas))
    con.commit()
    print(f"Obras{'' if completo else ' (leitura parcial; situacoes completas: ' + ', '.join(tipos_completos) + ')'}: {vistas} projetos lidos; {len(linhas)} de executores que receberam emendas")
    return len(linhas)
