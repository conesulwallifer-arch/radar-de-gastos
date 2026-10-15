"""Atlas — o explorador autônomo da equipe.

Diferente dos outros agentes (que analisam todas as ações por um roteiro fixo), o Atlas tem LIVRE-ARBÍTRIO
dentro de limites: ele mesmo decide o que investigar, usando ferramentas — consultar o ranking, abrir a ficha
de qualquer ação, comparar ações, pesquisar na internet, guardar anotações na memória de longo prazo
(ele lê as anotações dos dias anteriores), propor ações novas para a equipe vigiar e levantar alertas.

Limites (de propósito): não compra, não vende, não mexe no seu plano nem na carteira; no máximo
12 passos, 5 anotações e 3 propostas por dia. Propostas só entram na lista se o Yahoo tiver dados delas.

Sem chave da IA, o Atlas roda no modo por regras: procura sinais fora do óbvio (quem mais subiu de nota,
boas empresas esperando preço, ações com notas altas no setor fora do top 10).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

import numpy as np
import pandas as pd

from . import DADOS, escritorio, ia
from .alertas import _fmt_r as brl

NOTAS = DADOS / "atlas_notas.json"
DESCOBERTAS = DADOS / "descobertas.txt"
MAX_PASSOS, MAX_NOTAS_DIA, MAX_PROPOSTAS_DIA = 12, 5, 3
TICKER_OK = re.compile(r"^[A-Z]{4}\d{1,2}$")


# ------------------------------------------------------------------ memória de longo prazo
def ler_notas(limite: int = 40) -> list[dict]:
    try:
        notas = json.loads(NOTAS.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return notas[-limite:]


def _salvar_nota(texto: str, ticker: str | None) -> None:
    notas = ler_notas(400)
    notas.append({"data": date.today().isoformat(), "ticker": ticker, "texto": texto[:500]})
    NOTAS.parent.mkdir(parents=True, exist_ok=True)
    NOTAS.write_text(json.dumps(notas[-400:], ensure_ascii=False, indent=1), encoding="utf-8")


def ler_descobertas() -> list[str]:
    try:
        return [l.split("#")[0].strip() for l in DESCOBERTAS.read_text(encoding="utf-8").splitlines() if l.split("#")[0].strip()]
    except FileNotFoundError:
        return []


def _propor(ticker: str, motivo: str) -> bool:
    ticker = ticker.strip().upper()
    if not TICKER_OK.match(ticker) or ticker in ler_descobertas():
        return False
    DESCOBERTAS.parent.mkdir(parents=True, exist_ok=True)
    with open(DESCOBERTAS, "a", encoding="utf-8") as f:
        f.write(f"{ticker}  # {date.today().isoformat()} Atlas: {motivo[:150]}\n")
    return True


def limpar_descobertas(sem_dados: list[str]) -> None:
    """Remove propostas que o Yahoo não reconheceu (código errado ou inexistente)."""
    if not DESCOBERTAS.exists() or not sem_dados:
        return
    linhas = [l for l in DESCOBERTAS.read_text(encoding="utf-8").splitlines() if l.split("#")[0].strip() not in sem_dados]
    DESCOBERTAS.write_text("\n".join(linhas) + ("\n" if linhas else ""), encoding="utf-8")


# ------------------------------------------------------------------ as ferramentas (o que o Atlas pode fazer)
CAMPOS = ["ticker", "nome", "setor", "posicao", "nota", "sinal", "consenso", "preco", "preco_teto_bazin", "margem_bazin",
          "preco_justo_ddm", "dy_medio_5a", "anos_pagou_10", "seguranca_div", "f_score_9", "payout", "payout_fcl", "roe",
          "divida_pl", "pl", "pvp", "var_12m", "volatilidade", "grau_Valor", "grau_Renda", "grau_Qualidade", "grau_Saúde",
          "grau_Momento", "prob_alta_1m", "confianca"]

FERRAMENTAS = [
    {"name": "ver_ranking", "strict": True,
     "description": "Lista ações do ranking de hoje com os principais números. Use para ter visão geral ou filtrar por setor/sinal.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["setor", "sinal", "ordenar_por", "limite"],
                      "properties": {"setor": {"type": "string", "description": "nome do setor ou '' para todos"},
                                     "sinal": {"type": "string", "enum": ["", "Comprar", "Acumular", "Aguardar", "Evitar"]},
                                     "ordenar_por": {"type": "string", "enum": ["nota", "dy_medio_5a", "margem_bazin", "seguranca_div",
                                                                               "f_score_9", "var_12m", "prob_alta_1m"]},
                                     "limite": {"type": "integer", "enum": [5, 10, 20]}}}},
    {"name": "ver_acao", "strict": True,
     "description": "Ficha completa de uma ação: indicadores, notas por fator no setor, votos e argumentos dos 7 agentes, notícias recentes.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["ticker"],
                      "properties": {"ticker": {"type": "string"}}}},
    {"name": "comparar", "strict": True,
     "description": "Compara de 2 a 5 ações lado a lado.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["tickers"],
                      "properties": {"tickers": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "anotar", "strict": True,
     "description": "Guarda uma anotação na sua memória de longo prazo (você lerá amanhã). Use para teses, dúvidas a checar e o que aprendeu.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["texto", "ticker"],
                      "properties": {"texto": {"type": "string"}, "ticker": {"type": "string", "description": "código ou ''"}}}},
    {"name": "propor_vigiar", "strict": True,
     "description": "Propõe uma ação da B3 que NÃO está na lista para a equipe passar a analisar a partir da próxima apuração.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["ticker", "motivo"],
                      "properties": {"ticker": {"type": "string"}, "motivo": {"type": "string"}}}},
    {"name": "levantar_alerta", "strict": True,
     "description": "Envia um alerta ao investidor sobre algo importante que você descobriu (vai no relatório e no Telegram).",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["ticker", "texto", "gravidade"],
                      "properties": {"ticker": {"type": "string"}, "texto": {"type": "string"},
                                     "gravidade": {"type": "string", "enum": ["alta", "media"]}}}},
]


def _limpo(v):
    if isinstance(v, (float, np.floating)):
        return None if v != v or v in (float("inf"), float("-inf")) else round(float(v), 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


class Ferramentas:
    def __init__(self, R: dict):
        self.R = R
        self.rk: pd.DataFrame = R["ranking"]
        self.notas_hoje = 0
        self.propostas: list[dict] = []
        self.alertas: list[dict] = []
        self.diario: list[str] = []

    def _linha(self, r) -> dict:
        return {c: _limpo(r.get(c)) for c in CAMPOS if c in r}

    def executar(self, nome: str, entrada: dict) -> str:
        try:
            return json.dumps(getattr(self, nome)(**entrada), ensure_ascii=False, default=str)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"erro": str(e)}, ensure_ascii=False)

    def ver_ranking(self, setor: str, sinal: str, ordenar_por: str, limite: int):
        d = self.rk
        if setor:
            d = d[d["setor"].str.lower() == setor.lower()]
        if sinal:
            d = d[d["sinal"] == sinal]
        if ordenar_por in d:
            d = d.sort_values(ordenar_por, ascending=False, na_position="last")
        self.diario.append(f"consultou o ranking ({setor or 'todos os setores'}, {sinal or 'todos os sinais'}, por {ordenar_por})")
        return {"setores_disponiveis": sorted(self.rk["setor"].unique()), "acoes": [self._linha(r) for _, r in d.head(limite).iterrows()]}

    def ver_acao(self, ticker: str):
        t = ticker.strip().upper()
        if t not in set(self.rk["ticker"]):
            return {"erro": f"{t} não está na lista analisada hoje. Se valer a pena, use propor_vigiar."}
        r = self.rk.set_index("ticker").loc[t]
        ficha = self._linha({**r.to_dict(), "ticker": t})
        ficha["por_que"] = r.get("por_que")
        ficha["checagens_dividendos"] = r.get("seguranca_checks")
        mesa_ = (self.R.get("mesa") or {}).get("opinioes", {}).get(t, {})
        ficha["agentes"] = {a: {"voto": o["voto"], "argumentos": o["argumentos"][:4]} for a, o in mesa_.items()}
        ficha["noticias"] = [f"{n['titulo']} ({n['fonte']}, {n['tom']})" for n in (self.R.get("noticias") or {}).get(t, [])[:6]]
        self.diario.append(f"abriu a ficha de {t}")
        return ficha

    def comparar(self, tickers: list[str]):
        ts = [t.strip().upper() for t in tickers][:5]
        d = self.rk[self.rk["ticker"].isin(ts)]
        self.diario.append(f"comparou {', '.join(ts)}")
        return [self._linha(r) for _, r in d.iterrows()]

    def anotar(self, texto: str, ticker: str):
        if self.notas_hoje >= MAX_NOTAS_DIA:
            return {"erro": "limite de anotações de hoje atingido"}
        _salvar_nota(texto, ticker.strip().upper() or None)
        self.notas_hoje += 1
        self.diario.append(f"anotou na memória: {texto[:90]}")
        return {"ok": True}

    def propor_vigiar(self, ticker: str, motivo: str):
        if len(self.propostas) >= MAX_PROPOSTAS_DIA:
            return {"erro": "limite de propostas de hoje atingido"}
        t = ticker.strip().upper()
        if t in set(self.rk["ticker"]):
            return {"erro": f"{t} já é analisada."}
        if not _propor(t, motivo):
            return {"erro": "código inválido (formato B3, ex.: ABCD3) ou já proposto"}
        self.propostas.append({"ticker": t, "motivo": motivo})
        self.diario.append(f"propôs vigiar {t}: {motivo[:90]}")
        return {"ok": True, "obs": "entra na análise a partir da próxima apuração"}

    def levantar_alerta(self, ticker: str, texto: str, gravidade: str):
        self.alertas.append({"nivel": 1 if gravidade == "alta" else 2, "tipo": "Atlas", "ticker": ticker.strip().upper(),
                             "texto": texto[:400]})
        self.diario.append(f"levantou alerta ({gravidade}) sobre {ticker}")
        return {"ok": True}


SISTEMA = """Você é Atlas, o explorador autônomo de uma equipe de análise de ações brasileiras. O investidor faz aportes
mensais pensando no longo prazo, em renda (dividendos/JCP) e em chegar à meta de patrimônio dele.

