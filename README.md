# Radar de Gastos

Fiscalização cidadã de gastos de **deputados federais, senadores, prefeitos e vereadores** (e deputados estaduais, via campanha), no espírito da Operação Serenata de Amor (robô Rosie) e do cruzador de bases do Bruno César.

## O que ele faz

1. **Baixa os dados oficiais** (tudo público, sem senha):
   - Câmara: CEAP, nota a nota, com link para a nota fiscal
   - Senado: CEAPS
   - TSE: candidatos, bens declarados, receitas e despesas de campanha (2018–2024)
   - CGU: CEIS/CNEP (empresas punidas)
   - Receita: abertura, situação e sócios dos CNPJs de maior valor (via minhareceita.org / BrasilAPI)
2. **Roda 17 detectores**: nota duplicada, CNPJ inválido, fracionamento, valor atípico, refeição cara (regra da Rosie), fornecedor exclusivo, empresa sancionada, fornecedor que doou para a campanha, fornecedor candidato, político pagando a si mesmo, empresa recém-aberta, empresa baixada, sócio com o nome do político, sócio candidato, Benford, valores redondos e salto patrimonial.
3. **Dá um índice de atenção (0–100)** por político, para priorizar o que olhar primeiro.
4. **Mostra tudo**: um app local (Streamlit) com o Brasil inteiro, nota a nota, e um pacote JSON para o painel web.

## Como rodar (Windows, Mac ou Linux, com Python 3.10+)

```bash
pip install -r requirements.txt

python coletar.py --ufs MS          # comece por um estado (mais rápido)
python coletar.py                   # Brasil todo (vários GB, leva horas na 1ª vez)

streamlit run app.py                # abre no navegador: filtros, ranking, cada gasto

python exportar.py --uf MS          # gera dados/pacote_radar.json
python exportar.py --uf MS --municipio DOURADOS --cargo Prefeito Vereador
```

No painel web, toque em **Carregar pacote** e escolha `dados/pacote_radar.json`. Depois toque em **Salvar para todos** para abrir o mesmo pacote no celular (até 20 MB).

Opções úteis do coletor: `--anos 2025 2026` (anos da cota), `--eleicoes 2022 2024`, `--todos-candidatos` (inclui não eleitos), `--top-cnpj 1000` (mais CNPJs consultados na Receita), `--so-detectar` (reprocessa sem baixar de novo).

## Gastos do mandato municipal (prefeitura e câmara)

- **Contratos e empenhos publicados no PNCP** (todos os órgãos municipais: prefeitura, câmara, fundos, autarquias), com link para o contrato: automático com `--municipio DOURADOS:5003702` (nome:código IBGE).
- **Pagamentos, empenhos e diárias dos portais locais**: exporte a planilha (CSV/XLS/XLSX) no portal de transparência e salve em `dados\importar\` com nome começando por `prefeitura_` ou `camara_` e contendo o tipo, ex.: `prefeitura_pagamentos_2025.xlsx`, `camara_diarias_2025.csv`. O coletor reconhece as colunas sozinho. Diárias pagas a vereador/prefeito eleito entram na conta da pessoa.
- Novo detector: **doador de campanha contratado pelo município** (pelo CPF/CNPJ ou pelo nome do sócio da empresa).

## Publicar na internet (grátis, Hugging Face)

1. Crie uma conta em huggingface.co e um token tipo **Write** em huggingface.co/settings/tokens.
2. Rode `Publicar Radar.bat` (1ª vez pede o token). Ele cria a cópia pública do banco com CPFs de pessoas físicas ocultos,
   sobe os dados para `<usuario>/radar-de-gastos-dados` e o app para o Space `<usuario>/radar-de-gastos`.
3. Link para divulgar: `https://<usuario>-radar-de-gastos.hf.space`.
Para atualizar o site: rode `Atualizar Radar Brasil.bat` (ou o de MS) e depois `Publicar Radar.bat`.

## Novidades, votações e municípios

- **📰 Novidades**: o que entrou desde a última atualização (notas, contratos, alertas novos), lançamentos mais recentes,
  votações nominais recentes (Câmara e Senado, com o voto de cada parlamentar) e manchetes do Google Notícias.
- **Ficha → O que fez no mandato**: como votou (filtro só PECs e busca por tema), projetos apresentados e notícias.
- **Municípios**: `--municipios-uf MS` traz os contratos PNCP de todos os municípios da UF; `--capitais` as 27 capitais.

## Ficha do político

Na aba Políticos (separada dos órgãos municipais), ao clicar num nome aparece a ficha: foto, nome civil, idade, partido, quem representa, mandato (início, fim, quanto já cumpriu), gasto no mandato, e-mail, telefone, gabinete, redes sociais (Câmara/Senado/TSE) e uma mensagem pronta para cobrar por e-mail ou WhatsApp.

## Impostômetro

Aba **🧾 Impostômetro** no app: contador ao vivo dos tributos federais arrecadados no ano (dado oficial da Receita Federal até o último mês publicado + estimativa pelo ritmo dos últimos 12 meses), ranking dos impostos, arrecadação por ano e por estado. Fonte: `gov.br/receitafederal/dados/arrecadacao-estado.csv`. Soma federal (Tesouro, diário), estadual (ICMS/IPVA/ITCD dos 27 estados via SICONFI, bimestral) e municipal + FGTS (estimativa pela base anual oficial).

## Limites

- **Gastos de mandato municipal** (verba de gabinete de vereador, diárias, contratos da prefeitura) não têm base nacional padronizada: estão no portal de cada TCE e prefeitura. Para prefeitos e vereadores, o radar usa a prestação de contas de campanha do TSE (despesa a despesa) e os cruzamentos. Um próximo passo é um adaptador por TCE (ex.: TCE-MS) para trazer empenhos e diárias.
- **Deputados estaduais**: entram pela campanha; a cota das Assembleias varia por estado.
- CPFs de sócios vêm mascarados da Receita; o casamento sócio × candidato usa nome + 6 dígitos centrais.
- **Todo alerta é indício, não prova.** Confira a nota original antes de qualquer conclusão ou denúncia.

## Teste sem internet

`python tests/gerar_fixtures.py` cria dados fictícios nos formatos oficiais, com irregularidades plantadas; depois `python coletar.py --anos 2025 2026 --top-cnpj 0` (ou com o cache fictício gerado) valida o pipeline.

## Estrutura

```
coletar.py          baixa, normaliza, detecta e grava dados/radar.duckdb
exportar.py         gera o pacote JSON do painel
app.py              app local (Streamlit)
radar/fontes/       camara.py, senado.py, tse.py, empresas.py
radar/detectores.py regras de irregularidade e índice de atenção
```
