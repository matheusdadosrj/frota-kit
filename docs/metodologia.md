# Metodologia

Como cada número do relatório é calculado e por que foi feito assim. Todos os limites citados
ficam em `config/regras.yaml`.

## 0. Placas: a chave de tudo

Todas as tabelas se ligam pela placa. Uma placa digitada errada desliga um abastecimento, uma OS
ou um dia de diário do veículo certo, e o erro se espalha para a disponibilidade e o consumo.

1. **Normalização**: maiúsculas, sem espaço, hífen ou ponto (`abc-1d23` → `ABC1D23`).
2. **Correção pela posição**: no padrão brasileiro as posições 1–3 são letras e 4, 6 e 7 são
   números. Número em posição de letra (`0→O`, `1→I`, `5→S`, `8→B`) e letra em posição de
   número (`O→0`, `I→1`, `D→0`, `Q→0`, `L→1`) são trocados, **só** quando a placa original é
   inválida e a corrigida fica válida. Toda correção aparece na aba "Placas corrigidas".
3. **Sugestão, nunca vínculo automático**: placa que continua fora do cadastro vai para "Placas
   fora do cadastro" com um diagnóstico (formato inválido, provável erro de digitação ou placa
   válida desconhecida) e, quando existe, a placa do cadastro que **difere em 1 caractere**.
   Ligar "no chute" é pior do que não ligar: um vínculo errado contamina a situação de outro
   veículo. Quem confere decide e registra a decisão (seção 1.3).

## 1. Disponibilidade

Cada veículo recebe **uma** situação, decidida por regras avaliadas em ordem
(`disponibilidade.ordem`). A primeira que se aplica decide:

| ordem | regra | situação | motivo exibido |
| --- | --- | --- | --- |
| 1 | `decisao_manual`: decisão `situacao` registrada em `decisoes.csv`, válida a partir da data dela | a categoria decidida | `decisão manual: colisão; aguardando vistoria (Gestão de frota, 17/11/2026)` |
| 2 | `fora_da_frota`: status do cadastro em `status_fora_da_frota` | Indisponível | `cadastro: VENDIDO desde 21/09/2026` |
| 3 | `os_aberta`: OS com status em `status_os_aberta` (ou sem status e sem fechamento) | Indisponível | `OS 48096 aberta em 06/09/2026 em Oficina X (75 dias)` |
| 4 | `diario_manutencao`: última sigla do diário é do grupo `manutencao` | Indisponível | `diário (NOV-26): 'M' (Manutenção) em 19/11/2026` |
| 5 | `a_confirmar`: última sigla do diário não está no dicionário | A confirmar | `sigla 'RIO' sem significado no dicionário` |
| 6 | `ocioso`: nenhuma atividade há mais de `dias_ocioso` | Disponível (ocioso) | `sem atividade há 41 dias (último: abastecimento em 10/10/2026)` |
| 7 | `em_operacao`: o resto | Disponível | `abastecimento em 19/11/2026` |

"Atividade" é a data mais recente entre viagem/uso (siglas do grupo `rodou`), abastecimento e
posição de rastreador com ignição ligada. A sigla do diário só vale se tiver até
`diario.validade_dias` dias: um "M" de três semanas atrás não prende o carro hoje.

**Por que uma ordem explícita e um motivo?** Porque as fontes se contradizem. Mostrar *qual regra*
decidiu e *com qual dado* faz a operação confiar no número — e corrigir a fonte quando ela está
errada.

### 1.1 Quantas fontes confirmam (coluna `confirmacao`)

Uma indisponibilidade sustentada por uma fonte só é mais frágil do que uma sustentada por duas:

| caso | confirmação |
| --- | --- |
| baixa no cadastro **e** nenhuma atividade depois da data da baixa | confirmada por 2 fontes |
| baixa no cadastro, mas houve atividade depois | conflito entre fontes |
| OS aberta **e** veículo parado desde a abertura (ou diário com manutenção) | confirmada por 2 fontes |
| OS aberta, mas o veículo rodou depois | conflito entre fontes |
| manutenção só no diário, sem OS no sistema | só 1 fonte → alerta "abrir OS?" |
| decisão manual | decisão manual (com responsável e data) |

