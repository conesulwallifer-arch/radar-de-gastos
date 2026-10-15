"""Radar de Ações: ranking de ações para renda (dividendos/JCP), notícias, previsões e alertas diários."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados_acoes"
DADOS.mkdir(parents=True, exist_ok=True)

AVISO = ("Ferramenta educacional. Não é recomendação de investimento: previsões são estimativas estatísticas "
         "com base no passado, e o passado não garante o futuro. Confira os dados no RI da empresa antes de investir.")
