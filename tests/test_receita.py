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
    ["44444444", "2", "PEDRO LIMA", "***777777**", "22", "20150101", "", "", "", "", ""],      # outro socio da empresa ligada
    ["88888888", "2", "PEDRO LIMA", "***777777**", "22", "20150101", "", "", "", "", ""],      # liga a vizinha de endereco
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
outros = sorted(r[2] for r in con.execute("SELECT cnpj8, chave, nome FROM rf_socio WHERE cnpj8='44444444'"))
assert "PEDRO LIMA" in outros, outros
assert con.execute("SELECT COUNT(*) FROM rf_socio WHERE cnpj8='88888888' AND nome='PEDRO LIMA'").fetchone()[0] == 1
print("receita ok")

# ---- doacoes de campanha ----
from pipeline import doacoes
con.execute("INSERT INTO pessoa (id, nome, cargo) VALUES (2,'Beltrano Urna','deputado_federal')")
con.execute("INSERT INTO mandato (pessoa_id, cargo, legislatura, uf, partido) VALUES (2,'deputado_federal',57,'SP','XX')")
con.execute("INSERT INTO pessoa (id, nome, cargo) VALUES (3,'Outro Nome','senador')")
con.execute("INSERT INTO mandato (pessoa_id, cargo, legislatura, uf, partido) VALUES (3,'senador',57,'SP','YY')")
con.commit()
def _z(nome, texto):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z: z.writestr(nome, texto.encode("utf-8-sig"))
    return zipfile.ZipFile(io.BytesIO(b.getvalue()))
rec = ("SQ_CANDIDATO;NM_CANDIDATO;DS_CARGO;SG_UF;SG_PARTIDO;NR_CPF_CNPJ_DOADOR;NM_DOADOR;NM_DOADOR_RFB;VR_RECEITA\n"
       "1;BELTRANO DA SILVA;Deputado Federal;SP;XX;12345678909;JOAO DA SILVA;JOAO DA SILVA;1.500,00\n"        # socio (CPF com digitos centrais 456789? ver abaixo)
       "1;BELTRANO DA SILVA;Deputado Federal;SP;XX;11111111000191;ALFA LTDA;ALFA LTDA;2.000,50\n"             # empresa 11111111
       "9;OUTRO;Governador;SP;XX;11111111000191;ALFA LTDA;ALFA LTDA;999,00\n"                                 # cargo fora
       "2;OUTRO NOME;Senador;SP;YY;99999999999;FULANO QUALQUER;FULANO QUALQUER;50,00\n")                      # doador desconhecido
cand = "SQ_CANDIDATO;NM_CANDIDATO;NM_URNA_CANDIDATO;SG_UF\n1;BELTRANO DA SILVA;BELTRANO URNA;SP\n2;OUTRO NOME;OUTRO NOME;SP\n"
_antes = doacoes._baixar
def _fake(u):
    return _z("receitas_candidatos_2022_BRASIL.csv", rec) if "prestacao" in u else _z("consulta_cand_2022_BRASIL.csv", cand)
doacoes._baixar = _fake
# CPF do socio JOAO DA SILVA tem digitos centrais 123456 (na Receita: ***123456**) -> CPF completo 000123456xx
rec = rec.replace("12345678909", "00012345600")
_fake2 = lambda u: _z("receitas_candidatos_2022_BRASIL.csv", rec) if "prestacao" in u else _z("consulta_cand_2022_BRASIL.csv", cand)
doacoes._baixar = _fake2
n = doacoes.rodar(con, anos=(2022,))
doacoes._baixar = _antes
print(con.execute("SELECT * FROM doacao_campanha").fetchall())
assert n == 2
r = {(x[0], x[1]): x for x in con.execute("SELECT tipo, chave, doador, pessoa_id, valor FROM doacao_campanha")}
assert r[("socio", "pf:123456:joao da silva")][3] == 2 and r[("socio", "pf:123456:joao da silva")][4] == 1500.0
assert r[("empresa", "11111111")][4] == 2000.5
print("doacoes ok")