### 1.2 Alertas

As contradições não somem: viram a coluna **alertas**.

- OS aberta, mas houve atividade depois da abertura → OS esquecida aberta?
- OS aberta há mais de 30 dias → veículo parado na oficina;
- manutenção só no diário, sem OS → abrir OS?;
- diário marca manutenção, mas houve atividade depois;
- baixado no cadastro, mas houve atividade depois da baixa;
- decisão manual diz manutenção/baixa, mas o veículo rodou depois → rever a decisão;
- rastreador sem sinal há mais de `dias_sem_sinal` dias.

### 1.3 Siglas do diário e decisões manuais

**Siglas.** `config/dicionario_status.csv` traduz cada sigla num de três grupos: `rodou`
(atividade), `manutencao` (indisponível) e `parado` (não rodou, mas está disponível: folga, sem
rota, sem motorista). Números são quantidade de rotas (`0` = sem rota). Sigla fora do dicionário
**não quebra nada**: o veículo fica "A confirmar" e a sigla entra na aba "Siglas sem legenda", a
lista para a operação definir o significado. A regra de negócio fica na mão de quem é dono dela.

**Decisões.** O que nenhuma regra resolve é decidido por uma pessoa e registrado (placa, ação,
valor, motivo, quem, data): `ligar` troca uma placa digitada errada pela do cadastro em todas as
fontes; `ignorar` tira linhas que não são veículo ("RESERVA"); `situacao` força a categoria a
partir da data. A aba "Decisões manuais" mostra se cada uma foi aplicada, para nenhuma ficar
esquecida valendo para sempre.

### 1.4 Taxa de disponibilidade e histórico

A **taxa de disponibilidade** é calculada sobre a frota ativa (exclui "fora da frota"):
`(em operação + ocioso) ÷ (todo o resto menos fora da frota)`. "A confirmar" entra no
denominador e não no numerador: na dúvida, não conta como disponível.

A data de referência pode ser qualquer dia do passado: tudo o que aconteceu depois dela é ignorado.
O **histórico** usa isso para aplicar exatamente a mesma regra a cada um dos últimos
`dias_historico` dias e produz:

- a disponibilidade de cada dia, por base e total, e a **média do período** (o indicador do mês);
- os **dias de cada veículo** em cada categoria (quem custa mais tempo parado);
- os **dias com conflito**: o veículo rodou num dia em que constava em manutenção. Cada um desses
  dias é um erro em alguma fonte (OS esquecida aberta, sigla errada no diário).

## 2. Consumo real (km/L)

### Entre tanques cheios

Entre dois abastecimentos de **tanque cheio**, o combustível colocado é exatamente o que foi
gasto. Então, para cada par de cheios consecutivos:

```
km/L do intervalo = (odômetro no 2º cheio − odômetro no 1º cheio) ÷ (litros de todos os abastecimentos depois do 1º, até o 2º inclusive)
```

Abastecimentos parciais no meio entram nos litros. Média de km/L por abastecimento isolado não
funciona: um parcial de R$ 100 seguido de um cheio distorce qualquer conta que não use o par de cheios.

### Acumulado por veículo e margem de erro

O km/L do veículo é `Σ km ÷ Σ litros` dos intervalos válidos — não a média dos km/L. Se um "cheio"
na verdade não encheu, faltam litros num intervalo e sobram no seguinte; somando, o erro se anula.
Só erram as **pontas** de cada sequência contínua de intervalos. Aceitando um cheio como cheio a
partir de `tanque_referencia` (90%) da capacidade, cada ponta erra no máximo 10% do tanque:

```
margem = (1 − 0,90) × capacidade × nº de sequências ÷ Σ litros
```

Confiança: **alta** com margem ≤ 2% ou 5+ intervalos; **média** com 2–4; **baixa** com 1.

### Qualidade do dado (antes da conta)

