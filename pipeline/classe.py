"""Classifica um recebedor de recursos publicos pelo nome e documento: ente publico, empresa, entidade sem fins lucrativos...

E uma heuristica por nome (a fonte nao informa a natureza juridica). Serve para ORIENTAR a leitura, nao para afirmar:
quem nao se encaixa em nenhuma regra cai em "privado_outro" e o site avisa que o tipo nao foi identificado.
"""
import re
import unicodedata

BANCOS = {"00000000000191", "00360305000104", "07237373000120", "04902979000144"}
ROTULO = {
    "publico": "Ente público ou fundo público",
    "empresa": "Empresa privada",
    "entidade": "Entidade sem fins lucrativos",
    "privado_outro": "Entidade privada (tipo não identificado)",
    "pf": "Pessoa física ou sem identificação",
    "banco": "Banco público (intermediário)",
}
PRIVADOS = ("empresa", "entidade", "privado_outro")

_PUBLICO = re.compile(r"\b(MUNICIPIO|MUNICIPAL|PREFEITURA|ESTADO|GOVERNO|SECRETARIA|CAMARA|ASSEMBLEIA|TRIBUNAL|MINISTERIO|"
                      r"UNIVERSIDADE (FEDERAL|ESTADUAL|DE)|INSTITUTO FEDERAL|AUTARQUIA|CONSORCIO|DISTRITO FEDERAL|DEPARTAMENTO|"
                      r"SERVICO AUTONOMO|FNDE|FNS|COMANDO|POLICIA|CORPO DE BOMBEIROS|EXERCITO|MARINHA|AERONAUTICA|DEFENSORIA|"
                      r"PROCURADORIA|PREVIDENCIA|FUNDACAO NACIONAL|FUNDACAO ESTADUAL|FUNDACAO MUNICIPAL|UNIDADE GESTORA|SAMAE|SAAE|"
                      r"SERVICO MUNICIPAL|SERVICO NACIONAL|SERVICO SOCIAL)\b|^FUNDO\b")
_EMPRESA = re.compile(r"\b(LTDA|S/?A|S\.A|EIRELI|EPP|MEI|COMERCIO|INDUSTRIA|CONSTRUTORA|ENGENHARIA|SERVICOS|TECNOLOGIA|DISTRIBUIDORA|"
                      r"TRANSPORTES|MOTORS|AUTOMOVEIS|VEICULOS|MAQUINAS|EMPREENDIMENTOS|COMPANHIA|CIA|AGROPECUARIA|LOCACAO|CONSULTORIA|"
                      r"INCORPORADORA|EQUIPAMENTOS|MATERIAIS|PRODUTOS|COMUNICACAO|PUBLICIDADE)\b")
_ENTIDADE = re.compile(r"\b(ASSOCIACAO|INSTITUTO|FUNDACAO|ONG|ORGANIZACAO|SOCIEDADE|IRMANDADE|SANTA CASA|APAE|CENTRO|NUCLEO|IGREJA|"
                       r"CLUBE|SINDICATO|CONFEDERACAO|FEDERACAO|COOPERATIVA|CONSELHO|LIGA|HOSPITAL|MISSAO|PASTORAL|CASA DE|ACAO SOCIAL)\b")


def sem_acento(s):
    return re.sub(r"\s+", " ", "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")).upper().strip()


def classificar(nome, documento):
    d = re.sub(r"\D", "", documento or "")
    if d.zfill(14) in BANCOS and len(d) >= 11:
        return "banco"
    if len(d) != 14:
        return "pf"
    n = sem_acento(nome)
    if re.search(r"\bBANCO\b|CAIXA ECONOMICA|CORPORACAO ANDINA|CORREIOS", n):
        return "banco"  # bancos e estatais de servico: intermediarios, nao o destino final
    if _PUBLICO.search(n):
        return "publico"
    if re.search(r"\bSERVICO (SOCIAL|NACIONAL)\b", n):
        return "entidade"  # Sistema S (Sesc, Senac, Sesi...)
    if _EMPRESA.search(n):
        return "empresa"
    if _ENTIDADE.search(n):
        return "entidade"
    return "privado_outro"
