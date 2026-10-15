"""Testes sem internet:  python -m pytest radar_acoes/tests -q"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acoes import alertas, analise, aporte, demo, noticias, previsao  # noqa: E402

HOJE = pd.Timestamp("2026-10-15")


def ativo(ticker="TEST3", preco=10.0, div_anual=0.8, lpa=1.2, vpa=8.0, anos=10):
    dias = pd.bdate_range(HOJE - pd.DateOffset(years=anos), HOJE)
    precos = pd.Series(np.linspace(preco * 0.7, preco, len(dias)) * (1 + 0.01 * np.sin(np.arange(len(dias)))), index=dias)
    precos.iloc[-1] = preco
    datas = [pd.Timestamp(a, m, 15) for a in range(HOJE.year - anos + 1, HOJE.year + 1) for m in (3, 9)
             if pd.Timestamp(a, m, 15) <= HOJE]
    prov = pd.Series([div_anual / 2] * len(datas), index=pd.DatetimeIndex(datas))
    info = {"longName": f"{ticker} SA", "currentPrice": preco, "trailingEps": lpa, "bookValue": vpa,
            "returnOnEquity": lpa / vpa, "profitMargins": 0.18, "debtToEquity": 60}
    return {"ticker": ticker, "info": info, "precos": precos, "proventos": prov}


def test_indicadores_basicos():
    i = analise.indicadores(ativo(), HOJE)
    assert i["proventos_media_5a"] == pytest.approx(0.8)
    assert i["dy_medio_5a"] == pytest.approx(0.08)
    assert i["preco_teto_bazin"] == pytest.approx(0.8 / 0.06)
    assert i["preco_justo_graham"] == pytest.approx((22.5 * 1.2 * 8.0) ** 0.5)
    assert i["anos_pagou_10"] == 9  # 2017..2025 completos
    assert i["meses_pagamento"] == [3, 9]


def test_sinais():
    boa = analise.ranking({"BOA3": ativo("BOA3")}, hoje=HOJE).iloc[0]
    assert boa["sinal"] == "Comprar" and boa["nota"] >= 65
    cara = analise.ranking({"CARA3": ativo("CARA3", preco=30)}, hoje=HOJE).iloc[0]
    assert cara["sinal"] in ("Aguardar", "Evitar")
    preju = analise.ranking({"PREJ3": ativo("PREJ3", lpa=-0.5)}, hoje=HOJE).iloc[0]
    assert preju["sinal"] == "Evitar"
    pouca = analise.ranking({"POUC3": ativo("POUC3", div_anual=0.2)}, hoje=HOJE).iloc[0]
    assert pouca["sinal"] != "Comprar"  # DY 2% não serve para renda


def test_previsao_e_simulador():
    f = previsao.faixa_preco(100, 0.05, 0.3, 1)
    assert f["pessimista"] < f["mediana"] < f["otimista"]
    assert f["mediana"] == pytest.approx(105)
    s = previsao.simular_aportes(1000, 2, dy=0, valorizacao=0)
    assert s["patrimonio"].iloc[-1] == pytest.approx(24000)
    s = previsao.simular_aportes(1000, 10, dy=0.08, valorizacao=0.03)
    assert s["patrimonio"].iloc[-1] > s["investido"].iloc[-1]
    assert previsao.meta_renda(10, 0.08, 0.0, 1000) == 2  # mês 1: R$ 1.000 rende 6,67; mês 2: ~R$ 2.007 rende 13,4


def test_aporte_respeita_valor_e_setor():
    base = {t: demo.gerar(t, HOJE.date()) for t in ["TAEE11", "EGIE3", "CMIG4", "BBSE3", "ITSA4", "SAPR11", "VIVT3"]}
    base.update({f"B{n}A3": ativo(f"B{n}A3", preco=10 + n) for n in range(5)})
    rk = analise.ranking(base, hoje=HOJE)
    compras, sobra = aporte.sugerir(rk, 1000, pd.DataFrame(columns=["ticker", "quantidade"]), n_ativos=6, max_por_setor=2)
    assert len(compras) > 0
    assert compras["valor"].sum() + sobra == pytest.approx(1000, abs=0.01)
    assert sobra >= 0
    assert compras.groupby("setor").size().max() <= 2


def test_noticias_classificacao():
    assert noticias.classificar("Taesa anuncia dividendos e lucro sobe 20%")["tom"] == "positiva"
    c = noticias.classificar("Empresa X corta dividendos após prejuízo")
    assert c["tom"] == "negativa" and "Proventos" in c["assuntos"]


def test_alerta_novo_provento_e_oportunidade():
    rk = analise.ranking({"BOA3": ativo("BOA3")}, hoje=HOJE)
    ant = rk.copy()
    ant["ultimo_provento_data"] = "2026-03-15"
    ant["sinal"] = "Aguardar"
    rk["ultimo_provento_data"] = "2026-09-15"
    tipos = {a["tipo"] for a in alertas.gerar(rk, ant, {}, hoje=HOJE.date())}
    assert {"Provento", "Oportunidade"} <= tipos


# ---------------------------------------------------------------- meta, backtest, confiança
from acoes import backtest, meta  # noqa: E402


def test_meta_caminho_medio_e_aporte_necessario():
    # sem rendimento: 1.000/mês leva exatamente 100 meses para 100 mil
    assert meta.meses_ate(100_000, 0, 1000, 0.0) == 100
    ap = meta.aporte_necessario(1_000_000, 0, 0.10, 240)
    assert meta.meses_ate(1_000_000, 0, ap, 0.10) <= 240
    assert meta.meses_ate(1_000_000, 0, ap * 0.97, 0.10) > 240
    assert meta.fmt_tempo(25) == "2 anos e 1 mês"


def test_meta_monte_carlo_coerente():
    r = meta.simular(1_000_000, 0, 2000, 0.12, 0.20, n=2000)
    assert r["meses_10"] < r["meses_50"] < r["meses_90"]
    med = meta.meses_ate(1_000_000, 0, 2000, 0.12)
    assert abs(r["meses_50"] - med) <= 24  # mediana perto do caminho médio (um pouco mais conservadora)
    assert r["faixas"]["chance_ate_ano"].is_monotonic_increasing
    # sem oscilação, todas as simulações batem no mesmo mês do caminho médio
    r0 = meta.simular(1_000_000, 0, 2000, 0.12, 0.0001, n=200)
    assert abs(r0["meses_50"] - med) <= 1


def test_backtest_tir_e_sem_olhar_o_futuro():
    base = {f"B{n}A3": ativo(f"B{n}A3", preco=10 + n) for n in range(4)}
    cdi = pd.Series(1.10 ** (1 / 12) - 1, index=pd.period_range("2021-01", "2026-12", freq="M"))
    r = backtest.rodar(base, anos=3, aporte=1000, cdi=cdi, hoje=HOJE.date())
    assert r["investido"] == 1000 * r["meses"]
    assert r["tir_cdi"] == pytest.approx(0.10, abs=0.002)
    # um provento gigante em out/2025 só no B0A3 não pode mudar o que foi escolhido ANTES dessa data
    corte = pd.Timestamp("2025-10-10")
    fut = dict(base)
    d0 = base["B0A3"]
    fut["B0A3"] = {**d0, "proventos": pd.concat([d0["proventos"], pd.Series([999.0], index=[corte])]).sort_index()}
    r2 = backtest.rodar(fut, anos=3, cdi=cdi, hoje=HOJE.date())
    antes = lambda c: c[pd.to_datetime(c["mes"]) <= corte].reset_index(drop=True)  # noqa: E731
    assert antes(r2["compras"]).equals(antes(r["compras"]))
    assert r2["sistema"] != r["sistema"]  # depois da data, o provento entra na conta


def test_confianca_detecta_dado_estranho():
    d = ativo("ESTR3")
    d["info"]["currentPrice"] = 20.0  # preço da cotação diverge do histórico (10)
    i = analise.ranking({"ESTR3": d}, hoje=HOJE).iloc[0]
    assert i["confianca"] == "Baixa" and i["sinal"] != "Comprar"
    ok = analise.ranking({"BOA3": ativo("BOA3")}, hoje=HOJE).iloc[0]
    assert ok["confianca"] == "Alta" and "pagou em 9" in ok["por_que"]


# ---------------------------------------------------------------- JARVIS e vigia
from acoes import jarvis, vigia  # noqa: E402


def _R():
    base = {f"B{n}A3": ativo(f"B{n}A3", preco=10 + n) for n in range(4)}
    rk = analise.ranking(base, hoje=HOJE)
    for c in ("dy_previsto", "retorno_total_esperado_aa", "volatilidade_aa", "proventos_previstos_12m"):
        rk[c] = {"dy_previsto": 0.07, "retorno_total_esperado_aa": 0.11, "volatilidade_aa": 0.25, "proventos_previstos_12m": 0.8}[c]
    rk["meses_provaveis"] = "mar, set"
    return {"data": HOJE.date(), "demo": False, "ranking": rk, "alertas": [], "noticias": {}, "backtest": None,
            "macro": {"selic": 0.14, "ipca_12m": 0.045, "cdi_liquido": 0.119, "estimado": False}}


def test_jarvis_sem_ia_responde_com_dados(monkeypatch):
    monkeypatch.setenv("JARVIS_SEM_IA", "1")
    R = _R()
    pl = {"aporte_mensal": 1000.0, "meta": 1_000_000.0, "aumento_aporte_aa": 0.05, "patrimonio_fora_bolsa": 0.0,
          "corrigir_inflacao": False, "nome": "Tony"}
    rel = jarvis.relatorio(R, pl)
    assert rel["fonte"] == "regras" and "Tony" in rel["texto"] and "R$ 1.000.000" in rel["texto"]
    resp, fonte = jarvis.perguntar("B1A3 vale a pena?", [], R, pl)
    assert fonte == "regras" and "B1A3" in resp and "preço-teto" in resp
    assert "anos" in jarvis.perguntar("quando chego no milhão?", [], R, pl)[0]


def test_vigia_avisa_uma_vez_por_dia(tmp_path, monkeypatch):
    monkeypatch.setattr(vigia, "ESTADO", tmp_path / "estado.json")
    R = _R()
    rk = R["ranking"]
    t = rk.iloc[0]["ticker"]
    rk.loc[rk["ticker"] == t, "preco_teto_bazin"] = float(rk.iloc[0]["preco"]) * 0.97  # estava acima do teto
    rk.loc[rk["ticker"] == t, "nota"] = 80.0
    fake = lambda ts: {t: float(rk.iloc[0]["preco"]) * 0.95}  # noqa: E731  cai 5%: abaixo do teto e queda forte
    novos = vigia.checar(R, [], fake)
    assert len(novos) == 2 and any("preço-teto" in n for n in novos) and any("cai 5,0%" in n for n in novos)
    assert vigia.checar(R, [], fake) == []


# ---------------------------------------------------------------- mesa, verificação cruzada, memória, previsor
from acoes import memoria, mesa, previsor  # noqa: E402


def test_mesa_vota_veta_e_confere():
    R = _R()
    rk = R["ranking"]
    rk.loc[0, "lpa"] = -0.3  # prejuízo → Rex veta
    rk.loc[1, "payout"] = 0.97  # quase todo o lucro vira provento: Dora aprova, Fausto contesta
    m = mesa.reuniao(rk, {r["ticker"]: ativo(r["ticker"])["precos"] for _, r in rk.iterrows()}, {}, R["macro"],
                     data=str(HOJE.date()), usar_ia=False)
    c = m["consenso"].set_index("ticker")
    assert c.loc[rk.loc[0, "ticker"], "vetado"] and c.loc[rk.loc[0, "ticker"], "consenso"] == "Vetado"
    assert len(m["opinioes"][rk.loc[2, "ticker"]]) == 7
    assert any(v["verificador"].endswith("Fausto") and v["ticker"] == rk.loc[1, "ticker"] for v in m["verificacoes"])


def test_memoria_aprende_com_o_placar(tmp_path, monkeypatch):
    monkeypatch.setattr(memoria, "ARQ", tmp_path / "mem.csv")
    dias = pd.bdate_range("2025-01-01", periods=200)
    sobe = pd.Series(np.linspace(10, 14, 200), index=dias)
    cai = pd.Series(np.linspace(10, 7, 200), index=dias)
    precos = {"SOBE3": sobe, "CAI3": cai}
    # agente "bom" votou certo, agente "ruim" votou errado, em 20 dias diferentes
    for d in dias[:20]:
        ops = {"SOBE3": {"bom": {"voto": 1}, "ruim": {"voto": -1}}, "CAI3": {"bom": {"voto": -1}, "ruim": {"voto": 1}}}
        memoria.registrar(ops, {"SOBE3": float(sobe[d]), "CAI3": float(cai[d])}, d.date())
    av = memoria.avaliar(precos, {})
    pa = av["por_agente"].set_index("agente")
    assert pa.loc["bom", "acerto"] == 1.0 and pa.loc["ruim", "acerto"] == 0.0
    monkeypatch.setattr(memoria, "AMOSTRA_MINIMA", 10)
    f = memoria.fatores(av)
    assert f["bom"] == 1.5 and f["ruim"] == 0.5


def test_previsor_sem_vantagem_fica_neutro():
    rng = np.random.default_rng(1)
    dias = pd.bdate_range("2018-01-01", "2026-10-15")
    precos = {f"R{i}A3": pd.Series(20 * np.exp(np.cumsum(rng.normal(0, 0.02, len(dias)))), index=dias) for i in range(6)}
    prev = previsor.prever_todas(precos)
    val = previsor.validar_historico(precos)
    cal, fator = previsor.calibrar(prev, val)
    assert 0.40 < val["acerto"] < 0.60  # passeio aleatório: ninguém prevê
    if fator == 0:
        assert (cal["direcao"] == "Indefinida").all()
