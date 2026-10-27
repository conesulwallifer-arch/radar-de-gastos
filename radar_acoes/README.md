# 🪙 AURUM · Radar de Ações — renda passiva e patrimônio de longo prazo

Sistema que **apura todo dia** as ações da B3 que pagam bons proventos (dividendos e JCP), dá uma **nota de 0 a 100**,
diz se é hora de **Comprar / Acumular / Aguardar / Evitar**, faz **previsões** (proventos dos próximos 12 meses,
faixa de preço em 1, 3 e 5 anos, evolução da carteira com aportes mensais), traz as **notícias** de cada empresa
e **te avisa** (Telegram e/ou e-mail) das melhores oportunidades e do que mudou.

> ⚠️ Ferramenta educacional, **não é recomendação de investimento**. As previsões são estatísticas com base no passado.
> Confira os dados no site de RI da empresa antes de investir.

## 🪙 O agente AURUM

O painel tem o visual de um terminal de mercado financeiro (fundo escuro, dourado, verde/vermelho para altas e quedas, fita de cotações) e um estrategista-chefe, o **AURUM**, que trabalha por você:

| O que ele faz | Quando |
|---|---|
| **Vigia o pregão**: confere as 15 melhores ações e as da sua carteira e avisa no Telegram/e-mail se uma ação boa cair abaixo do preço-teto ou despencar ≥ 4% | a cada 30 min, das 10h às 18h (dias úteis) |
| **Apuração da hora**: baixa preços novos e refaz ranking, previsões, mesa dos 7 especialistas e alertas do painel (sem IA paga e sem mensagem no Telegram) | de hora em hora, das 10h às 17h (dias úteis) — `AURUM_APURAR_A_CADA_MIN` |
| **Apuração completa**: refaz notas, previsões, meta, teste no passado, notícias e escreve o **relatório do dia** | todo dia útil às 18h30 |
| **Conversa** no painel (aba 🪙 AURUM): "TAEE11 vale a pena?", "o que comprar este mês?", "quando chego no milhão?" | quando você quiser |

**Dois modos:**
- **Local (grátis, padrão)**: o AURUM fala só a partir dos dados da apuração, com regras.
- **Com IA (opcional)**: coloque `ANTHROPIC_API_KEY` no `config.env` (chave em console.anthropic.com). Aí o relatório é escrito pela IA Claude,
  que também **pesquisa notícias na internet** sobre as ações do plano do mês e da sua carteira, e você conversa livremente.
  Custo típico: alguns centavos de dólar por relatório ou pergunta.

**Como ligar o agente:**
- No computador: dois cliques em **`Iniciar AURUM.bat`** e deixe a janela aberta (ou agende no Agendador de Tarefas para iniciar com o Windows).
  Também dá para rodar uma vez: `python agente.py --agora` (apuração + relatório) ou `python agente.py --checar` (só vigilância).
- Na nuvem (computador desligado): o GitHub Actions já roda a vigilância de hora em hora no pregão e a apuração às 18h30.
  Cadastre os segredos `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` e, se quiser IA, `ANTHROPIC_API_KEY`; opcionalmente `CARTEIRA_CSV` e
  `PLANO_JSON` (o conteúdo do seu `dados_acoes/plano.json`).

## 🧠 A equipe de agentes

Sete especialistas analisam **todas** as ações todo dia, cada um pelo seu ângulo, e votam de −2 a +2:

| Agente | Função |
|---|---|
| 💰 **Dora** — Dividendos | quanto paga, regularidade, crescimento e sustentabilidade dos proventos |
| 🏛️ **Fausto** — Fundamentos | lucro, ROE, margens, dívida |
| 🏷️ **Vitória** — Valuation | preço-teto (Bazin), preço justo (Graham), P/L, P/VP |
| 📈 **Téo** — Tendência | média de 200 dias, quedas em andamento, distância do topo |
| 📰 **Nina** — Notícias | tom do noticiário e notícias graves (com IA: pesquisa na internet) |
| 🔮 **Íris** — Previsões | chance de subir/cair no próximo mês, com placar de acertos |
| 🛡️ **Rex** — Risco | veta prejuízo e dado duvidoso, mede oscilação, concentração e compara com a renda fixa |

