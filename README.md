# Gastos Públicos

Site com os gastos de deputados federais, senadores e da Presidência da República desde 2014: quanto, com o quê, com quem, emendas e comparação lado a lado.

- `pipeline/` coleta (Câmara, Senado, Portal da Transparência) e guarda em SQLite
- `site/` gerador do site estático (Python + Jinja2, JavaScript puro)
- `.github/workflows/atualizar.yml` rotina mensal: coleta, gera o site e publica no GitHub Pages
- `conteudo/` textos de apoio (o que cada gasto cobre)

Local: `python -m pipeline.run --db data/gastos.db`, depois `python -m pipeline.verificar --db data/gastos.db`, depois `python site/build.py --resumo resumo --saida dist`.
Detalhes de uso da coleta em `LEIA-ME.md`.
