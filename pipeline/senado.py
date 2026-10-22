"""Senado Federal: senadores (API) e CEAPS (API de dados abertos administrativos)."""
import sys

from . import common as c

LEGIS = "https://legis.senado.leg.br/dadosabertos"
ADM = "https://adm.senado.gov.br/adm-dadosabertos/api/v1"
LEGISLATURAS = [54, 55, 56, 57]
CARGO = "senador"


def lista(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def garantir_mandato(con, pid, leg, uf, partido):
    con.execute("""INSERT OR IGNORE INTO mandato (pessoa_id, cargo, legislatura, uf, partido)
                   VALUES (?,?,?,?,?)""", (pid, CARGO, leg, uf, partido))


def carregar_senadores(con):
    total = 0
    for leg in LEGISLATURAS:
        js = c.get(f"{LEGIS}/senador/lista/legislatura/{leg}.json").json()
        pars = lista(((js.get("ListaParlamentarLegislatura") or {}).get("Parlamentares") or {}).get("Parlamentar"))
        for p in pars:
            ident = p.get("IdentificacaoParlamentar") or {}
            cod = ident.get("CodigoParlamentar")
            if not cod:
                continue
            pid = c.pessoa_por_fonte(con, "senado", cod) or \
                c.criar_pessoa(con, "senado", cod, ident.get("NomeParlamentar") or f"Senador {cod}", CARGO)
            ufs = [m.get("UfParlamentar") for m in lista((p.get("Mandatos") or {}).get("Mandato")) if m.get("UfParlamentar")]
            garantir_mandato(con, pid, leg, (ufs[0] if ufs else ident.get("UfParlamentar")),
                             ident.get("SiglaPartidoParlamentar"))
            if ident.get("UrlFotoParlamentar"):
                c.guardar_foto(con, pid, ident["UrlFotoParlamentar"])
            total += 1
        con.commit()
        print(f"  Senado, legislatura {leg}: {len(pars)} registros")
    c.log(con, "senado", "senadores", None, total)
    print(f"Senadores: {total} mandatos")


def completar_uf(con):
    """Quem foi criado a partir das despesas nao tem UF/partido: busca na ficha do senador."""
    pend = con.execute(
        """SELECT DISTINCT p.id, f.id_externo FROM pessoa p
           JOIN pessoa_fonte f ON f.pessoa_id = p.id AND f.fonte='senado'
           JOIN mandato m ON m.pessoa_id = p.id AND m.cargo='senador'
           WHERE m.uf IS NULL OR m.uf = ''""").fetchall()
    ok = 0
    for pid, cod in pend:
        try:
            par = (c.get(f"{LEGIS}/senador/{cod}.json").json().get("DetalheParlamentar") or {}).get("Parlamentar") or {}
            ident = par.get("IdentificacaoParlamentar") or {}
            uf = ident.get("UfParlamentar")
            if not uf:
                continue
            con.execute("UPDATE mandato SET uf=? WHERE pessoa_id=? AND cargo='senador' AND (uf IS NULL OR uf='')", (uf, pid))
            con.execute("UPDATE mandato SET partido=? WHERE pessoa_id=? AND cargo='senador' AND (partido IS NULL OR partido='')",
                        (ident.get("SiglaPartidoParlamentar"), pid))
            ok += 1
        except Exception as e:
            print(f"  AVISO: ficha do senador {cod}: {e}", file=sys.stderr)
    con.commit()
    if pend:
        print(f"  UF preenchida para {ok} de {len(pend)} senadores sem UF")


def carregar_ceaps(con, ano):
    print(f"Senado: CEAPS {ano}...")
    try:
        dados = c.get(f"{ADM}/senadores/despesas_ceaps/{ano}", timeout=300).json()
    except Exception as e:
        print(f"  AVISO: nao consegui baixar CEAPS {ano}: {e}", file=sys.stderr)
        return False
    if isinstance(dados, dict):
        dados = next((v for v in dados.values() if isinstance(v, list)), [])
    lote = f"senado_ceaps:{ano}"
    con.execute("DELETE FROM gasto WHERE arquivo=?", (lote,))
    linhas, criados = [], 0
    for d in dados:
        cod = d.get("codSenador")
        if cod is None:
            continue
        pid = c.pessoa_por_fonte(con, "senado", cod)
        if pid is None:
            pid = c.criar_pessoa(con, "senado", cod, (d.get("nomeSenador") or f"Senador {cod}").title(), CARGO)
            garantir_mandato(con, pid, c.legislatura_de(int(d.get("ano") or ano), int(d.get("mes") or 6)), None, None)
            criados += 1
        try:
            v = float(d.get("valorReembolsado") or 0)
        except (TypeError, ValueError):
            v = 0.0
        linhas.append((pid, "senado_ceaps", int(d.get("ano") or ano), int(d.get("mes") or 0), (d.get("data") or "")[:10],
                       (d.get("tipoDespesa") or "(sem tipo)").strip().rstrip("."), d.get("fornecedor"), d.get("cpfCnpj"),
                       d.get("documento"), (d.get("detalhamento") or None), None, v, None, lote))
    con.executemany(
        """INSERT INTO gasto (pessoa_id, fonte, ano, mes, data, categoria, fornecedor, cnpj_cpf,
                              documento, descricao, unidade, valor, url, arquivo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", linhas)
    c.log(con, "senado", "ceaps", ano, len(linhas))
    print(f"  {ano}: {len(linhas)} despesas ({criados} senadores criados a partir das despesas)")
    return True


def rodar(con, anos, so_gastos=False):
    if not so_gastos:
        carregar_senadores(con)
    for ano in anos:
        carregar_ceaps(con, ano)
    completar_uf(con)