**Como eles se interligam para não errar:**
1. **Verificação cruzada** — um confere o outro: Fausto confere a Dora (o lucro sustenta os proventos?), Dora confere a Vitória
   (o preço-teto está inflado por provento extraordinário?), Téo confere a Vitória (está barata porque ainda está caindo?),
   Vitória confere o Téo, Nina confere o Fausto (notícia grave?), Rex confere a base de todos (cotação atrasada = veto).
2. **Dupla checagem** — o AURUM só mantém "Comprar/Acumular" se a nota do sistema **e** o consenso da equipe concordarem.
3. **Cérebro (memória e aprendizado)** — cada voto é guardado e conferido 3 meses depois contra o que a ação fez de verdade
   (descontando o movimento da bolsa). Com amostra suficiente, quem acerta mais ganha peso e quem erra perde.
4. **Íris se autoavalia** — as previsões de curto prazo são testadas nos últimos 3 anos sem olhar o futuro; se não baterem o
   "chute", são neutralizadas e não influenciam nada. Toda previsão diária é registrada e conferida 1 mês depois.

Com `ANTHROPIC_API_KEY`, cada especialista também é um agente Claude que revisa as 8 melhores candidatas (com seu próprio
histórico de acertos no "cérebro"), e a Nina pesquisa a internet. Na aba **🧠 Sala dos Agentes** você vê cada um trabalhando,
a atividade, as contestações, o placar, o debate sobre cada ação e o cérebro de cada agente. Ao clicar em **Apurar agora**,
as etapas aparecem ao vivo.

## 🧭 Atlas, o agente com livre-arbítrio

Os 7 especialistas seguem um roteiro. O **Atlas** não: ele decide sozinho o que investigar, usando ferramentas —
consultar o ranking, abrir a ficha de qualquer ação (com os votos dos outros agentes), comparar, pesquisar na internet,
**anotar na memória de longo prazo** (e ler as anotações dos dias anteriores para checar as próprias teses), **propor ações
novas** para a equipe passar a analisar e levantar alertas. Limites: não compra, não vende, não mexe no seu plano;
no máximo 12 passos, 5 anotações e 3 propostas por dia; proposta sem dados no Yahoo sai da lista sozinha.
Sem chave da IA, ele roda por regras (quem mais melhorou/piorou, boas empresas esperando preço, divergências ranking × equipe).

## O que veio dos melhores sistemas do mundo

| Inspiração | O que o Radar faz |
|---|---|
| Notas por fator comparadas ao setor (Seeking Alpha Quant) | Notas de **F a A+** em Valor, Renda, Qualidade, Saúde e Momento, comparando cada ação com as do mesmo setor |
| "Snowflake" com checagens objetivas (Simply Wall St) | **Raio-X em floco** de 5 eixos na ficha de cada empresa e **segurança dos dividendos** por 6 checagens |
| Piotroski F-score e cobertura por caixa livre (scores de segurança de dividendos) | **F-score de 9 testes** com os balanços e **quanto do caixa livre vira dividendo** |
| Preço-alvo / valor justo | Além de Bazin e Graham, **preço justo por dividendos descontados (Gordon)**, com taxa exigida que sobe com a Selic |
| Agenda de dividendos e gestão de carteira (Investidor10, Status Invest) | **Agenda de proventos**: quanto você deve receber em cada um dos próximos 12 meses e as próximas datas-com |
| Ratings que se dizem "preditivos" | Aqui tudo tem **placar real**: teste no passado sem colar, previsões registradas e conferidas, agentes que perdem peso quando erram |

## 🏢 A equipe trabalhando 24h (mesmo com o painel fechado)

