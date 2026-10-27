import sys
sys.path.insert(0, ".")
from pipeline import common as c, parentes

con = c.abrir_banco(":memory:")
con.execute("INSERT INTO pessoa (id, nome, cargo) VALUES (1,'Arthur Teste','deputado_federal'),(2,'Maria Exemplo','senador'),(3,'João Homônimo','deputado_federal')")
for pid, uf in ((1, "SP"), (2, "MG"), (3, "RJ")):
    con.execute("INSERT INTO mandato (pessoa_id, cargo, legislatura, uf, partido) VALUES (?,?,57,?,'XX')", (pid, "deputado_federal", uf))
for pid, doc, v in ((1, "11111111000191", 50000), (2, "33333333000193", 40000), (1, "44444444000144", 1000)):
    con.execute("INSERT INTO gasto (pessoa_id, fonte, ano, mes, fornecedor, cnpj_cpf, valor, arquivo) VALUES (?,'camara_ceap',2024,1,'F',?,?,'x')", (pid, doc, v))
S = lambda b8, nome, chave: con.execute("INSERT INTO rf_socio VALUES (?,?,?,?,?,?,?)", (b8, "2", nome, "***x***", "Sócio", "20100101", chave))
S("11111111", "ARTHUR TESTE DA SILVA", "pf:456789:arthur teste da silva")      # o proprio, mesmo CPF
S("22222222", "ARTHUR TESTE DA SILVA", "pf:999999:arthur teste da silva")      # homonimo com outro CPF: nao entra
S("33333333", "MARIA EXEMPLO FERREIRA", "pf:111111:maria exemplo ferreira")     # sem CPF no TSE: por nome
S("44444444", "JOSE TESTE DA SILVA", "pf:222222:jose teste da silva")           # pai do Arthur (Wikidata)
for i in range(4):                                                             # nome comum demais: descarta
    S(f"5555555{i}", "ANA COMUM", f"pf:10000{i}:ana comum")
S("66666666", "CARLOS SOBRINHO", "pf:333333:carlos sobrinho")                  # sem relacao declarada: nao entra
con.commit()
wiki = [("Q1", "Arthur Teste", "P22", "Q9", "Jose Teste da Silva"),
        ("Q2", "Maria Exemplo", "P26", "Q8", "Ana Comum"),
        ("Q3", "João Homônimo", "P26", "Q7", "Carlos Sobrinho"), ("Q4", "João Homônimo", "P26", "Q6", "Outra Pessoa")]   # rotulo repetido: ambiguo
civis = {1: {"arthur teste da silva": "456789"}, 2: {"maria exemplo ferreira": ""}}
r = parentes.achar(con, civis=civis, wiki=wiki)
tab = {(l[0], l[1], l[4], l[8]) for l in r}
print(sorted(tab))
assert (1, "próprio", "11111111", "cpf") in tab
assert not any(l[4] == "22222222" for l in r)                       # CPF diferente
assert (2, "próprio", "33333333", "nome") in tab
assert (1, "pai", "44444444", "wikidata") in tab
assert not any(l[4].startswith("5555555") for l in r)               # nome comum
assert not any(l[4] == "66666666" for l in r)                       # homonimo no Wikidata
l1 = next(l for l in r if l[4] == "11111111")
assert l1[9] == 50000 and l1[10] == 50000                            # pago pelo parlamentar e total
parentes._candidatos = lambda ano: []
parentes._wikidata = lambda: wiki
assert parentes.rodar(con, anos=()) >= 1
assert con.execute("SELECT COUNT(*) FROM parentesco_socio").fetchone()[0] >= 1
print("parentes ok")