Você tem livre-arbítrio para decidir O QUE investigar hoje. A equipe já analisou tudo por regras fixas; seu papel é
achar o que as regras não veem: contradições entre agentes, boas empresas esperando preço, riscos escondidos,
oportunidades fora da lista, e checar suas próprias teses anteriores (memória abaixo).

Regras: use as ferramentas para conferir números antes de afirmar; use a pesquisa web para fatos recentes e cite a fonte;
nunca invente dados; não prometa retorno. Anote na memória o que valer a pena acompanhar. Proponha no máximo 3 ações
novas e só com motivo concreto. Levante alerta só para algo que o investidor precisa saber hoje.
No fim, escreva um relatório curto (até 200 palavras) em português: o que investigou, o que descobriu e o que recomenda vigiar."""


def explorar_ia(R: dict, contexto_resumo: str) -> dict | None:
    import anthropic

    ferr = Ferramentas(R)
    memoria = ler_notas()
    pedido = (f"Data: {R['data']}. Resumo da apuração de hoje:\n{contexto_resumo}\n\n"
              "Sua memória (anotações dos dias anteriores):\n"
              + ("\n".join(f"- [{n['data']}] {n.get('ticker') or ''} {n['texto']}" for n in memoria) or "(vazia — primeiro dia)")
              + "\n\nComece a exploração.")
    msgs: list = [{"role": "user", "content": pedido}]
    tools = FERRAMENTAS + [ia.pesquisa_web(6)]
    client = anthropic.Anthropic()
    texto_final = None
    try:
        for _ in range(MAX_PASSOS):
            resp = client.beta.messages.create(
                model=ia.MODELO, max_tokens=16000, system=SISTEMA, messages=msgs, tools=tools,
                output_config={"effort": "medium"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            msgs.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "pause_turn":
                continue
            if resp.stop_reason == "refusal":
                break
            usos = [b for b in resp.content if b.type == "tool_use"]
            if not usos:
                texto_final = "".join(b.text for b in resp.content if b.type == "text").strip()
                break
            msgs.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": u.id, "content": ferr.executar(u.name, dict(u.input))}
                if u.name in {f["name"] for f in FERRAMENTAS}
                else {"type": "tool_result", "tool_use_id": u.id, "content": "ferramenta desconhecida", "is_error": True}
                for u in usos]})
        else:
            ferr.diario.append(f"atingiu o limite de {MAX_PASSOS} passos")
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        ferr.diario.append(f"interrompido por erro da IA ({e.__class__.__name__})")
    if not texto_final and not ferr.diario:
        return None
    return {"modo": "IA", "relatorio": texto_final or "Exploração interrompida antes do relatório final.",
            "diario": ferr.diario, "propostas": ferr.propostas, "alertas": ferr.alertas,
            "hora": datetime.now().isoformat(timespec="minutes")}


def explorar_regras(R: dict, anterior: pd.DataFrame | None) -> dict:
    """Sem IA: procura sinais fora do óbvio com regras simples."""
    rk = R["ranking"]
    achados, diario = [], [f"varreu as {len(rk)} ações procurando o que não está no topo do ranking"]
    if anterior is not None and len(anterior) and "nota" in anterior:
        delta = rk.set_index("ticker")["nota"] - anterior.set_index("ticker")["nota"]
        delta = delta.dropna().sort_values()
        if len(delta) and delta.iloc[-1] >= 3:
            achados.append(f"📈 {delta.index[-1]} foi a que mais melhorou desde a última apuração (+{delta.iloc[-1]:.0f} pontos de nota).")
        if len(delta) and delta.iloc[0] <= -3:
            achados.append(f"📉 {delta.index[0]} foi a que mais piorou ({delta.iloc[0]:.0f} pontos): vale olhar as notícias.")
        diario.append("comparou as notas com a apuração anterior")
    if "grau_Renda" in rk:
        esperando = rk[(rk["sinal"] == "Aguardar") & rk["grau_Renda"].isin(["A+", "A", "A-"]) & rk["grau_Qualidade"].isin(["A+", "A", "A-", "B+"])]
        for _, r in esperando.head(2).iterrows():
            achados.append(f"⏳ {r['ticker']}: renda {r['grau_Renda']} e qualidade {r['grau_Qualidade']} no setor, mas está acima do "
                           f"preço-teto ({brl(r['preco_teto_bazin'])}). Boa candidata para comprar numa queda.")
        diario.append("procurou boas empresas esperando preço")
        escondidas = rk[(rk["posicao"] > 10) & (rk.get("consenso", pd.Series(index=rk.index, dtype=str)).isin(["Compra forte", "Compra"]))]
        for _, r in escondidas.head(2).iterrows():
            achados.append(f"🔎 {r['ticker']} está só em {int(r['posicao'])}º no ranking, mas a mesa de agentes votou {r['consenso']}.")
        diario.append("cruzou ranking × votos da equipe")
    if not achados:
        achados.append("Nada fora do comum hoje: o ranking e a equipe estão alinhados.")
    return {"modo": "regras", "relatorio": "\n".join(achados), "diario": diario, "propostas": [], "alertas": [],
            "hora": datetime.now().isoformat(timespec="minutes")}


def explorar(R: dict, anterior: pd.DataFrame | None, contexto_resumo: str, usar_ia: bool = True) -> dict:
    escritorio.status("atlas", "trabalhando", "explorando o mercado por conta própria")
    r = explorar_ia(R, contexto_resumo) if usar_ia and not R.get("demo") and ia.disponivel() else None
    r = r or explorar_regras(R, anterior)
    for passo in r["diario"]:
        escritorio.registrar("atlas", passo)
    escritorio.status("atlas", "pausa", "exploração do dia entregue")
    return r
