# Ligando o kit aos dados da sua empresa

O kit não sabe de onde o dado vem. Quem sabe é o `config/fontes.yaml`: para cada entidade do
[modelo canônico](modelo-de-dados.md) ele diz **onde ler** e **como as colunas se chamam**.

```
fonte (ERP, API, planilha, WhatsApp) --adaptador--> tabela canônica --regras--> relatórios
```

Comece copiando o arquivo de exemplo para um que não vai para o Git:

```bash
cp config/fontes.yaml config/fontes.local.yaml
cp .env.example .env            # senhas e tokens ficam só aqui
python -m frotakit validar --fontes config/fontes.local.yaml
python -m frotakit rodar   --fontes config/fontes.local.yaml --saida saida/
```

Não precisa ter todas as entidades. Só `veiculos` já dá a lista da frota; com `ordens_servico`
vem a disponibilidade; com `abastecimentos` vem o consumo; e assim por diante.

## Cenário 1 — empresa com ERP

A forma mais limpa é pedir à TI uma **view só de leitura** por entidade, já com os nomes do modelo:

```sql
CREATE VIEW vw_frota_ordens_servico AS
SELECT os.numero        AS os_id,
       v.placa          AS placa,
       os.dt_abertura   AS abertura,
       os.dt_conclusao  AS fechamento,
       os.situacao      AS status,
       f.razao_social   AS oficina,
       os.valor_total   AS valor
FROM manutencao_os os
JOIN veiculo v     ON v.id = os.veiculo_id
JOIN fornecedor f  ON f.id = os.fornecedor_id
WHERE os.dt_abertura >= CURRENT_DATE - INTERVAL '400 days';
```

```yaml
ordens_servico:
  tipo: sql
  conexao: ${ERP_URL}          # .env: ERP_URL=postgresql+psycopg://leitura:senha@erp.interno/erp
  consulta: SELECT * FROM vw_frota_ordens_servico
```

Para bancos que não são SQLite instale `sqlalchemy` e o driver (`psycopg`, `pyodbc`, `oracledb`...).
Se os status do seu ERP tiverem outros nomes, acrescente-os em `regras.yaml ->
disponibilidade.status_os_aberta` em vez de traduzir na consulta.

## Cenário 2 — cartão combustível / telemetria por API

```yaml
abastecimentos:
  tipo: api
  url: https://api.fornecedor.com/v1/transactions
  # token fixo...
  token: ${CARTAO_FROTA_TOKEN}
  # ...ou OAuth2 client credentials:
  # token_url: https://api.fornecedor.com/oauth/token
  # client_id: ${CARTAO_FROTA_CLIENT_ID}
  # client_secret: ${CARTAO_FROTA_CLIENT_SECRET}
  parametros: {startDate: "2026-01-01"}
  registros_em: data.items                       # onde está a lista dentro do JSON
  paginacao: {parametro: page, inicio: 1, tamanho_parametro: pageSize, tamanho: 200}
  salvar_bruto: saida/bruto/cartao                # guarda cada página para auditoria
  colunas:
    vehicle.plate: placa                          # campos aninhados viram "a.b"
    transactionDate: data_hora
    quantity: litros
    totalValue: valor
    odometer: odometro
    fullTank: tanque_cheio
    merchant.name: posto
    merchant.city: cidade
    driver.name: motorista
```

O adaptador repete a chamada em caso de limite de requisições (HTTP 429) ou instabilidade (5xx).
Se a API do seu fornecedor fugir muito desse padrão, escreva um adaptador próprio: é uma função
`ler(cfg, base) -> DataFrame` registrada em `frotakit/adaptadores/__init__.py`.

## Cenário 3 — planilhas

```yaml
veiculos:
  tipo: arquivo
  caminho: //servidor/frota/Controle de Frota.xlsx
  aba: Frota
  pular_linhas: 2                               # títulos acima do cabeçalho
  colunas: {PLACA: placa, MODELO: modelo, "FILIAL/BASE": base, SITUAÇÃO: status_cadastro}

uso:
  tipo: arquivo
  caminho: exportacoes/diario_*.xlsx           # vários arquivos: são concatenados
```

O separador de CSV é detectado sozinho (`;`, `,`, tab ou `|`); números e datas no padrão
brasileiro são entendidos.

### Diário de bordo em grade (placa × dia)

