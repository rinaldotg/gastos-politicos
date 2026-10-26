"""Orquestrador: python -m pipeline.run --db data/gastos.db [--desde 2014] [--so camara senado presidencia]"""
import argparse
from datetime import datetime

from . import camara, common as c, emendas, ibge, obras, orcamento, presidencia, senado, tcesp, atuacao, sancoes, gabinete, partidos, remuneracao, candidaturas, receita


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/gastos.db")
    ap.add_argument("--desde", type=int, default=c.ANO_INICIAL)
    ap.add_argument("--ate", type=int, default=datetime.now().year)
    ap.add_argument("--so", nargs="*", choices=["camara", "senado", "presidencia", "emendas", "orcamento", "obras", "ibge", "tcesp", "atuacao", "sancoes", "gabinete", "remuneracao", "partidos", "candidaturas", "receita"])
    ap.add_argument("--rfb-url", default=None, help="modelo do endereco dos zips da Receita, com {mes} e {arq}")
    ap.add_argument("--pular-cadastro", action="store_true", help="nao recarrega listas de deputados/senadores")
    ap.add_argument("--recarregar-desde", type=int, default=None, help="anos do Portal anteriores a este e ja carregados sao pulados (padrao: ano passado)")
    a = ap.parse_args()
    anos = list(range(a.desde, a.ate + 1))
    con = c.abrir_banco(a.db)
    con.execute("DELETE FROM gasto WHERE ano < ?", (c.ANO_INICIAL,))  # lancamentos de extratos de 2014 com data anterior
    con.commit()
    etapas = a.so or ["camara", "senado", "presidencia", "emendas", "orcamento", "obras", "ibge", "tcesp", "atuacao", "sancoes", "gabinete", "remuneracao", "partidos", "candidaturas"]  # "receita" so quando pedida (baixa ~8 GB)
    if "camara" in etapas:
        camara.rodar(con, anos, so_gastos=a.pular_cadastro)
    if "senado" in etapas:
        senado.rodar(con, anos, so_gastos=a.pular_cadastro)
    if "presidencia" in etapas:
        presidencia.rodar(con, anos, a.recarregar_desde)
    if "orcamento" in etapas:
        orcamento.rodar(con, anos, a.recarregar_desde)
    if "emendas" in etapas:
        emendas.rodar(con, a.desde)
    if "obras" in etapas:
        obras.rodar(con)
    if "ibge" in etapas:
        ibge.rodar(con)
    if "tcesp" in etapas:
        tcesp.rodar(con)
    if "atuacao" in etapas:
        atuacao.rodar(con)
    if "sancoes" in etapas:
        sancoes.rodar(con)
    if "partidos" in etapas:
        partidos.rodar(con, recarregar=bool(a.recarregar_desde))
    if "gabinete" in etapas:
        gabinete.rodar(con)
    if "remuneracao" in etapas:
        remuneracao.rodar(con)
    if "candidaturas" in etapas:
        candidaturas.rodar(con)
    if "receita" in etapas:
        receita.rodar(con, url_modelo=a.rfb_url)
    print("Concluido.")


if __name__ == "__main__":
    main()
