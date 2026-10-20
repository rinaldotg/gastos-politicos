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

# Emendas com favorecidos (com ano do pagamento) e convenios
import io as _io, zipfile as _zf
def _zip_multi(arquivos):
    b = _io.BytesIO()
    with _zf.ZipFile(b, "w") as z:
        for n, t in arquivos.items():
            z.writestr(n, t.encode("latin-1"))
    class R: content = b.getvalue()
    return R()
fav = ("Código da Emenda;Código do Autor da Emenda;Nome do Autor da Emenda;Número da emenda;Tipo de Emenda;Ano/Mês;Código do Favorecido;Favorecido;Natureza Jurídica;Tipo Favorecido;UF Favorecido;Município Favorecido;Valor Recebido\n"
       "1;9;FULANO DE TAL;100;x;2023/05;11222333000144;PREFEITURA X;a;Pessoa Jurídica;SP;Santos;100,00\n"
       "1;9;FULANO DE TAL;100;x;2024/01;11222333000144;PREFEITURA X;a;Pessoa Jurídica;SP;Santos;50,00\n")
cv = ("Código da Emenda;Número Convênio;Convenente;Objeto Convênio;Situação Convênio;Valor Convênio;Valor Liberado;Data Início Vigência;Data Fim Vigência\n"
      "1;123456;PREFEITURA X;Construcao de ubs;Em execução;1.000,00;400,00;01/02/2023;01/02/2025\n")
cad = ("NÚMERO CONVÊNIO;SITUAÇÃO CONVÊNIO;VALOR LIBERADO;DATA INÍCIO VIGÊNCIA;DATA FIM VIGÊNCIA\n123456;Em execução;400,00;01/02/2023;01/02/2025\n")
c.get = lambda *a, **k: _zip_multi({"EmendasParlamentares.csv": em, "EmendasParlamentares_PorFavorecido.csv": fav, "EmendasParlamentares_Convenios.csv": cv})
emendas.carregar(con, 2014)
print(con.execute("select codigo,documento,valor,ano from emenda_favorecido").fetchall(), con.execute("select * from emenda_convenio").fetchall())

from pipeline import orcamento
ex = ("Nome Órgão Superior;Nome Órgão;Nome Programa Orçamentário;Nome Ação;Valor Empenhado (R$);Valor Liquidado (R$);Valor Pago (R$)\n"
      "Presidência da República;Secom;Comunicação;Publicidade;1.000,00;500,00;400,00\n"
      "Presidência da República;Secom;Comunicação;Publicidade;200,00;0,00;0,00\n"
      "Ministério da Saúde;FNS;SUS;X;9,00;9,00;9,00\n")
ex = ex.replace("Valor Pago (R$)", "Nome Grupo de Despesa;Modalidade da Despesa;Nome Elemento de Despesa;Valor Pago (R$);Valor Restos a Pagar Pagos (R$)")
ex = "\n".join(l if i == 0 else l.rsplit(";", 1)[0] + ";Outras Despesas Correntes;Aplicação Direta;Material de Consumo;" + l.rsplit(";", 1)[1] + ";1,00" for i, l in enumerate(ex.splitlines())) + "\n"
c.get = lambda *a, **k: zipar("202301_Despesas.csv", ex, "latin-1")
print(orcamento.carregar_mes(con, ids, 2023, 1)[0], con.execute("select pessoa_id,programa,acao,empenhado,pago from orcamento_acao").fetchall())
print(con.execute("select ano,mes,orgao,bucket,pago,rap_pago from despesa_orgao").fetchall())

assert orcamento.bucket("Pessoal e Encargos Sociais", "Aplicação Direta", "Vencimentos e Vantagens Fixas - Pessoal Civil") == "pessoal_ativo"
assert orcamento.bucket("Pessoal e Encargos Sociais", "Aplicação Direta", "Aposentadorias, Reserva Remunerada e Reformas") == "inativos"
assert orcamento.bucket("Outras Despesas Correntes", "Aplicação Direta", "Outros Serviços de Terceiros - Pessoa Jurídica") == "custeio"
assert orcamento.bucket("Outras Despesas Correntes", "Transferências a Municípios", "Transferências a Municípios") == "programas"
assert orcamento.bucket("Outras Despesas Correntes", "Aplicação Direta", "Benefícios Previdenciários") == "programas"
assert orcamento.bucket("Juros e Encargos da Dívida", "Aplicação Direta", "Juros sobre a Dívida por Contrato") == "divida"
assert orcamento.bucket("Investimentos", "Aplicação Direta", "Obras e Instalações") == "programas"
print("bucket ok")

