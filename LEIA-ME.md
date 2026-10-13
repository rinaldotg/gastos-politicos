# Gastos dos parlamentares - coleta de dados

## Requisitos
- Python 3.10+ e a biblioteca requests:  pip install requests

## Como rodar (Windows, PowerShell ou CMD)
1. Descompacte esta pasta, por exemplo em C:\gastos
2. Abra o terminal dentro da pasta:  cd C:\gastos
3. Teste rapido (sem internet, dados falsos):  python tests\test_offline.py
4. Coleta completa desde 2014 (demora; pode deixar rodando):
   python -m pipeline.run --db data\gastos.db --desde 2014 > log.txt 2>&1
5. Para testar uma parte so e mais rapido (ex.: um ano):
   python -m pipeline.run --db data\gastos.db --desde 2024 --ate 2024 --so camara
   Partes: camara  senado  presidencia  emendas  orcamento

## O que me mandar de volta
- O arquivo log.txt inteiro. Ele mostra as colunas reais do Portal da Transparencia
  (cartao corporativo, viagens, emendas, execucao da despesa), avisos de download
  bloqueado e quantos autores de emendas nao foram ligados a um parlamentar.
- Se algum download falhar, copie a linha que comeca com AVISO.

## Observacoes
- Pode rodar de novo a qualquer momento: cada lote e apagado e recarregado.
- Camara e Senado sao rapidos; presidencia e orcamento sao os mais pesados (varios arquivos mensais grandes).
- O banco gerado (data\gastos.db) fica so no seu computador.

## Conteudo
- pipeline/   coleta e banco SQLite (camara, senado, presidencia, emendas, orcamento)
- conteudo/   texto "o que cada gasto cobre" para o site
- tests/      teste offline

## Retomar depois de parar ou de um bloqueio
- O banco (data\gastos.db) guarda tudo o que ja foi baixado. NAO apague.
- Rode so as partes que faltam, sem recarregar Camara/Senado:
  python -m pipeline.run --db data\gastos.db --desde 2016 --so presidencia emendas orcamento --pular-cadastro > log2.txt 2>&1
- Meses/anos do Portal ja carregados (anteriores ao ano passado) sao pulados automaticamente.
- Se aparecer "PARADO: 3 downloads seguidos recusados", o Portal bloqueou temporariamente (erro 405).
  Espere 1-2 horas e rode o mesmo comando de novo.

## Conferir o banco e gerar o resumo para me enviar
  python -m pipeline.verificar --db data\gastos.db > verificacao.txt
Envie: verificacao.txt  e  resumo\resumo.zip  (CSVs pequenos, sem o banco inteiro).

## Corrigir orgao do orcamento e vinculo das emendas (versao de 13/10)
  python -m pipeline.run --db data\gastos.db --so emendas --pular-cadastro
  python -m pipeline.run --db data\gastos.db --so orcamento --recarregar-desde 2014 > log3.txt 2>&1
(o segundo recarrega os ~130 meses do orcamento e demora ~1h; o primeiro leva poucos minutos)
Depois: python -m pipeline.verificar --db data\gastos.db > verificacao.txt  e envie verificacao.txt + resumo\resumo.zip
