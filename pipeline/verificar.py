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
                        (SELECT uf FROM mandato m WHERE m.pessoa_id=p.id AND uf IS NOT NULL ORDER BY legislatura DESC LIMIT 1) uf,
                        (SELECT partido FROM mandato m WHERE m.pessoa_id=p.id AND partido IS NOT NULL ORDER BY legislatura DESC LIMIT 1) partido
                     FROM pessoa p""",
        "mandato": "SELECT pessoa_id, cargo, legislatura, uf, partido, data_inicio, data_fim FROM mandato",
        "gasto_ano_categoria": "SELECT pessoa_id, fonte, ano, categoria, ROUND(SUM(valor),2) total, COUNT(*) n FROM gasto GROUP BY 1,2,3,4",
        "gasto_mensal": "SELECT pessoa_id, ano, mes, ROUND(SUM(valor),2) total FROM gasto GROUP BY 1,2,3",
        "top_fornecedores": """SELECT * FROM (SELECT pessoa_id, fornecedor, cnpj_cpf, ROUND(SUM(valor),2) total, COUNT(*) n,
                       ROW_NUMBER() OVER (PARTITION BY pessoa_id ORDER BY SUM(valor) DESC) pos
                       FROM gasto WHERE fornecedor IS NOT NULL AND fornecedor<>'' GROUP BY pessoa_id, fornecedor, cnpj_cpf) WHERE pos<=20""",
        "presidencia_unidades": "SELECT pessoa_id, fonte, ano, unidade, categoria, ROUND(SUM(valor),2) total, COUNT(*) n FROM gasto WHERE fonte LIKE 'pres%' GROUP BY 1,2,3,4,5",
        "emenda_agregado": "SELECT pessoa_id, tipo, ano, ROUND(SUM(empenhado),2) empenhado, ROUND(SUM(liquidado),2) liquidado, ROUND(SUM(pago),2) pago, COUNT(*) n FROM emenda GROUP BY 1,2,3",
        "emenda_funcao": "SELECT pessoa_id, ano, funcao, ROUND(SUM(pago),2) pago FROM emenda WHERE pessoa_id IS NOT NULL GROUP BY 1,2,3",
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
