import io, zipfile, types, sys
sys.path.insert(0, ".")
from pipeline import common as c, camara, presidencia

def zipar(nome, texto, enc="utf-8-sig"):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z: z.writestr(nome, texto.encode(enc))
    return types.SimpleNamespace(content=b.getvalue())

con = c.abrir_banco(":memory:")
# Camara
csv = ('"txNomeParlamentar";"ideCadastro";"nuLegislatura";"sgUF";"sgPartido";"txtDescricao";"txtFornecedor";"txtCNPJCPF";"txtNumero";"datEmissao";"vlrLiquido";"numMes";"numAno";"urlDocumento"\n'
       '"FULANO DE TAL";"123";"55";"SP";"PT";"COMBUSTÍVEIS E LUBRIFICANTES.";"POSTO X";"111";"9";"2015-03-02T00:00:00";"150,50";"3";"2015";""\n')
c.get = lambda *a, **k: zipar("Ano-2015.csv", csv)
camara.carregar_cota(con, 2015)
print(con.execute("select p.nome,g.categoria,g.valor,g.fonte,g.ano from gasto g join pessoa p on p.id=g.pessoa_id").fetchall())
# Presidencia
ids = presidencia.garantir_presidentes(con)
cp = ("NOME ÓRGÃO SUPERIOR;DATA TRANSAÇÃO;TRANSAÇÃO;NOME FAVORECIDO;CNPJ OU CPF FAVORECIDO;NOME UNIDADE GESTORA;VALOR TRANSAÇÃO\n"
      "Presidência da República;15/06/2019;Compra a vista;PADARIA;222;Gabinete Pessoal;1.234,56\n"
      "Ministério da Saúde;15/06/2019;Compra;X;1;U;9,00\n")
c.get = lambda *a, **k: zipar("201906_CPGF.csv", cp, "latin-1")
print(presidencia.carregar_cpgf_mes(con, ids, 2019, 6)[:2])
vg = ("Nome do órgão superior;Período - Data de início;Descrição Função;Destinos;Motivo;Nome órgão solicitante;Número da Proposta (PCDP);Valor diárias;Valor passagens;Valor outros gastos;Valor devolução\n"
      "Presidência da República;10/02/2023;Assessor;Brasília;Reunião;Gabinete;P1;100,00;200,00;0,00;50,00\n")
c.get = lambda *a, **k: zipar("2023_Viagem.csv", vg, "latin-1")
print(presidencia.carregar_viagens_ano(con, ids, 2023)[:2])
print(con.execute("select pessoa_id,fonte,categoria,valor from gasto where fonte like 'pres%'").fetchall())

# Emendas
from pipeline import emendas
em = ("Código da Emenda;Ano da Emenda;Tipo de Emenda;Nome do Autor da Emenda;Número da emenda;UF;Município;Nome Função;Nome Subfunção;Valor Empenhado;Valor Liquidado;Valor Pago\n"
      "1;2023;Emenda Individual - Transferências Especiais;FULANO DE TAL;100;SP;Santos;Saúde;Atenção básica;1.000,00;800,00;500,00\n"
      "2;2023;Emenda de Bancada;BANCADA DE SP;200;SP;Santos;Saúde;X;10,00;0,00;0,00\n"
      "3;2012;Emenda Individual;FULANO DE TAL;1;SP;X;Y;Z;1,00;1,00;1,00\n")
c.get = lambda *a, **k: zipar("EmendasParlamentares.csv", em, "latin-1")
emendas.carregar(con, 2014)
print(con.execute("select pessoa_id,autor,tipo,pago from emenda").fetchall())

from pipeline import orcamento
ex = ("Nome Órgão Superior;Nome Órgão;Nome Programa Orçamentário;Nome Ação;Valor Empenhado (R$);Valor Liquidado (R$);Valor Pago (R$)\n"
      "Presidência da República;Secom;Comunicação;Publicidade;1.000,00;500,00;400,00\n"
      "Presidência da República;Secom;Comunicação;Publicidade;200,00;0,00;0,00\n"
      "Ministério da Saúde;FNS;SUS;X;9,00;9,00;9,00\n")
c.get = lambda *a, **k: zipar("202301_Despesas.csv", ex, "latin-1")
print(orcamento.carregar_mes(con, ids, 2023, 1)[0], con.execute("select pessoa_id,programa,acao,empenhado,pago from orcamento_acao").fetchall())
