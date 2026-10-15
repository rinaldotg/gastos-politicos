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