| alerta | regra | efeito |
| --- | --- | --- |
| `duplicado` | mesma placa e litros, mesmo odômetro (ou sem), em até `minutos_duplicado` | excluído |
| `odometro_ausente` | vazio ou zero | não serve de âncora; amplia a autonomia aceita no registro seguinte |
| `odometro_regrediu` | menor que o maior já visto | não serve de âncora |
| `odometro_corrigido` | 5× a 20× (ou 1/20 a 1/5) da mediana da placa: dígito a mais/a menos | dividido/multiplicado por 10 |
| `salto_odometro` | avançou mais que a autonomia (tanque × km/L máximo do grupo) e o registro seguinte **não** confirma | tratado como erro de digitação |
| `trecho_longo` | avançou mais que a autonomia e o registro seguinte **confirma** | rodou sem abastecer no controle: abastecimento por fora ou registro faltando |
| `acima_tanque` | litros > capacidade × `folga_tanque` | sinal de dois veículos no mesmo cartão |
| `cheio_valor_redondo` | marcado como cheio com litros múltiplos de 5 ou valor múltiplo de R$ 10 | só aviso: a bomba pode ter sido travada |
| `cheio_serrote` | intervalo com km/L alto seguido de um com km/L baixo, além da variação normal da placa | o "cheio" do meio não encheu: os dois intervalos são **juntados** |
| `cheio_abaixo_esperado` | km/L muito alto sem o par baixo para confirmar | só aviso |

O **padrão serrote** é o que mais distorce o consumo na prática. O limite para "alto" e "baixo" é
`max(limiar_serrote, 3 × desvio mediano da placa)`, para não confundir a variação normal de um
veículo (troca de motorista, rota diferente) com um cheio falso. Intervalos fora da faixa do grupo
também são examinados, porque é exatamente isso que um cheio falso provoca.

### Desperdício estimado

Para cada grupo de veículo (com pelo menos `minimo_grupo` veículos de confiança média ou alta)
calcula-se a mediana de km/L. Para quem está abaixo dela:

```
litros a mais = litros medidos − km medidos ÷ km/L mediano do grupo
R$ a mais     = litros a mais × preço médio pago pelo veículo
```

É uma estimativa conservadora (compara com a mediana, não com o melhor) e serve para priorizar
onde olhar primeiro: manutenção, motorista, rota ou fraude.

## 3. Motoristas

Comparar o km/L de motoristas diretamente é injusto: quem dirige caminhão sempre "consome mais".
Por isso cada intervalo é comparado com o km/L **do mesmo veículo dirigido por outros motoristas**
(mediana das medianas de cada outro motorista, para que um titular que quase sempre dirige o carro
não vire a referência). O desvio de cada motorista é a média desses desvios, e o intervalo de
confiança de 95% sai de `reamostragens` reamostragens *bootstrap*.

A conclusão só diz "consome mais/menos" quando **o intervalo inteiro** está de um lado do zero **e**
a diferença média passa de `desvio_relevante` (5%). Uma diferença de 1%, mesmo "significativa",
não justifica conversar com ninguém.

O motorista de cada intervalo é o do abastecimento que o fecha. Se a sua operação troca de
motorista no meio do intervalo com frequência, use a entidade `uso` para atribuir por km rodado.

## 4. Postos

Para cada abastecimento, `preço por litro − mediana dos preços da mesma cidade, combustível e mês`,
multiplicado pelos litros, dá o **pago a mais**. Somado por posto, mostra onde a escolha do posto
custa dinheiro. Postos com sobrepreço médio acima de `sobrepreco_minimo` são marcados.

## 5. Pedidos de pagamento

Cada pedido (formulário, WhatsApp, e-mail) é conferido antes de pagar. Um alerta qualquer retém o
pedido para conferência; sem alerta, ele aparece como liberado.

| alerta | regra |
| --- | --- |
| placa inválida / fora do cadastro | não casa com `regex_placa` / não está em `veiculos` |
| veículo indisponível | a disponibilidade diz que está baixado ou com OS aberta |
| provável reenvio | mesma placa e mesmo odômetro em até `horas_reenvio` |
| odômetro copiado | mesma placa e mesmo odômetro em outro dia |
| odômetro menor que o anterior | regrediu em relação a um pedido anterior da placa |
| mesmo motorista e odômetro em outra placa | placa digitada errada |
| sem odômetro / sem chave PIX | campo obrigatório vazio |