Clique em **▶️ Ligar equipe 24h** na barra lateral do painel (ou dois cliques em **`Ligar AURUM 24h.bat`**). A equipe passa a
rodar escondida e **liga sozinha sempre que o Windows iniciar** — não precisa de administrador nem do painel aberto:

| Quando | Quem | O quê |
|---|---|---|
| Ao ligar o computador | AURUM | Se perdeu alguma apuração, coloca o trabalho em dia na hora |
| Dias úteis, 10h–18h, a cada 30 min | Rex e Téo | Vigiam os preços das melhores ações e da sua carteira; avisam no Telegram |
| Dias úteis, 10h–17h, de hora em hora | Todos (sem IA) | Apuração da hora com preços novos: o painel sempre mostra o pregão de agora |
| Dias úteis, 18h30 | Todos | Reunião completa: coleta, 7 especialistas, verificação cruzada, Atlas, memória, relatório |
| Sábado, 10h | AURUM | Reunião semanal: o que mudou na semana, placar real da equipe, anotações do Atlas |

### 🔭 Equipe de previsibilidade (Otto, Bento e Sofia)
Três especialistas em prever, cada um **testado no passado sem colar** — o placar fica na aba **🔭 Previsões**:

| Agente | Prevê | Como é testado |
|---|---|---|
| 💵 **Otto** — Previsor de Proventos | Proventos dos próximos 12 meses (com faixa provável) e a **chance de corte** | Para cada um dos últimos 6 anos, prevê só com os anos anteriores e confere o que foi pago |
| 🎯 **Bento** — Estrategista de Entrada | Preço da **ordem de compra** com ~80% e ~50% de chance de executar em 1 mês | Aprende os níveis até 1 ano atrás e confere no último ano se 80% e 50% se confirmaram |
| 🧮 **Sofia** — Cientista de Dados | Chance de cada ação render **mais que a mediana** das outras em 3 meses (momento, tendência, oscilação, dividendos, distância do topo) | Treina e testa mês a mês (36 meses, com intervalo de segurança); só vota se o ganho for estatisticamente real (t ≥ 2) |

Otto e Sofia votam na mesa (Bento só informa o preço). Quem não prova vantagem no teste fica neutro — o mesmo vale para a Íris.

### ⚡ Mesa de Trading (médio prazo)
A aba **⚡ Trading** é separada do projeto de dividendos. O **Leo** testa 5 padrões clássicos em todas as ações:
correção na tendência de alta, rompimento de máxima de 3 meses, **dividendos no topo + virada** (barata pela renda e começando a subir),
cruzamento dourado e **queda forte + virada**.

- **Regras de saída iguais para todos:** stop a ~1 mês de oscilação normal (5% a 18%), alvo a 2× o risco, stop vai para a entrada
  quando o ganho cobre o risco, saída por tempo em 3 meses; custos descontados.
- **Teste honesto:** dois períodos separados (antigo e últimos 3 anos) e comparação com o *chute* (entrar em dias aleatórios com as
  mesmas saídas). ✅ Aprovado só se ganhou nos dois períodos e venceu o chute com folga estatística (t ≥ 1,5).
- **Sinais de hoje** com entrada, stop, alvo, acerto do padrão e se a ação está **barata**; ações vetadas pelo Rex ficam de fora.
- **Calculadora de posição** (arriscar 1% do capital por operação) e **Minhas operações**: o Leo acompanha e avisa no Telegram
  quando bater alvo, stop ou for hora de proteger o ganho.
- **Placar real:** os sinais aprovados são registrados e conferidos depois.

### 🔄 Atualizar
Dê dois cliques em **`Atualizar AURUM.bat`**: baixa a versão mais nova, mantém `dados_acoes` e `config.env`,
reinicia a Equipe 24h (se estiver ligada) e abre o painel.

