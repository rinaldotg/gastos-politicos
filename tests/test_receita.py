import io, os, sys, tempfile, zipfile
sys.path.insert(0, ".")
from pipeline import common as c, receita

def zip_(pasta, nome, linhas):
    caminho = os.path.join(pasta, nome)
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("dados.csv", "\n".join(";".join(f'"{x}"' for x in l) for l in linhas).encode("latin-1"))

con = c.abrir_banco(":memory:")
con.execute("INSERT INTO pessoa (id, nome, cargo) VALUES (1,'Fulano','deputado_federal')")
for i, (doc, v) in enumerate([("11.111.111/0001-91", 50000), ("22222222000192", 40000), ("33333333000193", 10), ("123.456.789-09", 99999)]):
    con.execute("INSERT INTO gasto (pessoa_id, fonte, ano, mes, fornecedor, cnpj_cpf, valor, arquivo) VALUES (1,'camara_ceap',2024,1,?,?,?,'x')", (f"F{i}", doc, v))
con.commit()
assert set(receita.alvos_do_banco(con)) == {"11111111", "22222222"}

p = tempfile.mkdtemp()
# socios: 11111111 e 44444444 dividem o mesmo socio (nome + CPF mascarado); 55555555 tem homonimo com outro CPF
zip_(p, "Socios0.zip", [
    ["11111111", "2", "JOAO DA SILVA", "***123456**", "49", "20100101", "", "", "", "", ""],
    ["44444444", "2", "JOAO DA SILVA", "***123456**", "22", "20150101", "", "", "", "", ""],
    ["55555555", "2", "JOAO DA SILVA", "***999999**", "22", "20150101", "", "", "", "", ""],
    ["22222222", "1", "HOLDING X", "99999999000100", "22", "20100101", "", "", "", "", ""],
    ["66666666", "1", "HOLDING X", "99999999000100", "22", "20100101", "", "", "", "", ""],
    ["22222222", "2", "MARIA", "***111111**", "22", "20100101", "", "", "", "", ""],   # um so nome: nao liga
    ["77777777", "2", "MARIA", "***111111**", "22", "20100101", "", "", "", "", ""],
])
def est(b, ordem, dv, mat, sit, nome, logr, num, cep, uf="SP", mun="7107"):
    l = [""] * 30
    l[0], l[1], l[2], l[3], l[4], l[5], l[10], l[11] = b, ordem, dv, mat, nome, sit, "20100101", "4711301"
    l[13], l[14], l[15], l[16], l[17], l[18], l[19], l[20] = "RUA", logr, num, "SALA 1", "CENTRO", cep, uf, mun
    return l
zip_(p, "Estabelecimentos0.zip", [
    est("11111111", "0001", "91", "1", "02", "ALFA", "DAS FLORES", "100", "01001000"),
    est("22222222", "0001", "92", "1", "02", "BETA", "DO COMERCIO", "5", "02002000"),
    est("44444444", "0001", "44", "1", "02", "GAMA", "OUTRA", "9", "03003000"),
    est("88888888", "0001", "88", "1", "02", "VIZINHA", "DAS FLORES", "100", "01001000"),     # mesmo endereco da ALFA
    est("99999999", "0001", "99", "1", "08", "BAIXADA", "DAS FLORES", "100", "01001000"),     # baixada: nao entra
    est("77777777", "0001", "77", "1", "02", "SEMNUM", "S", "S/N", "04004000"),
])
zip_(p, "Empresas0.zip", [["11111111", "ALFA LTDA", "2062", "0", "5000", "01"], ["22222222", "BETA SA", "2054", "0", "10", "05"],
                          ["44444444", "GAMA LTDA", "2062", "0", "5", "01"], ["88888888", "VIZINHA ME", "2135", "0", "1", "01"],
                          ["66666666", "HOLDING FILHA", "2062", "0", "1", "01"]])
zip_(p, "Municipios.zip", [["7107", "SAO PAULO"]])
n = receita.rodar(con, pasta=p, baixar=False)
assert n == 2
rel = sorted(con.execute("SELECT alvo8, tipo, outro8 FROM rf_relacao").fetchall())
print(rel)
assert ("11111111", "socio", "44444444") in rel and ("11111111", "socio", "55555555") not in rel  # CPF parcial diferente
assert ("22222222", "socio", "66666666") in rel and not any(r[0] == "22222222" and r[2] == "77777777" for r in rel)
assert ("11111111", "end", "88888888") in rel and not any(r[2] == "99999999" for r in rel)  # baixada fora
assert con.execute("SELECT municipio FROM rf_estab WHERE cnpj='11111111000191'").fetchone()[0] == "SAO PAULO"
assert con.execute("SELECT razao FROM rf_empresa WHERE cnpj8='44444444'").fetchone()[0] == "GAMA LTDA"
assert con.execute("SELECT qualificacao FROM rf_socio WHERE cnpj8='11111111'").fetchone()[0] == "Sócio-administrador"
# formato novo dos socios (CNPJ completo na primeira coluna) tambem funciona
assert receita._dig("11111111000191")[:8] == "11111111"
print("receita ok")