Muitas bases controlam a frota numa grade: uma linha por placa, uma coluna por dia, uma sigla em
cada célula. O adaptador `grade` lê isso direto, sem ninguém converter a planilha:

```yaml
uso:
  - tipo: arquivo                         # viagens de um roteirizador (sem sigla = rodou)
    caminho: exportacoes/viagens.csv
  - tipo: grade                           # diário de bordo das bases sem roteirizador
    caminho: diarios/*.xlsx
    abas: todas                           # ou [OUT-26, NOV-26]
    coluna_placa: PLACA
```

Ele procura a linha com "PLACA" e a linha das datas (a mesma ou uma acima) em cada aba; títulos,
linhas em branco e colunas como "modelo" e "total" no meio não atrapalham, e abas sem grade
(legenda) são ignoradas. Dias futuros já preenchidos com 0 são cortados. O significado das siglas
vem de `config/dicionario_status.csv`:

```
sigla;significado;grupo
M;Manutenção;manutencao
F;Folga;parado
SM;Sem motorista;parado
C;Coleta;rodou
```

Grupos: `rodou`, `manutencao`, `parado`. Números são quantidade de rotas. Sigla que não estiver
no arquivo aparece na aba "Siglas sem legenda" e o veículo fica "A confirmar" até alguém definir.

## Cenário 4 — vários fornecedores para a mesma entidade

Uma lista de fontes é concatenada. `fixos` grava um valor em todas as linhas; `placa_de` extrai a
placa de uma coluna de texto quando o fornecedor identifica o veículo por apelido ou descrição.

```yaml
posicoes:
  - tipo: arquivo
    caminho: rastreadores/fornecedor_a.csv
    fixos: {fornecedor: Fornecedor A}
  - tipo: arquivo
    caminho: rastreadores/fornecedor_b.xlsx
    placa_de: Descrição                        # "VAN 12 - ABC-1D23" -> ABC1D23
    colunas: {"Última posição": data_hora, Lat: latitude, Lng: longitude, Ignição: ignicao}
    fixos: {fornecedor: Fornecedor B}
```

## Cenário 5 — formulários de WhatsApp

Exporte a conversa pelo próprio WhatsApp (*Mais opções → Exportar conversa → Sem mídia*). O kit
lê o `.txt`; não acessa o WhatsApp.

```yaml
solicitacoes:
  tipo: whatsapp
  caminho: exportacoes/grupo_abastecimento.txt
  gatilho: FORMULARIO DE ABASTECIMENTO          # texto que marca a mensagem (sem acento)
  rotulos: {PLACA: placa, MOTORISTA: motorista, VALOR: valor, KM: odometro, PIX: chave_pix, POSTO: posto}
```

## Decisões manuais

Toda conferência acaba em casos que nenhuma regra resolve. Registre-os num CSV fora do Git e
aponte no `fontes.yaml`:

```yaml
decisoes:
  tipo: arquivo
  caminho: config/decisoes.local.csv
```

```
placa;acao;valor;motivo;quem;data
ABC1D28;ligar;ABC1D23;placa digitada errada no diário de novembro;Coordenação Base Sul;18/11/2026
RESERVA;ignorar;;linha de veículo reserva, sem placa;Coordenação Base Sul;18/11/2026
XYZ9A88;situacao;Manutenção;colisão, aguardando vistoria;Gestão de frota;19/11/2026
```

A aba "Decisões manuais" do relatório mostra o status de cada linha (aplicada, nenhum registro
com essa placa, placa de destino fora do cadastro...).

## Automatizar

Rodar duas vezes ao dia e publicar o HTML numa pasta compartilhada já resolve a maior parte das
operações. Linux (cron):

```
0 7,13 * * 1-6  cd /opt/frota-kit && .venv/bin/python -m frotakit rodar --fontes config/fontes.local.yaml --saida /srv/compartilhado/frota
```

No Windows, use o Agendador de Tarefas com o mesmo comando. Para o painel, `streamlit run
app/streamlit_app.py -- --fontes config/fontes.local.yaml` num servidor interno.

## Segurança

- Nunca escreva senha ou token no YAML; use `${VARIAVEL}` e defina no `.env`.
- `config/*.local.yaml`, `config/*.local.csv`, `.env`, `saida/` e `dados/` já estão no `.gitignore`.
- Prefira usuários **só de leitura** no ERP e tokens com o menor escopo que a API permitir.
