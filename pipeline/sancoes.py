"""Cadastros de sancoes do Portal da Transparencia: CEIS (empresas inidoneas/suspensas), CNEP (Lei Anticorrupcao) e
CEPIM (entidades sem fins lucrativos impedidas de receber recursos federais). Guardamos so quem aparece como recebedor de emendas.
Estar no cadastro e um fato publico sobre o CNPJ; nao diz que a emenda foi irregular nem a data em que a sancao valia."""
import io
import sys
import zipfile
from datetime import date, timedelta

from . import common as c
from .emendas import _achar, _fluxo_csv

BASE = "https://portaldatransparencia.gov.br/download-de-dados/{cad}/{data}"
CADASTROS = ("ceis", "cnep", "cepim")


def _baixar(cad):
    hoje = date.today()
    for d in range(0, 21):
        cand = (hoje - timedelta(days=d)).strftime("%Y%m%d")
        try:
            r = c.get(BASE.format(cad=cad, data=cand), timeout=300, rapido=True)
            z = zipfile.ZipFile(io.BytesIO(r.content))
            print(f"  {cad.upper()} baixado ({cand})")
            return z
        except Exception:
            continue
    return None


def rodar(con):
    docs = {"".join(ch for ch in (r[0] or "") if ch.isdigit()).zfill(14) for r in con.execute("SELECT DISTINCT documento FROM emenda_favorecido")}
    docs.discard("00000000000000")
    if not docs:
        print("  AVISO: sem recebedores de emendas no banco; rode antes a etapa de emendas", file=sys.stderr)
        return 0
    linhas = []
    for cad in CADASTROS:
        z = _baixar(cad)
        if z is None:
            print(f"  AVISO: nao consegui baixar o cadastro {cad.upper()}", file=sys.stderr)
            continue
        nome = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
        if not nome:
            print(f"  AVISO: {cad.upper()} sem csv: {z.namelist()}", file=sys.stderr)
            continue
        cab, leitor = _fluxo_csv(z, nome)
        print(f"  Colunas do {cad.upper()}: {cab}")
        i_doc = _achar(cab, ("cnpj", "sancionado"), ("cpf", "cnpj"), ("cnpj",))
        i_nom = _achar(cab, ("nome", "sancionado"), ("razao",), ("nome",))
        i_cat = _achar(cab, ("categoria",), ("motivo",))
        i_ini = _achar(cab, ("inicio", "sancao"), ("inicio",))
        i_fim = _achar(cab, ("final", "sancao"), ("fim",))
        i_org = _achar(cab, ("orgao", "sancionador"), ("orgao",))
        if i_doc is None:
            print(f"  AVISO: coluna de documento do {cad.upper()} nao reconhecida", file=sys.stderr)
            continue

        def cel(l, i):
            return l[i].strip() if i is not None and i < len(l) else ""
        n = 0
        for l in leitor:
            d = "".join(ch for ch in cel(l, i_doc) if ch.isdigit())
            if len(d) == 14 and d in docs:
                linhas.append((d, cad.upper(), cel(l, i_cat) or None, cel(l, i_ini) or None, cel(l, i_fim) or None, cel(l, i_org) or None, cel(l, i_nom) or None))
                n += 1
        print(f"  {cad.upper()}: {n} registros de recebedores de emendas")
    if linhas:
        con.execute("DELETE FROM sancao")
        con.executemany("INSERT INTO sancao VALUES (?,?,?,?,?,?,?)", linhas)
        c.log(con, "sancoes", "ceis_cnep_cepim", None, len(linhas))
        con.commit()
    print(f"Sancoes: {len(linhas)} registros de {len({l[0] for l in linhas})} recebedores")
    return len(linhas)
