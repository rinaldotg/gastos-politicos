-- Modelo unico de gastos. Uma linha de "gasto" = uma despesa individual.
CREATE TABLE IF NOT EXISTS pessoa (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    cargo TEXT NOT NULL                -- 'deputado_federal' | 'senador' | 'presidente'
);
CREATE TABLE IF NOT EXISTS pessoa_fonte (
    pessoa_id INTEGER NOT NULL REFERENCES pessoa(id),
    fonte TEXT NOT NULL,               -- 'camara' | 'senado' | 'presidencia'
    id_externo TEXT NOT NULL,
    PRIMARY KEY (fonte, id_externo)
);
CREATE TABLE IF NOT EXISTS mandato (
    id INTEGER PRIMARY KEY,
    pessoa_id INTEGER NOT NULL REFERENCES pessoa(id),
    cargo TEXT NOT NULL,
    legislatura INTEGER NOT NULL,      -- 0 para presidente
    uf TEXT,
    partido TEXT,
    data_inicio TEXT,
    data_fim TEXT,
    UNIQUE (pessoa_id, cargo, legislatura)
);
CREATE TABLE IF NOT EXISTS gasto (
    id INTEGER PRIMARY KEY,
    pessoa_id INTEGER NOT NULL REFERENCES pessoa(id),
    fonte TEXT NOT NULL,               -- 'camara_ceap' | 'senado_ceaps' | 'pres_cpgf' | 'pres_viagem'
    ano INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    data TEXT,
    categoria TEXT,
    fornecedor TEXT,
    cnpj_cpf TEXT,
    documento TEXT,
    descricao TEXT,
    unidade TEXT,
    valor REAL NOT NULL,               -- liquido: ja descontadas glosas/devolucoes
    url TEXT,
    arquivo TEXT NOT NULL              -- origem do lote ('camara_ceap:2024'): recarga apaga e reinsere o lote
);
CREATE INDEX IF NOT EXISTS ix_gasto_pessoa ON gasto (pessoa_id, ano, mes);
CREATE INDEX IF NOT EXISTS ix_gasto_arquivo ON gasto (arquivo);
CREATE TABLE IF NOT EXISTS coleta_log (
    id INTEGER PRIMARY KEY,
    fonte TEXT NOT NULL,
    recurso TEXT NOT NULL,
    ano INTEGER,
    registros INTEGER,
    coletado_em TEXT NOT NULL
);
-- Emendas parlamentares (Portal da Transparencia): uma linha por emenda x localidade x funcao
CREATE TABLE IF NOT EXISTS emenda (
    id INTEGER PRIMARY KEY,
    pessoa_id INTEGER REFERENCES pessoa(id),   -- NULL: autor coletivo (bancada, comissao, relator) ou nome sem correspondencia
    autor TEXT NOT NULL,                       -- nome do autor como veio da fonte
    tipo TEXT NOT NULL,                        -- Individual, Individual - Transferencias Especiais, Bancada, Comissao, Relator
    codigo TEXT,
    ano INTEGER NOT NULL,
    numero TEXT,
    uf TEXT,
    municipio TEXT,
    funcao TEXT,
    subfuncao TEXT,
    programa TEXT,
    acao TEXT,
    localidade TEXT,
    empenhado REAL, liquidado REAL, pago REAL,
    rap_inscrito REAL, rap_cancelado REAL, rap_pago REAL,   -- restos a pagar (empenhos de anos anteriores)
    arquivo TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_emenda_pessoa ON emenda (pessoa_id, ano);
-- Orcamento da Presidencia por programa e acao (Portal da Transparencia, execucao da despesa), agregado por mes
CREATE TABLE IF NOT EXISTS orcamento_acao (
    id INTEGER PRIMARY KEY,
    pessoa_id INTEGER NOT NULL REFERENCES pessoa(id),   -- ocupante do cargo no mes
    ano INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    orgao TEXT,
    programa TEXT,
    acao TEXT,
    empenhado REAL, liquidado REAL, pago REAL,
    arquivo TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_orc_pessoa ON orcamento_acao (pessoa_id, ano);
CREATE INDEX IF NOT EXISTS ix_orc_arquivo ON orcamento_acao (arquivo);

-- Quem recebeu cada emenda (Portal da Transparencia, arquivo "por favorecido"), somado por emenda x favorecido
CREATE TABLE IF NOT EXISTS emenda_favorecido (
    id INTEGER PRIMARY KEY,
    codigo TEXT NOT NULL,          -- codigo da emenda (liga com emenda.codigo)
    favorecido TEXT,
    documento TEXT,                -- CNPJ ou CPF (CPF vem mascarado)
    tipo TEXT,
    uf TEXT,
    municipio TEXT,
    valor REAL NOT NULL,
    n INTEGER NOT NULL,
    ano INTEGER                    -- ano do pagamento (coluna "Ano/Mes" do Portal)
);
CREATE INDEX IF NOT EXISTS ix_emenda_fav_codigo ON emenda_favorecido (codigo);

-- Obras federais (Obras.gov.br) cujo executor e recebedor de emendas
CREATE TABLE IF NOT EXISTS obra (
    id INTEGER PRIMARY KEY,
    id_unico TEXT, nome TEXT, situacao TEXT, uf TEXT, especie TEXT, natureza TEXT, tipo TEXT, subtipo TEXT,
    valor REAL, ini_prev TEXT, fim_prev TEXT, ini_efetiva TEXT, fim_efetiva TEXT, data_situacao TEXT,
    executor_cnpj TEXT, executor_nome TEXT, repassador TEXT
);
CREATE INDEX IF NOT EXISTS ix_obra_cnpj ON obra (executor_cnpj);
-- Populacao dos municipios (IBGE)
CREATE TABLE IF NOT EXISTS municipio_pop (ibge TEXT, nome TEXT, uf TEXT, populacao INTEGER, ano INTEGER);

-- Convenio (objeto e situacao) das emendas que viraram convenio (Portal da Transparencia)
CREATE TABLE IF NOT EXISTS emenda_convenio (
    id INTEGER PRIMARY KEY,
    codigo TEXT NOT NULL,          -- codigo da emenda
    numero TEXT,                   -- numero do convenio
    convenente TEXT,
    objeto TEXT,
    situacao TEXT,
    valor REAL,
    liberado REAL,
    inicio TEXT,
    fim TEXT,
    publicacao TEXT
);
CREATE INDEX IF NOT EXISTS ix_emenda_conv_codigo ON emenda_convenio (codigo);

-- Piloto Sao Paulo: despesa paga dos municipios paulistas (TCE-SP, dados Audesp), agregada
CREATE TABLE IF NOT EXISTS tce_carga (slug TEXT, ano INTEGER, municipio TEXT, linhas INTEGER, carregado TEXT, PRIMARY KEY (slug, ano));
CREATE TABLE IF NOT EXISTS tce_funcao (slug TEXT, ano INTEGER, funcao TEXT, fonte TEXT, pago REAL, n INTEGER);
CREATE INDEX IF NOT EXISTS ix_tce_funcao ON tce_funcao (slug, ano);
CREATE TABLE IF NOT EXISTS tce_pagamento (slug TEXT, ano INTEGER, documento TEXT, fornecedor TEXT, funcao TEXT, fonte TEXT, emenda INTEGER, historico TEXT, pago REAL, n INTEGER);
CREATE INDEX IF NOT EXISTS ix_tce_pag ON tce_pagamento (slug, ano);

-- Atuacao legislativa por parlamentar e ano (Camara: arquivos abertos de proposicoes e votacoes; Senado: API de processos)
CREATE TABLE IF NOT EXISTS atuacao (
    pessoa_id INTEGER NOT NULL, ano INTEGER NOT NULL, fonte TEXT NOT NULL,
    proposicoes INTEGER, pl INTEGER, pec INTEGER, normas INTEGER,   -- autoria principal; normas = viraram lei/norma
    votos INTEGER, votacoes_janela INTEGER,                         -- votacoes nominais em que votou x ocorridas entre o primeiro e o ultimo voto dele no ano
    PRIMARY KEY (pessoa_id, ano, fonte)
);
CREATE TABLE IF NOT EXISTS atuacao_carga (fonte TEXT, ano INTEGER, registros INTEGER, carregado TEXT, PRIMARY KEY (fonte, ano));

-- Cadastros de sancoes do Portal da Transparencia (CEIS, CNEP, CEPIM), so de quem aparece como recebedor de emendas
CREATE TABLE IF NOT EXISTS sancao (documento TEXT, cadastro TEXT, categoria TEXT, inicio TEXT, fim TEXT, orgao TEXT, nome TEXT);
CREATE INDEX IF NOT EXISTS ix_sancao_doc ON sancao (documento);
-- Fornecedores privados pagos pelos municipios do piloto (TCE-SP), por municipio e ano
CREATE TABLE IF NOT EXISTS tce_fornecedor (slug TEXT, ano INTEGER, documento TEXT, fornecedor TEXT, classe TEXT, pago REAL, pago_federal REAL, pago_dispensa REAL, n INTEGER);
CREATE INDEX IF NOT EXISTS ix_tce_forn ON tce_fornecedor (slug, ano);

-- Despesa paga por orgao superior (ministerios etc.), por mes e tipo de gasto (Portal da Transparencia, execucao da despesa)
CREATE TABLE IF NOT EXISTS despesa_orgao (
    ano INTEGER NOT NULL, mes INTEGER NOT NULL, orgao TEXT NOT NULL, bucket TEXT NOT NULL,   -- pessoal, divida, transferencias, demais
    empenhado REAL, liquidado REAL, pago REAL, rap_pago REAL, arquivo TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_desp_org ON despesa_orgao (ano, orgao);
CREATE INDEX IF NOT EXISTS ix_desp_org_arq ON despesa_orgao (arquivo);

-- Equipe dos gabinetes (lista do dia da coleta; sem remuneracao individual)
CREATE TABLE IF NOT EXISTS gabinete_pessoa (
    pessoa_id INTEGER NOT NULL REFERENCES pessoa(id), nome TEXT NOT NULL, cargo TEXT, lotacao TEXT, nomeacao TEXT, fonte TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_gab_pessoa ON gabinete_pessoa (pessoa_id);
CREATE TABLE IF NOT EXISTS gabinete_remun (pessoa_id INTEGER NOT NULL, ano INTEGER, mes INTEGER, nome TEXT, cargo TEXT, bruto REAL, fonte TEXT);
CREATE INDEX IF NOT EXISTS ix_gab_rem ON gabinete_remun (pessoa_id, ano, mes);

-- Dinheiro dos partidos (TSE): base = campanha_orgao | campanha_candidato | anual
CREATE TABLE IF NOT EXISTS partido_receita (ano INTEGER, base TEXT, sigla TEXT, fonte TEXT, valor REAL, n INTEGER);
CREATE INDEX IF NOT EXISTS ix_part_rec ON partido_receita (sigla, ano);
CREATE TABLE IF NOT EXISTS partido_despesa (ano INTEGER, base TEXT, sigla TEXT, categoria TEXT, valor REAL, n INTEGER);
CREATE INDEX IF NOT EXISTS ix_part_des ON partido_despesa (sigla, ano);
CREATE TABLE IF NOT EXISTS partido_recebedor (ano INTEGER, base TEXT, sigla TEXT, documento TEXT, nome TEXT, classe TEXT, valor REAL, n INTEGER);
CREATE INDEX IF NOT EXISTS ix_part_rcb ON partido_recebedor (sigla, ano);
CREATE TABLE IF NOT EXISTS partido_candidato (ano INTEGER, sigla TEXT, candidato TEXT, cargo TEXT, uf TEXT, fefc REAL, total REAL);
CREATE INDEX IF NOT EXISTS ix_part_cand ON partido_candidato (sigla, ano);
CREATE TABLE IF NOT EXISTS partido_carga (ano INTEGER, base TEXT, linhas INTEGER, carregado TEXT, PRIMARY KEY (ano, base));

CREATE TABLE IF NOT EXISTS pessoa_foto (pessoa_id INTEGER PRIMARY KEY, url TEXT);
CREATE TABLE IF NOT EXISTS candidatura (pessoa_id INTEGER NOT NULL, ano INTEGER, cargo TEXT, partido TEXT, numero TEXT, nome_urna TEXT, situacao TEXT);
CREATE INDEX IF NOT EXISTS ix_candidatura ON candidatura (pessoa_id, ano);

CREATE TABLE IF NOT EXISTS rf_empresa (cnpj8 TEXT PRIMARY KEY, razao TEXT, natureza TEXT, capital TEXT, porte TEXT, alvo INTEGER);
CREATE TABLE IF NOT EXISTS rf_estab (cnpj TEXT PRIMARY KEY, cnpj8 TEXT, matriz INTEGER, fantasia TEXT, situacao TEXT, abertura TEXT, cnae TEXT,
  logradouro TEXT, numero TEXT, complemento TEXT, bairro TEXT, cep TEXT, uf TEXT, municipio TEXT, chave_end TEXT);
CREATE TABLE IF NOT EXISTS rf_socio (cnpj8 TEXT, tipo TEXT, nome TEXT, doc TEXT, qualificacao TEXT, entrada TEXT, chave TEXT);
CREATE TABLE IF NOT EXISTS rf_relacao (alvo8 TEXT, tipo TEXT, chave TEXT, outro8 TEXT, cnpj TEXT, total INTEGER);
CREATE INDEX IF NOT EXISTS ix_rf_estab8 ON rf_estab (cnpj8);
CREATE INDEX IF NOT EXISTS ix_rf_socio8 ON rf_socio (cnpj8);
CREATE INDEX IF NOT EXISTS ix_rf_rel ON rf_relacao (alvo8);
CREATE TABLE IF NOT EXISTS doacao_campanha (ano INTEGER, tipo TEXT, chave TEXT, doador TEXT, pessoa_id INTEGER, partido TEXT, valor REAL, n INTEGER);
CREATE INDEX IF NOT EXISTS ix_doacao_chave ON doacao_campanha (chave);
