# Estudo de caso — controle de frota numa transportadora de last mile

Este kit é a versão genérica de soluções que desenvolvi como **estagiário** na **Pralog**. Eu era o único
na área de dados: cuidava de extrair e tratar os dados brutos das várias fontes e de transformá-los em
informação para apoiar as decisões da operação e da gestão de frota. A Pralog é uma transportadora
de last mile que atende grandes marketplaces, com uma frota de cerca de mil veículos (carros,
utilitários, vans e caminhões) em sete estados. Nenhum dado da empresa está neste repositório;
o código original também não — ele era preso demais àquela realidade para servir a outra empresa.

## O problema

A informação da frota estava espalhada e se contradizia:

| fonte | o que dizia | problema |
| --- | --- | --- |
| Sistema de gestão de frota (API) | ordens de serviço, cadastro | OS abertas para veículos que já rodavam; cadastro desatualizado |
| Planilha "Controle de Frota" (SharePoint) | situação de cada placa, oficina, baixa | atualizada à mão, cada base de um jeito |
| Diários de bordo por base (Excel) | um código por placa por dia (rodou, manutenção, reserva...) | dezenas de siglas, novas surgindo toda semana |
| Rotas de três plataformas de entrega | quem rodou e quando | uma delas não traz a placa |
| Cinco fornecedores de rastreador | última posição | cinco formatos; alguns identificam o veículo pelo apelido |
| Cartão combustível (API OAuth2) | abastecimentos | odômetro digitado à mão, "tanque cheio" marcado sem encher |
| Grupo de WhatsApp | pedidos de pagamento de abastecimento por PIX | conferidos a olho, com reenvios e odômetros copiados |

Duas perguntas simples não tinham resposta confiável: **quantos veículos estão disponíveis hoje?**
e **quanto cada veículo realmente consome?**

## O que foi construído

1. **Consulta de placas**, atualizada automaticamente duas vezes por dia (Agendador do Windows):
   juntava todas as fontes acima, aplicava a regra de disponibilidade definida com a operação e
   publicava Excel, página HTML e um banco SQLite na pasta que a equipe já usava. Cada placa vinha
   com a **situação, o motivo e as divergências entre fontes**.
2. **Consumo real por veículo** a partir da API do cartão combustível: km/L entre tanques cheios,
   detecção de cheio falso (padrão serrote), odômetro com dígito a mais, registros em dobro,
   comparação de motoristas e de preço dos postos, e um painel local para conferir pagamentos.
3. **Consolidação dos rastreadores**: um adaptador por fornecedor, geocodificação reversa com cache
   e alerta de "sem sinal há N dias".
4. **Leitura dos formulários de WhatsApp**: a conversa exportada virava planilha de lançamentos
   com alertas antes do pagamento. Numa semana típica, cerca de um em cada quatro formulários
   tinha algo a conferir (reenvio, odômetro repetido, placa incompleta, sem PIX).

## As primeiras quatro semanas (consulta de placas)

| semana | entregas |
| --- | --- |
| 1 | Ambiente (venv, token fora do código), extração de filiais e veículos pela API, camada bruta em JSON com data e hora, tratamento do cadastro e primeiro relatório de qualidade |
| 1–2 | Leitura dos diários de bordo (grades por aba, cada base de um jeito), dicionário de siglas e a primeira lista de siglas sem legenda enviada à operação |
| 2 | Cruzamento de placas entre quatro fontes, com revisão dos casos ambíguos junto com a operação; ordens de serviço pela API |
| 2 | **Consulta de placas publicada** para a equipe, atualizada sozinha às 8h e às 14h |
| 3 | Rotas das três plataformas numa tabela única e situação de cada veículo dia a dia num banco SQLite |
| 3 | Regra de disponibilidade refinada em rodadas com a operação |
| 4 | Planilha de monitoramento como fonte principal de rastreador e desmobilização; listas de veículos em manutenção; gerador de dados fictícios |

Depois vieram o consumo pela API do cartão combustível, os rastreadores e os formulários de WhatsApp.

## Problemas reais e o que aprendi com cada um

- **"O sistema mostra 194 OS e o meu código, 198."** Antes de mexer no código, conferi a tela do
  sistema: ela estava filtrada em duas filiais, e as quatro OS a mais eram de outras. *Conferir os
  filtros da referência antes de concluir que o código errou.*