from pipeline import gabinete
con.execute("INSERT INTO pessoa (id, nome, cargo) VALUES (901, 'Delegado Francischini', 'deputado_federal'), (902, 'Beto Faro', 'senador')")
cam = ("Nome;Cargo;Lotação;Data de Nomeação\n"
       "ANA SOUZA;Secretário Parlamentar;GAB DEP DELEGADO FRANCISCHINI;01/03/2023\n"
       "JOAO LIMA;Secretário Parlamentar;Gabinete do Deputado Fulano de Tal;15/05/2022\n"
       "DELEGADO FRANCISCHINI;Deputado;GAB DEP DELEGADO FRANCISCHINI;01/02/2023\n"
       "MARIA RH;Analista;Diretoria de Pessoal;01/01/2010\n"
       "PEDRO X;Secretário Parlamentar;Gabinete do Deputado Inexistente;01/01/2024\n").encode("latin-1")
sen = ("SERVIDOR;CARGO;LOTAÇÃO;ADMISSÃO\nCARLA M;Assessor Parlamentar;1.2.3.GSBFARO - GABINETE DO SENADOR BETO FARO;2023-02-01\n").encode("utf-8")
resp = lambda b: types.SimpleNamespace(content=b)
import types
c.get = lambda u, *a, **k: resp(cam if "camara" in u else sen)
gabinete.rodar(con)
print(con.execute("select pessoa_id, nome, cargo, nomeacao, fonte from gabinete_pessoa order by 1,2").fetchall())
assert len(con.execute("select * from gabinete_pessoa").fetchall()) == 3

# ---- remuneracao dos assessores (Senado) ----
from pipeline import remuneracao
_ss = "Ano;Mes;Nome;Sequencial;Tipo Folha;Remuneração Básica;Vantagens Pessoais;Função Comissionada;Gratificação Natalina;Horas Extras;Outras Eventuais;Abono Permanência;Vantagens Indenizatórias;Remuneração Líquida\n" + \
      "2026;3;CARLA M;1;Normal;5.000,00;100,00;2.000,00;0,00;0,00;0,00;0,00;900,00;6.000,00\n2026;3;CARLA M;1;Suplementar;0,00;0,00;0,00;1.000,50;0,00;0,00;0,00;0,00;900,00\n2026;3;OUTRA PESSOA;2;Normal;9.000,00;0;0;0;0;0;0;0;8.000,00\n"
def _get_rem(u, *a, **k):
    if "servidores/remuneracoes/2026/3" in u and "formato=csv" in u:
        return types.SimpleNamespace(content=_ss.encode("latin-1"))
    raise Exception("404")
_old_get = c.get; c.get = _get_rem
n_rem = remuneracao.rodar(con)
c.get = _old_get
rr = con.execute("select ano, mes, nome, bruto, fonte, pessoa_id from gabinete_remun").fetchall()
print(rr)
assert rr == [(2026, 3, "CARLA M", 8100.5, "gab_senado", 902)]

# ---- partidos (TSE) ----
import io as _io, zipfile as _zf
from pipeline import partidos
def _zip(arqs):
    b = _io.BytesIO()
    with _zf.ZipFile(b, "w") as z:
        for n, t in arqs.items():
            z.writestr(n, t.encode("latin-1"))
    return b.getvalue()
zorg = _zip({
    "receitas_orgaos_partidarios_2022_BRASIL.csv": 'SG_PARTIDO;DS_FONTE_RECEITA;VR_RECEITA\n"PT";"Fundo Especial de Financiamento de Campanha";"1000000,50"\n"PMDB";"Fundo Partidário";"500,00"\n',
    "despesas_contratadas_orgaos_partidarios_2022_BRASIL.csv": 'SG_PARTIDO;DS_ORIGEM_DESPESA;NM_FORNECEDOR;NR_CPF_CNPJ_FORNECEDOR;VR_DESPESA_CONTRATADA\n"PT";"Publicidade";"GRAFICA X LTDA";"11.222.333/0001-44";"200,00"\n"PT";"Serviços";"JOAO DA SILVA";"12345678901";"50,00"\n',
    "despesas_pagas_orgaos_partidarios_2022_BRASIL.csv": 'SG_PARTIDO;DS_ORIGEM_DESPESA;VR_DESPESA_PAGA\n"PT";"Publicidade";"999,00"\n'})
