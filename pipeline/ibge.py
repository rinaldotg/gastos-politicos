"""Populacao dos municipios (IBGE, API de agregados): para mostrar valores por habitante."""
import sys

from . import common as c

FONTES = [
    # estimativas anuais da populacao residente: periodo mais recente
    ("https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/-1/variaveis/9324?localidades=N6[all]", "estimativa"),
    # Censo 2022
    ("https://servicodados.ibge.gov.br/api/v3/agregados/4714/periodos/2022/variaveis/93?localidades=N6[all]", "censo 2022"),
]


def _ler(j):
    out = []
    for var in j or []:
        for res in var.get("resultados", []):
            for s in res.get("series", []):
                loc = s.get("localidade", {})
                serie = s.get("serie", {})
                if not serie:
                    continue
                ano = max(serie)
                try:
                    pop = int(float(serie[ano]))
                except (TypeError, ValueError):
                    continue
                nome = loc.get("nome") or ""
                if " - " not in nome:
                    continue
                mun, uf = nome.rsplit(" - ", 1)
                out.append((str(loc.get("id")), mun.strip(), uf.strip()[:2].upper(), pop, int(ano)))
    return out


def rodar(con):
    for url, rotulo in FONTES:
        try:
            linhas = _ler(c.get(url, timeout=300).json())
        except Exception as e:
            print(f"  AVISO: populacao do IBGE ({rotulo}) indisponivel: {e}", file=sys.stderr)
            continue
        if len(linhas) > 1000:
            con.execute("DELETE FROM municipio_pop")
            con.executemany("INSERT INTO municipio_pop (ibge, nome, uf, populacao, ano) VALUES (?,?,?,?,?)", linhas)
            c.log(con, "ibge", "populacao", None, len(linhas))
            con.commit()
            print(f"Populacao: {len(linhas)} municipios ({rotulo}, ano {linhas[0][4]})")
            return len(linhas)
        print(f"  AVISO: resposta do IBGE ({rotulo}) com poucos municipios ({len(linhas)})", file=sys.stderr)
    print("  AVISO: sem populacao dos municipios; valores por habitante nao serao exibidos", file=sys.stderr)
    return 0
