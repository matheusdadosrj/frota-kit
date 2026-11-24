# Limitações e recomendações

Todo sistema tem limites. Este documento diz com franqueza onde o frota-kit **não** resolve o
problema, por quê, e o que uma empresa precisa ter, em pessoas e em tecnologia, para tirar dele
o máximo. Leia antes de prometer resultados à diretoria.

- O que configurar e como implantar: [nota-tecnica.md](nota-tecnica.md)
- Como cada número é calculado: [metodologia.md](metodologia.md)

---

## 1. O que depende do dado de origem

O kit trabalha bem com dado ruim: aponta erro, sugere correção e declara a margem de erro. Mas
**não cria informação que não existe**.

| gargalo | por que o kit não resolve | recomendação |
| --- | --- | --- |
| **Odômetro digitado à mão** | Separa erro de digitação de trecho rodado sem abastecer, mas não sabe qual era o valor certo | Telemetria que lê o odômetro automaticamente, ou cartão que exige odômetro e confere com o anterior |
| **"Tanque cheio" não marcado** | Sem essa marcação não existe km/L confiável; o consumo fica "sem cálculo" | Combinar com postos e motoristas e exigir o campo do fornecedor do cartão |
| **Abastecimento fora do cartão** (PIX, dinheiro, reembolso) | O que não está registrado em `abastecimentos` não entra na conta de consumo | Carregar esses pagamentos como abastecimento, ou reduzir ao mínimo o pagamento por fora |
| **OS que nunca é fechada** | O kit aponta "OS esquecida", mas não fecha a OS | Um responsável por fechar OS no sistema no mesmo dia |
| **Placa como única chave** | Troca de placa (conversão Mercosul, transferência) ou veículo sem placa quebra a ligação entre as tabelas | Identificador fixo por veículo no ERP (código interno ou chassi) e histórico de troca de placa |
| **Desvio de combustível bem feito** | Quem desvia sempre um pouco faz o veículo parecer só "gastão". A comparação com o grupo aponta, mas não prova | Sensor de nível do tanque na telemetria; sem ele, o kit só indica suspeita |

## 2. Limites técnicos atuais

- **Consumo sem contexto.** O km/L é comparado com a mediana do grupo de veículos; carga, rota,
  relevo, trânsito e temperatura não entram. Uma van que só roda em serra parecerá desperdício.
  O passo seguinte seria um modelo de consumo previsto com essas variáveis, que depende de dados
  que poucas empresas têm organizados (peso por viagem, rota planejada, altimetria).
- **Comparação de motoristas exige rodízio.** Se cada motorista dirige sempre o mesmo veículo, não
  dá para separar o efeito do motorista do efeito do veículo; nesses casos o kit não conclui nada.
- **"Disponível" significa não estar na oficina nem baixado.** O kit não sabe se há motorista para
  o veículo, se licenciamento ou seguro venceram, ou se o pneu está gasto. Essas fontes podem
  virar regras novas (ver [nota-tecnica.md](nota-tecnica.md), seção 6).
- **Processamento em lote.** O relatório é gerado algumas vezes ao dia; não há alertas em tempo
  real nem envio automático por e-mail ou mensagem.
- **Escala.** Os dados são processados em memória (pandas) e o histórico recalcula cada dia do
  período a cada rodada. Funciona bem até alguns milhares de veículos e alguns anos de
  abastecimentos; acima disso, o cálculo deve ir para um banco de dados (PostgreSQL, data
  warehouse), processando só o que mudou.
- **Geocodificação gratuita é lenta.** O OpenStreetMap (Nominatim) aceita 1 consulta por segundo:
  atende frotas pequenas, não milhares de posições por dia. Para isso, um serviço pago.
- **Sem controle de acesso e sem edição concorrente.** O painel Streamlit não tem login, e o
  arquivo de decisões não suporta duas pessoas editando ao mesmo tempo. Em produção: autenticação
  corporativa e uma tela de decisões gravando em banco.
- **Somente leitura, por decisão de projeto.** O kit não escreve no ERP: não fecha OS nem bloqueia
  cartão. É mais seguro, mas toda ação continua manual.
- **Formulários de WhatsApp dependem de padrão.** O kit não lê a foto da nota fiscal (não há
  reconhecimento de texto em imagem). O ideal é trocar o WhatsApp por um formulário estruturado.
- **Calibrado numa realidade.** Faixas de km/L, validade das siglas e limites de alerta nasceram
  de uma operação de last mile e dos dados fictícios. Cada empresa precisa recalibrar com a
  própria frota.
- **Manutenção do projeto.** É um projeto aberto mantido por uma pessoa, sem suporte garantido.
  Quem adotar deve ter alguém interno capaz de ler e ajustar o código.

## 3. Pessoas que a empresa precisa ter

O kit não funciona sem donos.

| papel | responsabilidade | dedicação |
| --- | --- | --- |
| **Gestor de frota** (dono das regras) | Aprova o `regras.yaml`, define o que é "disponível", aprova decisões manuais | Calibração no início; revisão mensal |
| **Responsável pelo cadastro** | Mantém placa, grupo, capacidade do tanque e status de baixa corretos | Contínua — é a base de tudo |
| **Responsável pela manutenção** | Abre e fecha OS no sistema no mesmo dia | Contínua |
| **Coordenadores das bases** | Mantêm o diário de bordo e o dicionário de siglas | Diária |
| **Analista de dados** | Roda, monitora, investiga alertas, ajusta regras, escreve adaptadores | Meio período na implantação; algumas horas por semana depois |
| **TI** | Views de leitura no ERP, credenciais, servidor, agendamento | Pontual |
| **Jurídico, RH ou encarregado de dados (LGPD)** | Valida o uso da comparação de motoristas e o tratamento de nomes e CPF | Pontual, **antes** de usar o ranking de motoristas |

**Atenção ao ranking de motoristas.** Usá-lo para cobrar, advertir ou punir tem implicações
trabalhistas e de proteção de dados. Ele serve para orientar e treinar, nunca como prova isolada.

## 4. Tecnologia que destrava o próximo nível

Por ordem de impacto:

1. **Telemetria com leitura da rede do veículo e sensor de nível do tanque** — elimina o odômetro
   digitado e transforma suspeita de desvio em evidência.
2. **Cartão combustível com odômetro obrigatório e marcação de tanque cheio**, ou bomba própria
   automatizada.
3. **Banco de dados e ferramenta de BI** (por exemplo PostgreSQL com Power BI ou Metabase) quando
   a frota ou o histórico crescer.
4. **App ou formulário estruturado** no lugar do WhatsApp para pedidos de pagamento.
5. **Dados de viagem** (carga, rota planejada, altimetria) para chegar a um modelo de consumo
   previsto por rota.
