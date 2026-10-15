# 📈 Radar de Ações — renda passiva de longo prazo

Sistema que **apura todo dia** as ações da B3 que pagam bons proventos (dividendos e JCP), dá uma **nota de 0 a 100**,
diz se é hora de **Comprar / Acumular / Aguardar / Evitar**, faz **previsões** (proventos dos próximos 12 meses,
faixa de preço em 1, 3 e 5 anos, evolução da carteira com aportes mensais), traz as **notícias** de cada empresa
e **te avisa** (Telegram e/ou e-mail) das melhores oportunidades e do que mudou.

> ⚠️ Ferramenta educacional, **não é recomendação de investimento**. As previsões são estatísticas com base no passado.
> Confira os dados no site de RI da empresa antes de investir.

## Como instalar (Windows, Mac ou Linux, Python 3.10+)

```bash
cd radar_acoes
pip install -r requirements.txt

python apurar.py --demo --sem-envio   # teste rápido com dados FICTÍCIOS (sem internet)
python apurar.py --aporte 1000        # apuração real + sugestão para um aporte de R$ 1.000
streamlit run app.py                  # abre o painel no navegador
```

No Windows, dê dois cliques em **`Apurar Acoes.bat`** (apuração) e **`Abrir Painel Acoes.bat`** (painel).

## O painel

| Aba | O que mostra |
|---|---|
| 🏆 Ranking | Todas as ações com nota, sinal, preço, preço-teto (Bazin), preço justo (Graham), DY 12m / médio 5 anos / previsto, anos pagando, ROE, P/L, P/VP, dívida, payout e meses em que costuma pagar. Filtros por setor, sinal e DY mínimo. |
| 🔔 Alertas | Oportunidades novas, queda forte de ação boa, novo provento anunciado, data-com chegando, mudanças no top 10, ação da sua carteira que piorou, notícias negativas relevantes. |
| 🏢 Empresa | Gráfico de 5 anos com o preço-teto, proventos ano a ano, histórico de pagamentos, previsão de preço (pessimista/mediana/otimista), proventos previstos, indicadores, notícias com tom (🟢/🔴) e assunto, descrição do negócio. |
| 🛒 Aporte do mês | Digite o valor do aporte e (opcional) sua carteira atual: o sistema diz **quantas cotas comprar de cada ação**, diversificando por setor e completando o que está abaixo do peso-alvo. |
| 📊 Simulador | Aportes mensais + reinvestimento dos proventos por N anos, 3 cenários, e **em quanto tempo você chega à renda passiva desejada**. |

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

Crie `dados_acoes/carteira.csv` (ou edite na aba **Aporte do mês**):

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

## Fontes e limites

- Cotações, proventos (dividendos + JCP pela data-ex, valores brutos) e indicadores: **Yahoo Finance** (biblioteca `yfinance`).
  Pode haver atraso ou falhas pontuais; se um código mudar na B3, ele aparece em "sem dados".
- Notícias: **Google Notícias** (RSS). O tom (positiva/negativa) é uma classificação simples por palavras-chave.
- JCP tem 15% de IR retido na fonte; dividendos são isentos (regra vigente pode mudar — confira).

## Testes

```bash
python -m pytest radar_acoes/tests -q
```

## Estrutura

```
apurar.py            apuração diária: coleta → nota → notícias → previsões → alertas → envio
app.py               painel (Streamlit)
acoes/dados.py       Yahoo Finance com cache diário
acoes/analise.py     indicadores, preço-teto, preço justo, nota e sinal
acoes/previsao.py    proventos 12m, faixa de preço, simulador de aportes
acoes/aporte.py      sugestão de compra do mês e revisão da carteira
acoes/alertas.py     alertas do dia, Telegram e e-mail
acoes/noticias.py    Google Notícias + tom e assunto
acoes/demo.py        dados fictícios para testar sem internet
```