zcan = _zip({"receitas_candidatos_2022_BRASIL.csv": 'SG_PARTIDO;NM_CANDIDATO;DS_CARGO;SG_UF;SQ_CANDIDATO;DS_FONTE_RECEITA;VR_RECEITA\n"PT";"MARIA CAND";"Deputado Federal";"SP";"1";"Fundo Especial de Financiamento de Campanha";"300,00"\n"PT";"MARIA CAND";"Deputado Federal";"SP";"1";"Recursos de pessoas físicas";"100,00"\n',
             "despesas_contratadas_candidatos_2022_BRASIL.csv": 'SG_PARTIDO;DS_ORIGEM_DESPESA;NM_FORNECEDOR;NR_CPF_CNPJ_FORNECEDOR;VR_DESPESA_CONTRATADA\n"PT";"Publicidade";"GRAFICA X LTDA";"11222333000144";"70,00"\n'})
zanu = _zip({"receitas_partidos_2023.csv": 'SG_PARTIDO;DS_TIPO_RECEITA;VR_RECEITA\n"PL";"Fundo Partidário";"9000,00"\n',
             "despesas_partidos_2023.csv": 'SG_PARTIDO;DS_TIPO_DESPESA;NM_FORNECEDOR;NR_CPF_CNPJ_FORNECEDOR;VR_DESPESA\n"PL";"Despesas com pessoal";"MARIA FUNC";"11122233344";"4000,00"\n"PL";"Serviços";"EMPRESA Z SA";"99888777000166";"500,00"\n'})
class _R:
    def __init__(s, b): s.b = b
    def iter_content(s, n): yield s.b
partidos.ANOS_CAMPANHA = (2022,); partidos.ANOS_ANUAL = (2023,)
partidos._recursos = lambda q: [("https://x/prestacao_contas_anual_partidaria_2023.zip", "")] if "anual" in q or "partidaria" in q else []
def _get(u, *a, **k):
    if "anual_partidaria" in u or "anual_partidaria" in u.replace("prestacao_contas_",""): return _R(zanu)
    if "candidatos" in u: return _R(zcan)
    if "orgaos" in u: return _R(zorg)
    raise Exception("404")
c.get = _get
assert partidos.rodar(con) == 2
rec = {(r[0], r[1], r[2], r[3]): r[4] for r in con.execute("select ano, base, sigla, fonte, valor from partido_receita")}
print(rec)
assert rec[(2022, "campanha_orgao", "PT", "Fundo Especial de Financiamento de Campanha")] == 1000000.5
assert (2022, "campanha_orgao", "MDB", "Fundo Partidário") in rec  # PMDB renomeado
assert rec[(2023, "anual", "PL", "Fundo Partidário")] == 9000
rcb = con.execute("select base, sigla, documento, nome, classe, valor from partido_recebedor order by 1,2,5,6").fetchall()
print(rcb)
assert ("campanha_orgao", "PT", "11222333000144", "Grafica X Ltda", "PJ", 200.0) in rcb
assert any(r[4] == "PF" and r[3].startswith("Pessoas físicas") and r[5] == 50.0 for r in rcb)  # PF so agregada, sem nome
assert not any(r[0] == "campanha_candidato" and r[4] == "PJ" for r in rcb)  # abaixo do limiar de campanha de candidatos
assert not any("JOAO" in (r[3] or "").upper() or "MARIA FUNC" in (r[3] or "").upper() for r in rcb)
des = {(r[0], r[1], r[2]): r[3] for r in con.execute("select base, sigla, categoria, valor from partido_despesa")}
assert des[("campanha_orgao", "PT", "Publicidade")] == 200.0  # despesas_pagas nao somam em duplicidade
cand = con.execute("select sigla, candidato, fefc, total from partido_candidato").fetchall()
print(cand); assert cand == [("PT", "Maria Cand", 300.0, 400.0)]
assert partidos.rodar(con) == 0  # ja carregado (campanha) e anual recente (recarrega) -> ver abaixo
print("partidos ok")