### 📡 Mercado ao vivo
A aba **📡 Mercado ao vivo** mostra todas as ações acompanhadas no pregão de hoje — o que **sobe** e o que **cai**,
o Ibovespa, mínima/máxima e o gráfico do dia — e **se atualiza sozinha a cada minuto** (dá para pausar no botão *Ao vivo*).
Filtros: todas, só as recomendadas ou só a sua carteira. Destaca **boas empresas em queda abaixo do preço-teto**.
Fonte: Yahoo Finance, com **atraso de ~15 minutos** para a B3 (cotação em tempo real de verdade só com contrato pago da B3).

Na aba **🧠 Sala dos Agentes**, o **Escritório em 3D** (Three.js, roda no seu computador, sem internet) mostra a sala com
cada agente como um boneco 3D na sua mesa: digitando quando trabalha, olhando em volta e mexendo o mouse quando vigia,
recostado tomando café na pausa; o monitor de cada um mostra a sua função, e o telão da parede tem a fita de cotações.
A câmera gira sozinha — arraste para olhar de qualquer ângulo e role para aproximar. Há também a visão **2D** (botão 3D/2D).
O escritório mostra cada um na sua mesa (trabalhando, vigiando ou em pausa, e o que está
fazendo) e o **diário da equipe**, que acumula tudo o que fizeram, dia após dia — a tela se atualiza sozinha a cada 20 segundos.
Para parar: **⏹️ Desligar equipe** (ou `Desligar AURUM 24h.bat`). Com o computador desligado, quem cobre é o GitHub Actions.

**Melhorando a cada dia, com prova:** cada voto de cada agente — e a decisão final da equipe — é guardado e conferido 3 meses
depois contra o que a ação fez de verdade (descontando o movimento da bolsa). Quem acerta ganha peso; o placar aparece no
"Cérebro de cada agente" e na reunião semanal.

## 🔭 Um passo à frente

Ninguém prevê o preço de amanhã; o que dá para antecipar é o que **já está marcado para acontecer**:
- **Juros**: o Boletim Focus do Banco Central (o que o mercado espera para a Selic e o IPCA). Se espera queda de juros,
  boas pagadoras de dividendos costumam se valorizar — o AURUM avisa antes.
- **Balanços** das próximas 3 semanas (alerta 7 dias antes para o top 15 e sua carteira) e **datas-com** dos próximos 15 dias.

## ⚙️ Configurar Telegram, IA e aporte (assistente)

Dois cliques em **`Configurar AURUM.bat`** (ou `python configurar.py`). O assistente explica cada passo, descobre sozinho o
seu chat do Telegram, manda uma mensagem de teste, confere a chave da IA sem gastar créditos e grava o `config.env`.

## Como instalar (Windows, Mac ou Linux, Python 3.10+)

```bash
cd radar_acoes
pip install -r requirements.txt

python apurar.py --demo --sem-envio   # teste rápido com dados FICTÍCIOS (sem internet)
python apurar.py --aporte 1000        # apuração real + sugestão para um aporte de R$ 1.000
python -m streamlit run app.py        # abre o painel no navegador (rode de dentro da pasta radar_acoes)
```

No Windows, dê dois cliques em **`Apurar Acoes.bat`** (apuração) e **`Abrir Painel Acoes.bat`** (painel).

## O painel