- **58 OS com data vazia.** A API devolvia datas ISO em formatos misturados, e
  o parse silencioso virava nulo. *Validar a contagem de nulos depois de cada conversão.*
- **O mês errado no diário.** O mês de cada arquivo era deduzido pela data mais frequente nas
  abas, e um arquivo com abas antigas puxava para o mês anterior. Passou a valer o mês mais recente.
- **A conclusão que eu quase levei errada.** A primeira análise dizia que 19 carros desmobilizados
  tinham rodado no mês. Conferindo linha a linha antes de apresentar, vi que todos tinham zero
  dias rodados: o erro estava no cruzamento. A correção virou regra: **uma baixa só é confirmada
  quando duas fontes concordam** (cadastro diz baixa **e** nenhuma atividade depois) — no kit, a
  coluna `confirmacao`. *Conferir o número antes de levar à operação.*
- **A placa que "parecia" outra.** Placas com um caractere de diferença eram tentadoras de ligar
  automaticamente. Não liguei: um vínculo errado põe a situação de um carro em outro. O que é
  ambíguo foi para uma lista de revisão, e a decisão de quem conferiu ficou registrada com nome e
  data — no kit, a sugestão de placa parecida e o `decisoes.csv`.
- **Sigla nova toda semana.** As bases criavam siglas no diário sem avisar. Em vez de o código
  quebrar ou adivinhar, sigla desconhecida virava "a confirmar" e entrava numa lista mandada para a
  operação — no kit, o dicionário de siglas editável e a aba "Siglas sem legenda".
- **Atualização parada por 18 horas.** O notebook dormiu no meio da rodada e a seguinte não
  começou. O agendador passou a encerrar a rodada anterior e a limitar cada uma a 30 minutos.
- **"A tarefa rodou", mas não rodou.** Na limpeza de pastas, o `.bat` do agendador foi apagado;
  o Windows seguia mostrando a última execução, com código de erro 1. *O horário da última
  execução só diz que tentou; quem diz se funcionou é o código de saída e o log.*
- **A publicação que ninguém via.** Ao sincronizar a biblioteca inteira da nuvem, o caminho da
  pasta mudou e os arquivos continuaram indo para o antigo. O destino passou a ser configurável.

## O que deu certo

- **Mostrar o motivo, não só o status.** A operação passou a confiar no número quando viu *por que*
  cada placa estava em cada situação, e passou a corrigir as planilhas na origem.
- **Divergência é informação.** "OS aberta, mas rodou ontem" e "na oficina há meses sem orçamento"
  foram os achados de maior valor: veículos parados que ninguém via, OS esquecidas, pagamentos
  possivelmente duplicados.
- **Regras explícitas e versionadas.** Cada ajuste combinado com a operação virou uma regra com
  data e justificativa, o que encerrou discussões do tipo "mas ontem estava diferente".
- **Entregar onde as pessoas já estão** (Excel e HTML na pasta compartilhada) teve adoção imediata.
- **Estatística simples e honesta**: medianas, intervalos de confiança e margem de erro declarada
  evitaram acusar motorista ou posto por acaso.

## O que eu faria diferente — e virou este kit

- **Separar fonte de regra.** No original, a regra de disponibilidade lia direto de várias planilhas,
  com exceções para cada uma. Aqui, todo dado passa primeiro por um modelo canônico; a regra só
  conhece "veículo", "OS", "abastecimento", "uso" e "posição". Numa empresa com ERP, basta apontar
  o adaptador SQL para uma view.
- **Configuração fora do código.** Faixas de km/L, dias para "ocioso", status de OS, a ordem das
  regras e o significado das siglas do diário ficam em arquivos que a operação edita.
- **Revisão humana como parte do sistema**, e não por fora dele: decisões registradas com
  responsável e data, aplicadas em todas as rodadas e visíveis no relatório.
- **O indicador do mês, não só o retrato do dia**: a mesma regra aplicada a cada dia do período
  dá a disponibilidade média e os dias em que as fontes se contradisseram.
- **Testes desde o começo**, com dados fictícios que reproduzem cada problema real encontrado.

## Stack

Python, pandas, numpy, requests (REST e OAuth2), SQLite, openpyxl, HTML/CSS/JS sem dependências,
Streamlit, pytest; automação com Agendador de Tarefas do Windows e publicação em SharePoint/OneDrive.
