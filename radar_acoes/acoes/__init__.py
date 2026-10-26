"""Radar de Ações: ranking de ações para renda (dividendos/JCP), notícias, previsões e alertas diários."""
import sys
from pathlib import Path

# No Windows, quando a saída vai para arquivo (painel sem janela, agendador), o padrão é cp1252, que não
# sabe escrever emojis: um simples print("🔮 ...") derrubava a apuração. Força UTF-8 e, se mesmo assim
# algum caractere não couber, troca por "?" em vez de quebrar.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # sem console (pythonw) ou fluxo que não aceita reconfigurar
        pass

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados_acoes"
DADOS.mkdir(parents=True, exist_ok=True)

AVISO = ("Ferramenta educacional. Não é recomendação de investimento: previsões são estimativas estatísticas "
         "com base no passado, e o passado não garante o futuro. Confira os dados no RI da empresa antes de investir.")