| Aba | O que mostra |
|---|---|
| ✅ O que fazer hoje | Em português simples: **quais ações comprar este mês, quantas cotas, quanto custa e por quê**, com link para conferir no Status Invest; sua meta; os alertas mais importantes. |
| 🎯 Rumo ao R$ 1 milhão | 5.000 simulações da bolsa: **tempo até a meta com anos bons, o mais provável e com anos ruins**, chance de chegar até cada ano, o que te leva mais rápido, quanto aportar para chegar em X anos e a comparação com a renda fixa (Selic real do Banco Central). |
| 🧪 O sistema funciona? | **Teste no passado**: R$ X por mês nos últimos 5 anos seguindo o sistema (só com o que se sabia em cada mês) × CDI × Ibovespa. |
| 💼 Minha carteira | Suas ações, quanto valem hoje, resultado e renda estimada. |
| 🏆 Ranking | Todas as ações com nota, sinal, preço, preço-teto (Bazin), preço justo (Graham), DY 12m / médio 5 anos / previsto, anos pagando, ROE, P/L, P/VP, dívida, payout e meses em que costuma pagar. Filtros por setor, sinal e DY mínimo. |
| 🔔 Alertas | Oportunidades novas, queda forte de ação boa, novo provento anunciado, data-com chegando, mudanças no top 10, ação da sua carteira que piorou, notícias negativas relevantes. |
| 🏢 Empresa | Gráfico de 5 anos com o preço-teto, proventos ano a ano, histórico de pagamentos, previsão de preço (pessimista/mediana/otimista), proventos previstos, indicadores, notícias com tom (🟢/🔴) e assunto, descrição do negócio. |

## Alertas diários automáticos

### Opção 1 — no seu computador (Windows)
1. Copie `config.env.exemplo` para `config.env` e preencha o Telegram e/ou o e-mail e o `APORTE_MENSAL`.
2. Abra o **Agendador de Tarefas** → *Criar Tarefa Básica* → Diariamente (marque seg–sex) às 19:00 →
   *Iniciar um programa* → escolha `Apurar Acoes.bat`.

