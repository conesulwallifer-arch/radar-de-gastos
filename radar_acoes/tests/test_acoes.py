"""Testes sem internet:  python -m pytest radar_acoes/tests -q"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acoes import alertas, analise, aporte, demo, noticias, previsao  # noqa: E402

HOJE = pd.Timestamp("2026-10-15")


@pytest.fixture(autouse=True)
def _escritorio_isolado(tmp_path, monkeypatch):
    """Os testes nunca escrevem no diário/status reais da equipe."""
    from acoes import escritorio
    monkeypatch.setattr(escritorio, "STATUS", tmp_path / "status.json")
    monkeypatch.setattr(escritorio, "DIARIO", tmp_path / "diario.jsonl")


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


# ---------------------------------------------------------------- AURUM e vigia
from acoes import aurum, vigia  # noqa: E402


def _R():
    base = {f"B{n}A3": ativo(f"B{n}A3", preco=10 + n) for n in range(4)}
    rk = analise.ranking(base, hoje=HOJE)
    for c in ("dy_previsto", "retorno_total_esperado_aa", "volatilidade_aa", "proventos_previstos_12m"):
        rk[c] = {"dy_previsto": 0.07, "retorno_total_esperado_aa": 0.11, "volatilidade_aa": 0.25, "proventos_previstos_12m": 0.8}[c]
    rk["meses_provaveis"] = "mar, set"
    return {"data": HOJE.date(), "demo": False, "ranking": rk, "alertas": [], "noticias": {}, "backtest": None,
            "macro": {"selic": 0.14, "ipca_12m": 0.045, "cdi_liquido": 0.119, "estimado": False}}


def test_aurum_sem_ia_responde_com_dados(monkeypatch):
    monkeypatch.setenv("AURUM_SEM_IA", "1")
    R = _R()
    pl = {"aporte_mensal": 1000.0, "meta": 1_000_000.0, "aumento_aporte_aa": 0.05, "patrimonio_fora_bolsa": 0.0,
          "corrigir_inflacao": False, "nome": "Ana"}
    rel = aurum.relatorio(R, pl)
    assert rel["fonte"] == "regras" and "Ana" in rel["texto"] and "R$ 1.000.000" in rel["texto"]
    resp, fonte = aurum.perguntar("B1A3 vale a pena?", [], R, pl)
    assert fonte == "regras" and "B1A3" in resp and "preço-teto" in resp
    assert "anos" in aurum.perguntar("quando chego no milhão?", [], R, pl)[0]


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
    assert len(m["opinioes"][rk.loc[2, "ticker"]]) == len(mesa.AGENTES)
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


# ---------------------------------------------------------------- balanços, notas setoriais, agenda, Atlas
from acoes import agenda, atlas, fundamentos  # noqa: E402


def _demos(lucro, ativos, fco, capex, divs, acoes=(1e9, 1e9, 1e9), receita=(100, 90, 80), bruto=(40, 34, 30)):
    anos = [pd.Timestamp(2025, 12, 31), pd.Timestamp(2024, 12, 31), pd.Timestamp(2023, 12, 31)]
    df = lambda d: pd.DataFrame(d, index=anos).T  # noqa: E731
    return {"dre": df({"Net Income": lucro, "Total Revenue": receita, "Gross Profit": bruto}),
            "balanco": df({"Total Assets": ativos, "Current Assets": [a * .3 for a in ativos], "Current Liabilities": [a * .2 for a in ativos],
                           "Long Term Debt": [a * .2 for a in ativos], "Ordinary Shares Number": list(acoes)}),
            "fluxo": df({"Operating Cash Flow": fco, "Capital Expenditure": capex, "Cash Dividends Paid": divs})}


def test_piotroski_e_cobertura_por_caixa():
    bom = fundamentos.extrair(_demos([12, 10, 9], [100, 100, 100], [15, 12, 11], [-5, -5, -5], [-6, -5, -5]))
    p = fundamentos.piotroski(bom)
    assert p["f_testes"] == 9 and p["f_score"] >= 7
    c = fundamentos.caixa(bom, 10.0, 0.6)
    assert c["fcl"] == 10 and c["payout_fcl"] == pytest.approx(0.6)
    ruim = fundamentos.extrair(_demos([-2, 5, 6], [100, 100, 100], [-1, 6, 7], [-5, -5, -5], [-4, -4, -4], acoes=(1.2e9, 1e9, 1e9),
                                         receita=(80, 90, 100), bruto=(24, 30, 40)))
    assert fundamentos.piotroski(ruim)["f_score"] <= 3
    assert fundamentos.caixa(ruim, 10.0, 0.4)["payout_fcl"] == float("inf")  # paga com caixa livre negativo


def test_ddm_reage_a_selic_e_bancos_sem_dados():
    alto = fundamentos.preco_justo_ddm(1.0, 0.03, 0.15)
    baixo = fundamentos.preco_justo_ddm(1.0, 0.03, 0.08)
    assert baixo > alto > 0  # juros maiores exigem preço menor
    banco = fundamentos.analisar({"preco": 10, "proventos_media_5a": 0.8, "setor": "Bancos", "anos_pagou_10": 10,
                                  "payout": 0.5, "roe": 0.2, "cresc_proventos_5a": 0.05}, None, 0.14)
    assert banco["f_score_9"] != banco["f_score_9"]  # sem balanço: não inventa nota
    assert banco["seguranca_div"] == 100  # checagens disponíveis todas aprovadas


def test_notas_setoriais_comparam_dentro_do_setor():
    base = {f"B{n}A3": ativo(f"B{n}A3", preco=10 + 2 * n) for n in range(5)}
    rk = analise.ranking(base, hoje=HOJE)
    assert {"grau_Valor", "grau_Renda", "pct_Valor"} <= set(rk.columns)
    mais_barata = rk.sort_values("preco").iloc[0]
    assert mais_barata["pct_Valor"] == rk["pct_Valor"].max()


def test_agenda_projeta_meses_de_pagamento():
    d = ativo("AGD3")
    rk = analise.ranking({"AGD3": d}, hoje=HOJE)
    rk["proventos_previstos_12m"] = 0.8
    pj = agenda.projetar({"AGD3": 100}, {"AGD3": d["proventos"]}, rk, HOJE.date())
    assert set(pj["mes"].str[:3]) == {"mar", "set"}
    assert pj["valor"].sum() == pytest.approx(80, rel=0.01)


def test_atlas_regras_e_limites(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas, "NOTAS", tmp_path / "n.json")
    monkeypatch.setattr(atlas, "DESCOBERTAS", tmp_path / "d.txt")
    R = _R()
    f = atlas.Ferramentas(R)
    assert json.loads(f.executar("propor_vigiar", {"ticker": "abc", "motivo": "x"}))["erro"]  # código inválido
    assert json.loads(f.executar("propor_vigiar", {"ticker": "KEPL3", "motivo": "x"}))["ok"]
    assert "erro" in json.loads(f.executar("propor_vigiar", {"ticker": R["ranking"].iloc[0]["ticker"], "motivo": "x"}))
    for k in range(atlas.MAX_NOTAS_DIA + 1):
        r = json.loads(f.executar("anotar", {"texto": f"nota {k}", "ticker": ""}))
    assert "erro" in r and len(atlas.ler_notas()) == atlas.MAX_NOTAS_DIA
    atlas.limpar_descobertas(["KEPL3"])
    assert atlas.ler_descobertas() == []
    assert atlas.explorar(R, None, "", usar_ia=False)["modo"] == "regras"


# ---------------------------------------------------------------- escritório, agente 24h, antecipação
from acoes import escritorio, macro  # noqa: E402


def test_escritorio_status_e_diario():
    escritorio.status(["renda", "risco"], "trabalhando", "analisando 57 empresas")
    escritorio.registrar("renda", "analisou 57 empresas")
    escritorio.SILENCIOSO = True
    escritorio.registrar("renda", "não deve aparecer (teste)")
    escritorio.SILENCIOSO = False
    assert escritorio.ler_status()["risco"]["estado"] == "trabalhando"
    d = escritorio.ler_diario()
    assert len(d) == 1 and d[0]["agente"] == "renda" and escritorio.dias_trabalhados() == 1


def test_agente_coloca_trabalho_em_dia():
    from datetime import datetime
    import agente
    f = agente.FUSO
    qui_manha = datetime(2026, 10, 15, 9, 0, tzinfo=f)
    seg_manha = datetime(2026, 10, 19, 8, 0, tzinfo=f)
    assert str(agente.ultimo_pregao_fechado(qui_manha)) == "2026-10-14"
    assert str(agente.ultimo_pregao_fechado(seg_manha)) == "2026-10-16"  # pula o fim de semana
    assert str(agente.ultimo_pregao_fechado(datetime(2026, 10, 15, 19, 0, tzinfo=f))) == "2026-10-15"


def test_leitura_dos_juros_esperados():
    from datetime import date
    prox = f"selic_{date.today().year + 1}"
    assert "caindo" in macro.leitura_juros(0.14, {prox: 0.11})
    assert "subindo" in macro.leitura_juros(0.14, {prox: 0.16})
    assert "estável" in macro.leitura_juros(0.14, {prox: 0.1405})
    assert macro.leitura_juros(0.14, {}) is None


def test_proximo_balanco_so_futuro():
    d = ativo("BAL3")
    d["info"]["earningsTimestamp"] = int(pd.Timestamp("2026-10-20").timestamp())
    assert analise.indicadores(d, HOJE)["proximo_balanco"] == "2026-10-20"
    d["info"]["earningsTimestamp"] = int(pd.Timestamp("2026-09-01").timestamp())
    assert analise.indicadores(d, HOJE)["proximo_balanco"] is None


def test_alertas_toleram_datas_ausentes():
    """Empresa sem data-ex, sem balanço marcado e sem proventos não pode derrubar a apuração (célula vazia = NaN)."""
    base = {"COM3": ativo("COM3"), "SEM3": ativo("SEM3")}
    base["COM3"]["info"]["earningsTimestamp"] = int(pd.Timestamp("2026-10-18").timestamp())
    base["COM3"]["info"]["exDividendDate"] = int(pd.Timestamp("2026-10-20").timestamp())
    base["SEM3"]["proventos"] = pd.Series(dtype=float)
    rk = analise.ranking(base, hoje=HOJE)
    assert rk["proximo_balanco"].isna().any() and rk["ex_dividendo"].isna().any()
    ant = rk.copy()
    tipos = {a["tipo"] for a in alertas.gerar(rk, ant, {}, hoje=HOJE.date())}
    assert "Balanço" in tipos and "Data-com" in tipos and "Provento" not in tipos


def test_sala_ilustrada_desenha_todos_os_agentes():
    from acoes import visual
    for aid in escritorio.EQUIPE:
        for estado in ("trabalhando", "vigiando", "pausa", "erro"):
            svg = visual._uma_linha(visual.boneco(aid, estado))
            assert svg.startswith("<svg") and svg.endswith("</svg>")
            assert "\n" not in svg and "$" not in svg  # o Streamlit não pode quebrar o desenho
            assert visual.EQUIPE_NOME[aid].upper() in svg  # plaquinha com o nome na mesa


def test_sala_3d_tem_arquivos_e_dados(monkeypatch):
    from pathlib import Path
    from acoes import visual
    raiz = Path(__file__).resolve().parent.parent
    for arq in ("static/three.module.min.js", "static/OrbitControls.js", "static/sala3d.js", "static/LICENSE-three.txt"):
        assert (raiz / arq).exists(), arq
    assert "enableStaticServing = true" in (raiz / ".streamlit/config.toml").read_text()
    capturado = {}
    import streamlit as st
    import streamlit.components.v1 as comp
    monkeypatch.setattr(comp, "html", lambda html, height: capturado.update(html=html, altura=height))
    monkeypatch.setattr(st, "iframe", lambda src, height: capturado.update(html=src, altura=height), raising=False)
    mesas = [{"id": a, "nome": n, "cargo": c, "estado": "trabalhando"} for a, (n, _, c) in escritorio.EQUIPE.items()]
    visual.sala_3d(mesas, True, 14, [("TAEE11", 34.5, 0.012), ("VALE3", 60.0, float("nan"))])
    h = capturado["html"]
    assert '"three": "/app/static/three.module.min.js"' in h and "/app/static/sala3d.js" in h
    dados = json.loads(h.split("window.SALA_DADOS = ")[1].split(";</script>")[0])
    assert len(dados["agentes"]) == len(escritorio.EQUIPE) and dados["pregao"] is True and dados["fita"][1][2] == 0.0  # NaN vira 0


# ---------------------------------------------------------------- mercado ao vivo
from acoes import aovivo  # noqa: E402


def _yf_lote(series: dict, tz="America/Sao_Paulo") -> pd.DataFrame:
    """Imita o formato do yf.download(..., group_by='ticker'): colunas (símbolo, campo), índice com fuso."""
    partes = {}
    for sym, s in series.items():
        s = s.copy()
        s.index = s.index.tz_localize(tz)
        partes[(sym, "Close")] = s
        partes[(sym, "Open")] = s
    return pd.DataFrame(partes)


def test_mercado_ao_vivo_variacao_do_dia():
    ontem = pd.date_range("2026-10-26 10:00", periods=84, freq="5min")
    hoje = pd.date_range("2026-10-27 10:00", periods=30, freq="5min")
    intra = _yf_lote({
        "SOBE3.SA": pd.Series([10.0] * 84 + list(np.linspace(10.1, 11.0, 30)), index=ontem.append(hoje)),
        "CAI3.SA": pd.Series([20.0] * 84 + list(np.linspace(19.9, 19.0, 30)), index=ontem.append(hoje)),
        "^BVSP": pd.Series([130000.0] * 84 + [131300.0] * 30, index=ontem.append(hoje)),
    })
    dias = pd.DatetimeIndex(["2026-10-23", "2026-10-26", "2026-10-27"])
    diario = _yf_lote({"SOBE3.SA": pd.Series([9.0, 10.0, 11.0], index=dias),
                       "CAI3.SA": pd.Series([21.0, 20.0, 19.0], index=dias),
                       "^BVSP": pd.Series([129000.0, 130000.0, 131300.0], index=dias)})
    sims = ["SOBE3.SA", "CAI3.SA", "^BVSP"]
    df = aovivo.resumir(aovivo._colunas(intra, sims), aovivo._colunas(diario, sims)).set_index("ticker")
    assert df.loc["SOBE3", "var_dia"] == pytest.approx(0.10) and df.loc["CAI3", "var_dia"] == pytest.approx(-0.05)
    assert df.loc["^BVSP", "var_dia"] == pytest.approx(0.01)
    assert len(df.loc["SOBE3", "grafico"]) == 30 and df.loc["SOBE3", "maxima"] == pytest.approx(11.0)
    assert str(df.loc["SOBE3", "pregao"]) == "2026-10-27"
    assert aovivo.placar(df.drop(index="^BVSP")) == {"sobem": 1, "caem": 1, "estaveis": 0}
    # sem o diário, usa a última cotação de ontem como referência
    so_intra = aovivo.resumir(aovivo._colunas(intra, sims), {}).set_index("ticker")
    assert so_intra.loc["CAI3", "var_dia"] == pytest.approx(-0.05)


# ---------------------------------------------------------------- equipe de previsibilidade (Otto, Bento, Sofia)
from acoes import oraculos  # noqa: E402


def test_otto_prev_estavel_e_detecta_corte():
    dias = pd.bdate_range("2014-01-01", "2026-10-15")
    precos = pd.Series(20.0, index=dias)
    hoje = pd.Timestamp("2026-10-15")
    estavel = pd.Series(1.0, index=pd.DatetimeIndex([pd.Timestamp(a, m, 15) for a in range(2014, 2026) for m in (3, 9)]))
    r = {"proventos_previstos_12m": 2.0, "preco": 20.0}
    o = oraculos.otto(r, estavel, precos, hoje)
    assert o["otto_acerto"] == 1.0 and o["otto_prob_corte"] < 0.12 and o["otto_anos_testados"] >= 5
    # empresa que corta: paga 1,0 por semestre e despenca para 0,2 nos últimos anos, com lucro caindo e payout > 100%
    valores = [1.0 if a < 2022 else 0.2 for a in range(2014, 2026) for _ in (3, 9)]
    corta = pd.Series(valores, index=estavel.index)
    o2 = oraculos.otto({"proventos_previstos_12m": 0.5, "preco": 20.0, "payout": 1.3, "cresc_lucro": -0.4}, corta, precos, hoje)
    assert o2["otto_prob_corte"] > 0.40 and "paga mais do que lucra" in o2["otto_motivos_corte"]
    # sem colar: a previsão do ano X só usa anos anteriores (mudar 2025 não muda o previsto para 2024)
    h1 = oraculos.otto_historico(corta, precos, hoje).set_index("ano")
    mexido = corta.copy()
    mexido[mexido.index.year == 2025] = 9.0
    h2 = oraculos.otto_historico(mexido, precos, hoje).set_index("ano")
    assert h1.loc[2024, "previsto"] == h2.loc[2024, "previsto"] and h1.loc[2025, "real"] != h2.loc[2025, "real"]


def test_bento_calibrado_em_passeio_aleatorio():
    rng = np.random.default_rng(3)
    dias = pd.bdate_range("2019-01-01", periods=1800)
    precos = {f"A{i}": pd.Series(30 * np.exp(np.cumsum(rng.normal(0, 0.015, len(dias)))), index=dias) for i in range(20)}
    v = oraculos.bento_validacao(precos)
    assert v["n"] > 1000 and abs(v["real_80"] - 0.80) < 0.10 and abs(v["real_50"] - 0.50) < 0.10
    b = oraculos.bento({"preco": float(precos["A0"].iloc[-1]), "preco_teto_bazin": float(precos["A0"].iloc[-1]) * 0.9}, precos["A0"])
    assert b["bento_preco_50"] < b["bento_preco_80"] <= float(precos["A0"].iloc[-1])
    assert 0 < b["bento_prob_tocar_teto"] < 1


def test_sofia_nao_vota_quando_e_so_ruido():
    rng = np.random.default_rng(11)
    dias = pd.bdate_range("2016-01-01", periods=2500)
    precos = {f"R{i}": pd.Series(20 * np.exp(np.cumsum(rng.normal(0, 0.018, len(dias)))), index=dias) for i in range(25)}
    s = oraculos.sofia(precos, {})
    assert s["validacao"]["n"] > 300
    assert s["fator"] == 0.0  # sem padrão real, ela não vota
    assert s["previsoes"]["sofia_prob_bruta"].between(0.35, 0.65).all()  # nada de "certeza" em cima de ruído
    # com um padrão real (as que mais pagam dividendos rendem mais), ela encontra e ganha voz
    precos2, prov2 = {}, {}
    for i in range(25):
        dy = 0.02 + 0.10 * i / 24
        ret = rng.normal(0.00012 + 0.9 * dy / 252, 0.012, len(dias))
        precos2[f"D{i}"] = pd.Series(20 * np.exp(np.cumsum(ret)), index=dias)
        datas = dias[::63]
        prov2[f"D{i}"] = pd.Series([float(precos2[f"D{i}"].loc[d]) * dy / 4 for d in datas], index=datas)
    s2 = oraculos.sofia(precos2, prov2)
    assert s2["fator"] > 0 and s2["validacao"]["t_stat"] >= 2 and s2["pesos"]["dividendos dos últimos 12 meses"] > 0


# ---------------------------------------------------------------- mesa de trading
from acoes import trading  # noqa: E402


def test_trading_simula_alvo_stop_e_protecao():
    osc = 0.01  # risco = 1,2 × 1% × √20 ≈ 5,4% → stop 94,6 e alvo ≈ 110,7
    stop, alvo = trading.niveis(100.0, osc)
    assert stop == pytest.approx(100 * (1 - 1.2 * 0.01 * np.sqrt(20)), rel=1e-6) and alvo == pytest.approx(100 + 2 * (100 - stop))
    sobe = np.array([100, 103, 106, 109, 112.0])
    r = trading.simular(sobe, 0, osc)
    assert r["motivo"] == "alvo" and r["ret"] == pytest.approx(alvo / 100 - 1 - trading.CUSTO)
    cai = np.array([100, 98, 96, 93.0, 99])
    assert trading.simular(cai, 0, osc)["motivo"] == "stop"
    # subiu 1× o risco (stop vai para a entrada) e depois devolveu tudo: sai no zero a zero, não no prejuízo
    devolve = np.array([100, 103, 106, 101, 99.5, 98.0])
    r = trading.simular(devolve, 0, osc)
    assert r["motivo"] == "empate" and r["ret"] > -0.01
    # operação que ainda não terminou não entra na estatística
    assert trading.simular(np.array([100, 101, 100.5]), 0, osc) is None


def test_trading_nao_aprova_padrao_em_passeio_aleatorio():
    rng = np.random.default_rng(5)
    dias = pd.bdate_range("2014-01-01", periods=3000)
    precos = {f"P{i}": pd.Series(25 * np.exp(np.cumsum(rng.normal(0, 0.017, len(dias)))), index=dias) for i in range(30)}
    bt = trading.backtest(precos, {})
    assert len(bt["padroes"]) == 5 and (bt["padroes"]["status"] != "✅ Aprovado").all()
    assert bt["chute"]["n"] > 1000


def test_trading_posicao_e_acompanhamento(tmp_path, monkeypatch):
    pos = trading.tamanho_posicao(10_000, 0.01, 20.0, 18.0)  # arrisca R$ 100: 2,00 por ação → 50 ações
    assert pos["quantidade"] == 50 and pos["perda_maxima"] == pytest.approx(100.0)
    assert trading.tamanho_posicao(1_000, 0.05, 20.0, 19.9)["quantidade"] == 50  # nunca mais que o capital
    monkeypatch.setattr(trading, "OPERACOES", tmp_path / "ops.csv")
    monkeypatch.setattr(trading, "ESTADO_ALERTAS", tmp_path / "estado.json")
    trading.salvar_operacoes(pd.DataFrame([
        {"ticker": "aaaa3", "data_compra": "2026-10-01", "preco_compra": 10.0, "quantidade": 100, "stop": 9.0, "alvo": 12.0, "status": "aberta"},
        {"ticker": "BBBB4", "data_compra": "2026-10-01", "preco_compra": 20.0, "quantidade": 50, "stop": 18.0, "alvo": 24.0, "status": "aberta"},
        {"ticker": "CCCC3", "data_compra": "2026-10-01", "preco_compra": 30.0, "quantidade": 10, "stop": 27.0, "alvo": 36.0, "status": "fechada"},
    ]))
    ac = trading.acompanhar(trading.ler_operacoes(), {"AAAA3": 12.5, "BBBB4": 17.5, "CCCC3": 40.0}).set_index("ticker")
    assert "ALVO" in ac.loc["AAAA3", "o_que_fazer"] and "STOP" in ac.loc["BBBB4", "o_que_fazer"] and "CCCC3" not in ac.index
    assert ac.loc["AAAA3", "resultado_rs"] == pytest.approx(250.0)
    msgs = trading.alertas_operacoes({"AAAA3": 12.5, "BBBB4": 17.5})
    assert len(msgs) == 2 and trading.alertas_operacoes({"AAAA3": 12.5, "BBBB4": 17.5}) == []  # uma vez por dia
