"""Populacao dos municipios (IBGE, API de agregados): para mostrar valores por habitante."""
import sys
import time

import requests

from . import common as c

_VERIFY = None
UFS = [11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53]
BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
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


def _por_uf(agregado, periodo, var):
    """Uma consulta por UF (respostas pequenas, mais resistentes a timeout)."""
    linhas, falhas = [], 0
    for uf in UFS:
        url = f"{BASE}/{agregado}/periodos/{periodo}/variaveis/{var}?localidades=N6[N3[{uf}]]"
        try:
            linhas.extend(_ler(_get(url, _VERIFY, 40).json()))
        except Exception as e:
            falhas += 1
            if falhas == 1:
                print(f"  AVISO: IBGE UF {uf}: {e}", file=sys.stderr)
            if falhas >= 3 and not linhas:
                break
    return linhas


def _sessao_ibge():
    """Verifica o TLS do IBGE completando a cadeia de certificados (o servidor nao envia o intermediario)."""
    try:
        return c.bundle_com_intermediarios("servicodados.ibge.gov.br")
    except Exception as e:
        print(f"  AVISO: nao consegui montar a cadeia de certificados do IBGE: {e}", file=sys.stderr)
        return None


def _get(url, verify, timeout):
    for i in range(3):
        try:
            r = requests.get(url, headers=c.HEADERS, timeout=timeout, verify=verify if verify else True)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if i == 2:
                raise
            time.sleep(3 * (i + 1))


def rodar(con):
    global _VERIFY
    _VERIFY = _sessao_ibge()
    tentativas = [(None, url, rot) for url, rot in FONTES] + [
        ((6579, "-1", 9324), None, "estimativa por UF"), ((4714, "2022", 93), None, "censo 2022 por UF")]
    for por_uf, url, rotulo in tentativas:
        try:
            linhas = _por_uf(*por_uf) if por_uf else _ler(_get(url, _VERIFY, 60).json())
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