### Opção 2 — na nuvem, de graça (GitHub Actions)
O arquivo `.github/workflows/radar_acoes.yml` roda a apuração nos dias úteis às 18h30 (Brasília), mesmo com o computador desligado.
Em *Settings → Secrets and variables → Actions* do repositório, cadastre:
- Segredos: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` (e/ou `EMAIL_REMETENTE`, `EMAIL_SENHA`, `EMAIL_DESTINO`);
  opcional `CARTEIRA_CSV` com o conteúdo da sua carteira (ex.: `ticker,quantidade,preco_medio` e uma linha por ação).
- Variável: `APORTE_MENSAL` (ex.: `1000`).

O relatório de cada dia também fica em *Actions → execução → Artifacts*. Você pode rodar na hora em *Actions → Run workflow*.

## Sua carteira

Crie `dados_acoes/carteira.csv` (ou edite na aba **💼 Minha carteira**):

```csv
ticker,quantidade,preco_medio
TAEE11,50,34.20
BBSE3,30,31.00
```

Com ela, o aporte do mês completa as posições abaixo do alvo, os alertas acompanham suas ações de perto
e as notícias delas são sempre buscadas.

Para mudar a lista de ações analisadas, crie `dados_acoes/minha_lista.txt` com um código por linha
(o padrão está em `acoes/universo.py`, ~60 pagadoras de proventos de setores perenes).

## Como a nota é calculada

- **Renda (40%)**: dividend yield médio de 5 anos (DY acima de 14% é penalizado: costuma ser extraordinário), regularidade
  (anos pagando nos últimos 10), crescimento e estabilidade dos proventos.
- **Qualidade (30%)**: ROE, margem líquida, dívida/patrimônio (exceto bancos e seguradoras), payout sustentável, lucro positivo.
- **Preço (20%)**: margem até o **preço-teto de Bazin** (dividendo médio ÷ 6%), **preço justo de Graham** (√(22,5 × LPA × VPA)), P/L e P/VP.
- **Risco (10%)**: volatilidade e maior queda em 5 anos. Notícias ajustam no máximo ±3 pontos.

**Sinais**: *Comprar* = nota ≥ 65 e preço abaixo do teto · *Acumular* = nota ≥ 55 e até 10% acima do teto ·
*Aguardar* = boa, mas cara ou com DY médio < 4% · *Evitar* = nota baixa ou prejuízo.

## Previsões

- **Proventos 12 meses**: média dos últimos 3 anos × crescimento histórico (limitado a ±10% a.a.), com os meses em que a empresa costuma pagar.
- **Preço**: modelo log-normal; tendência = 50% histórico de 5 anos + 50% expectativa de longo prazo da bolsa (12% a.a. menos o DY);
  faixa de 80% de probabilidade pela volatilidade histórica.
- **Carteira**: aportes mensais com reinvestimento dos proventos, cenários pessimista/base/otimista (valores nominais).

## Dá para confiar?

O sistema foi feito para ser **verificável**, não para pedir fé:
- Todo número mostra **de quando é** (data da cotação no topo; aviso se tiver mais de 3 dias úteis).
- Cada ação passa por uma **checagem de confiança** (cotação velha, preço divergente entre fontes, provento fora do normal,
  dado faltando). Dado duvidoso **nunca** vira "Comprar".
- Cada recomendação diz **por quê**, em português, e tem um link para conferir no Status Invest.
- O **teste no passado** mostra como o método teria se saído, com os limites escritos na tela.
- O simulador mostra **chances**, não promessas, e compara com a renda fixa: se a Selic estiver alta, ele te diz que a
  renda fixa pode chegar lá tão rápido quanto.

O que nenhum sistema faz: prever o preço de amanhã ou garantir R$ 1 milhão. O caminho até a meta depende
principalmente de **quanto você aporta e por quanto tempo**; o sistema faz a lição de casa diária para você investir bem esse dinheiro.

## Fontes e limites

- Cotações, proventos (dividendos + JCP pela data-ex, valores brutos) e indicadores: **Yahoo Finance** (biblioteca `yfinance`).
  Pode haver atraso ou falhas pontuais; se um código mudar na B3, ele aparece em "sem dados".
- Selic, IPCA e CDI: **Banco Central do Brasil** (API oficial SGS).
- Notícias: **Google Notícias** (RSS). O tom (positiva/negativa) é uma classificação simples por palavras-chave.
- JCP tem 15% de IR retido na fonte; dividendos são isentos (regra vigente pode mudar — confira).

## Testes

```bash
python -m pytest radar_acoes/tests -q
```

## Estrutura

```
agente.py            agente AURUM: vigia o pregão e faz a apuração diária sozinho
apurar.py            apuração diária: coleta → nota → notícias → previsões → alertas → relatório do AURUM → envio
app.py               painel (Streamlit)
acoes/dados.py       Yahoo Finance com cache diário
acoes/analise.py     indicadores, preço-teto, preço justo, nota e sinal
acoes/previsao.py    proventos 12m, faixa de preço, simulador de aportes
acoes/aporte.py      sugestão de compra do mês e revisão da carteira
acoes/meta.py        simulação até a meta (Monte Carlo), alavancas, aporte necessário
acoes/backtest.py    teste no passado × CDI × Ibovespa
acoes/macro.py       Selic, IPCA e CDI do Banco Central
acoes/plano.py       seu plano (aporte, meta) salvo em dados_acoes/plano.json
acoes/aurum.py      relatório do dia e conversa (regras ou IA Claude com pesquisa na web)
acoes/vigia.py       vigilância de preços durante o pregão
acoes/visual.py      visual de terminal de mercado do painel e a sala dos agentes (2D)
static/sala3d.js     a sala dos agentes em 3D (Three.js incluído em static/, licença MIT)
acoes/mesa.py        os 7 agentes, verificação cruzada e consenso (regras + IA)
acoes/previsor.py    Íris: chance de alta/queda em 1 mês, teste sem colar e placar real
acoes/memoria.py     cérebro dos agentes: memória de votos e pesos aprendidos
acoes/ia.py          acesso à IA Claude (opcional)
acoes/atlas.py       Atlas: explorador autônomo com ferramentas, memória e propostas
acoes/fundamentos.py Piotroski, caixa livre, segurança dos dividendos, preço justo por Gordon
acoes/agenda.py      agenda de proventos dos próximos 12 meses e datas-com
acoes/alertas.py     alertas do dia, Telegram e e-mail
acoes/noticias.py    Google Notícias + tom e assunto
acoes/demo.py        dados fictícios para testar sem internet
```
