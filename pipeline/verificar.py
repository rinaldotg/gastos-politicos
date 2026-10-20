"""Confere o banco e gera resumo/ (CSVs pequenos) para enviar de volta.
Uso: python -m pipeline.verificar --db data\\gastos.db
"""
import argparse
import csv
import sqlite3
import zipfile
from datetime import date
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/gastos.db")
    ap.add_argument("--saida", default="resumo")
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    hoje = date.today()
    print("== Gastos por fonte e ano (linhas | meses distintos | total R$) ==")
    for fonte, ano, n, meses, tot in con.execute(
            "SELECT fonte, ano, COUNT(*), COUNT(DISTINCT mes), ROUND(SUM(valor),0) FROM gasto GROUP BY fonte, ano ORDER BY fonte, ano"):
        aviso = "  <-- FALTAM MESES?" if meses < 12 and ano < hoje.year else ""
        print(f"{fonte:13} {ano}  {n:>8}  {meses:>2}  {tot:>16,.0f}{aviso}")
    print("\n== Pessoas por cargo ==")
    for r in con.execute("SELECT cargo, COUNT(*) FROM pessoa GROUP BY cargo"):
        print(r)
    print("\n== Emendas por tipo (linhas | com parlamentar vinculado) ==")
    for r in con.execute("SELECT tipo, COUNT(*), SUM(pessoa_id IS NOT NULL) FROM emenda GROUP BY tipo ORDER BY 2 DESC"):
        print(r)
    print("\n== Orcamento da Presidencia por ano (R$ pago) ==")
    for r in con.execute("SELECT ano, COUNT(*), ROUND(SUM(pago),0) FROM orcamento_acao GROUP BY ano"):
        print(r)

    consultas = {
        "pessoa": """SELECT p.id, p.nome, p.cargo,
                        (SELECT id_externo FROM pessoa_fonte f WHERE f.pessoa_id=p.id AND f.fonte IN ('camara','senado') LIMIT 1) id_externo,
                        (SELECT uf FROM mandato m WHERE m.pessoa_id=p.id AND uf IS NOT NULL ORDER BY legislatura DESC LIMIT 1) uf,
                        (SELECT partido FROM mandato m WHERE m.pessoa_id=p.id AND partido IS NOT NULL ORDER BY legislatura DESC LIMIT 1) partido
                     FROM pessoa p""",
        "mandato": "SELECT pessoa_id, cargo, legislatura, uf, partido, data_inicio, data_fim FROM mandato",
        "gasto_ano_categoria": "SELECT pessoa_id, fonte, ano, categoria, ROUND(SUM(valor),2) total, COUNT(*) n FROM gasto GROUP BY 1,2,3,4",
        "gasto_mensal": "SELECT pessoa_id, ano, mes, ROUND(SUM(valor),2) total FROM gasto GROUP BY 1,2,3",
        "gasto_mes_categoria": "SELECT pessoa_id, ano, mes, categoria, ROUND(SUM(valor),2) total FROM gasto WHERE mes IS NOT NULL GROUP BY 1,2,3,4",
        "top_fornecedores": """SELECT * FROM (SELECT pessoa_id, fornecedor, cnpj_cpf, ROUND(SUM(valor),2) total, COUNT(*) n,
                       ROW_NUMBER() OVER (PARTITION BY pessoa_id ORDER BY SUM(valor) DESC) pos
                       FROM gasto WHERE fornecedor IS NOT NULL AND fornecedor<>'' GROUP BY pessoa_id, fornecedor, cnpj_cpf) WHERE pos<=20""",
        "fornecedor_ano_pessoa": """SELECT * FROM (SELECT pessoa_id, ano, fornecedor, ROUND(SUM(valor),2) total, COUNT(*) n,
                       ROW_NUMBER() OVER (PARTITION BY pessoa_id, ano ORDER BY SUM(valor) DESC) pos
                       FROM gasto WHERE fornecedor IS NOT NULL AND fornecedor<>'' GROUP BY pessoa_id, ano, fornecedor) WHERE pos<=15""",
        "partido_receita": "SELECT ano, base, sigla, fonte, valor, n FROM partido_receita",
        "partido_despesa": "SELECT ano, base, sigla, categoria, valor, n FROM partido_despesa",
        "partido_recebedor": "SELECT ano, base, sigla, documento, nome, classe, valor, n FROM partido_recebedor",
        "partido_candidato": "SELECT ano, sigla, candidato, cargo, uf, fefc, total FROM partido_candidato",
        "gabinete_pessoa": "SELECT pessoa_id, nome, cargo, lotacao, nomeacao, fonte FROM gabinete_pessoa ORDER BY pessoa_id, cargo, nome",
        "top_fornecedores_ano": """SELECT * FROM (SELECT pessoa_id, ano, fornecedor, cnpj_cpf, ROUND(SUM(valor),2) total,
                       ROW_NUMBER() OVER (PARTITION BY pessoa_id, ano ORDER BY SUM(valor) DESC) pos
                       FROM gasto WHERE fonte NOT LIKE 'pres%' AND fornecedor IS NOT NULL AND fornecedor<>''
                       AND LENGTH(REPLACE(REPLACE(REPLACE(COALESCE(cnpj_cpf,''),'.',''),'/',''),'-',''))=14
                       GROUP BY pessoa_id, ano, fornecedor, cnpj_cpf) WHERE pos<=3""",
        "presidencia_unidades": "SELECT pessoa_id, fonte, ano, unidade, categoria, ROUND(SUM(valor),2) total, COUNT(*) n FROM gasto WHERE fonte LIKE 'pres%' GROUP BY 1,2,3,4,5",
        "emenda_agregado": "SELECT pessoa_id, tipo, ano, ROUND(SUM(empenhado),2) empenhado, ROUND(SUM(liquidado),2) liquidado, ROUND(SUM(pago),2) pago, COUNT(*) n, ROUND(SUM(rap_inscrito),2) rap_inscrito, ROUND(SUM(rap_cancelado),2) rap_cancelado, ROUND(SUM(rap_pago),2) rap_pago FROM emenda GROUP BY 1,2,3",
        "emenda_detalhe": """SELECT pessoa_id, codigo, numero, tipo, ano, uf, municipio, localidade, funcao, subfuncao, programa, acao,
                       ROUND(empenhado,2) empenhado, ROUND(liquidado,2) liquidado, ROUND(pago,2) pago
                       FROM emenda WHERE pessoa_id IS NOT NULL""",
        "emenda_favorecido": "SELECT codigo, favorecido, documento, tipo, uf, municipio, ROUND(valor,2) valor, n, ano FROM emenda_favorecido ORDER BY codigo, valor DESC",
        "emenda_convenio": "SELECT codigo, numero, convenente, objeto, situacao, ROUND(valor,2) valor, ROUND(liberado,2) liberado, inicio, fim, publicacao FROM emenda_convenio",
        "obra": "SELECT id_unico, nome, situacao, uf, especie, natureza, tipo, subtipo, ROUND(valor,2) valor, ini_prev, fim_prev, ini_efetiva, fim_efetiva, data_situacao, executor_cnpj, executor_nome, repassador FROM obra",
        "atuacao": "SELECT pessoa_id, ano, fonte, proposicoes, pl, pec, normas, votos, votacoes_janela FROM atuacao",
        "sancao": "SELECT documento, cadastro, categoria, inicio, fim, orgao, nome FROM sancao",
        "tce_fornecedor": "SELECT slug, ano, documento, fornecedor, classe, ROUND(pago,2) pago, ROUND(pago_federal,2) pago_federal, ROUND(pago_dispensa,2) pago_dispensa, n FROM tce_fornecedor",
        "despesa_orgao": "SELECT ano, orgao, bucket, MAX(mes) ate_mes, ROUND(SUM(empenhado),2) empenhado, ROUND(SUM(liquidado),2) liquidado, ROUND(SUM(pago),2) pago, ROUND(SUM(rap_pago),2) rap_pago FROM despesa_orgao GROUP BY ano, orgao, bucket",
        "despesa_orgao_meses": "SELECT ano, COUNT(DISTINCT mes) meses, MAX(mes) ate_mes FROM despesa_orgao GROUP BY ano",
        "tce_funcao": "SELECT slug, ano, funcao, fonte, ROUND(pago,2) pago, n FROM tce_funcao",
        "tce_pagamento": "SELECT slug, ano, documento, fornecedor, funcao, fonte, emenda, modalidade, historico, ROUND(pago,2) pago, n FROM tce_pagamento",
        "tce_carga": "SELECT slug, ano, municipio, linhas, carregado FROM tce_carga",
        "municipio_pop": "SELECT ibge, nome, uf, populacao, ano FROM municipio_pop",
        "emenda_funcao": "SELECT pessoa_id, ano, funcao, ROUND(SUM(pago),2) pago FROM emenda WHERE pessoa_id IS NOT NULL GROUP BY 1,2,3",
        "emenda_sem_autor": "SELECT tipo, CASE WHEN lower(autor) LIKE 'sem informa%' THEN 1 ELSE 0 END sem_info, ano, COUNT(*) n, ROUND(SUM(empenhado),2) empenhado, ROUND(SUM(pago),2) pago FROM emenda WHERE pessoa_id IS NULL GROUP BY 1,2,3",
        "emenda_sem_vinculo": "SELECT autor, tipo, COUNT(*) n, ROUND(SUM(pago),2) pago FROM emenda WHERE pessoa_id IS NULL GROUP BY 1,2 ORDER BY n DESC LIMIT 300",
        "orcamento_acao": "SELECT pessoa_id, ano, mes, orgao, programa, acao, ROUND(empenhado,2) empenhado, ROUND(liquidado,2) liquidado, ROUND(pago,2) pago FROM orcamento_acao",
        "coleta_log": "SELECT fonte, recurso, ano, registros, coletado_em FROM coleta_log",
    }
    out = Path(a.saida)
    out.mkdir(exist_ok=True)
    with zipfile.ZipFile(out / "resumo.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for nome, sql in consultas.items():
            cur = con.execute(sql)
            f = out / f"{nome}.csv"
            with open(f, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow([d[0] for d in cur.description])
                w.writerows(cur)
            z.write(f, f.name)
    print(f"\nGerado {out / 'resumo.zip'} - envie este arquivo.")


if __name__ == "__main__":
    main()
