"""Mesa de analistas: onze agentes especialistas analisam cada ação, votam e o AURUM consolida o consenso.

Cada agente olha a ação por um ângulo e devolve um voto de -2 (fortemente contra) a +2 (fortemente a favor),
com os argumentos. O Gestor de Risco pode VETAR (ex.: prejuízo, dado duvidoso, notícia grave).
Com a chave da IA, cada especialista também é um agente Claude que revisa as melhores candidatas, e o
analista de notícias pesquisa a internet; os votos da IA são somados aos das regras.
"""
from __future__ import annotations

import json
import time
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import escritorio, ia


@dataclass
class Opiniao:
    voto: int = 0
    argumentos: list[str] = field(default_factory=list)
    veto: bool = False

    def add(self, delta: int, texto: str):
        self.voto += delta
        self.argumentos.append(texto)


def _p(x, c=1):
    return "—" if x is None or x != x else f"{x * 100:.{c}f}%".replace(".", ",")


def _ok(x):
    return x is not None and x == x


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


# ------------------------------------------------------------------ os agentes
class Agente:
    id = nome = icone = especialidade = apelido = ""
    peso = 1.0

    def avaliar(self, r: pd.Series, ctx: dict) -> Opiniao:
        raise NotImplementedError


class Renda(Agente):
    id, nome, icone, peso = "renda", "Analista de Dividendos", "💰", 1.3
    apelido = "Dora"
    especialidade = "Quanto a empresa paga, com que regularidade e se os proventos crescem."

    def avaliar(self, r, ctx):
        o = Opiniao()
        dy, anos = r["dy_medio_5a"], int(r["anos_pagou_10"])
        if _ok(dy) and dy >= 0.08 and anos >= 9:
            o.add(2, f"Excelente pagadora: {_p(dy)} ao ano em média e pagou em {anos} dos últimos 10 anos.")
        elif _ok(dy) and dy >= 0.06 and anos >= 8:
            o.add(1, f"Boa pagadora: {_p(dy)} ao ano, pagou em {anos} de 10 anos.")
        elif not _ok(dy) or dy < 0.04:
            o.add(-1, f"Paga pouco para quem busca renda ({_p(dy)} ao ano).")
        else:
            o.argumentos.append(f"Proventos medianos: {_p(dy)} ao ano.")
        if anos < 6:
            o.add(-1, f"Irregular: só pagou em {anos} dos últimos 10 anos.")
        g = r.get("cresc_proventos_5a")
        if _ok(g) and g >= 0.05:
            o.add(1, f"Proventos crescendo {_p(g)} ao ano.")
        elif _ok(g) and g <= -0.10:
            o.add(-1, f"Proventos encolhendo {_p(-g)} ao ano.")
        pay = r.get("payout")
        if _ok(pay) and pay > 1.0:
            o.add(-1, f"Paga mais do que lucra (payout {_p(pay, 0)}): não é sustentável.")
        if _ok(r.get("dy_12m")) and _ok(dy) and dy > 0 and r["dy_12m"] > 2 * dy:
            o.argumentos.append("Atenção: os últimos 12 meses tiveram provento extraordinário, que pode não se repetir.")
        seg = r.get("seguranca_div")
        if _ok(seg):
            falhas = [c[2:] for c in (r.get("seguranca_checks") if isinstance(r.get("seguranca_checks"), list) else []) if c.startswith("❌")]
            if seg >= 80:
                o.add(1, f"Dividendos seguros: {seg:.0f}/100 nas checagens de segurança.")
            elif seg <= 40:
                o.add(-1, f"Dividendos em risco: só {seg:.0f}/100 nas checagens" + (f" (falhou: {', '.join(falhas[:2]).lower()})." if falhas else "."))
            else:
                o.argumentos.append(f"Segurança dos dividendos: {seg:.0f}/100.")
        o.voto = int(np.clip(o.voto, -2, 2))
        return o


class Fundamentos(Agente):
    id, nome, icone, peso = "fundamentos", "Analista Fundamentalista", "🏛️", 1.1
    apelido = "Fausto"
    especialidade = "Qualidade do negócio: lucro, rentabilidade, margens e dívida."

    def avaliar(self, r, ctx):
        o = Opiniao()
        roe, mg, lpa = r.get("roe"), r.get("margem_liquida"), r.get("lpa")
        if not _ok(lpa) or lpa <= 0:
            o.add(-2, "Está dando prejuízo.")
        elif _ok(roe) and roe >= 0.18 and (not _ok(mg) or mg >= 0.12):
            o.add(2, f"Negócio muito rentável: ROE de {_p(roe)}" + (f" e margem de {_p(mg)}." if _ok(mg) else "."))
        elif _ok(roe) and roe >= 0.12:
            o.add(1, f"Rentabilidade boa: ROE de {_p(roe)}.")
        elif _ok(roe) and roe < 0.06:
            o.add(-1, f"Rentabilidade fraca: ROE de {_p(roe)}.")
        fin = r["setor"] in ("Bancos", "Seguros", "Holdings", "Bolsa e serviços financeiros")
        d = r.get("divida_pl")
        if not fin and _ok(d) and d > 2.0:
            o.add(-1, f"Endividada: dívida de {d:.1f}× o patrimônio.".replace(".", ","))
        elif not fin and _ok(d) and d < 0.5:
            o.argumentos.append("Dívida baixa.")
        cl = r.get("cresc_lucro")
        if _ok(cl) and cl <= -0.20:
            o.add(-1, f"Lucro caiu {_p(-cl)} no último ano.")
        elif _ok(cl) and cl >= 0.15:
            o.add(1, f"Lucro cresceu {_p(cl)} no último ano.")
        fs = r.get("f_score_9")
        if _ok(fs):
            if fs >= 7:
                o.add(1, f"Piotroski {fs:.0f}/9: balanço melhorando em quase todos os testes.")
            elif fs <= 3:
                o.add(-1, f"Piotroski {fs:.0f}/9: balanço piorando.")
            else:
                o.argumentos.append(f"Piotroski {fs:.0f}/9.")
        g = r.get("grau_Qualidade")
        if g and g != "—":
            o.argumentos.append(f"Nota de Qualidade comparada ao setor: {g}.")
        o.voto = int(np.clip(o.voto, -2, 2))
        return o


class Valuation(Agente):
    id, nome, icone, peso = "valuation", "Analista de Valuation", "🏷️", 1.0
    apelido = "Vitória"
    especialidade = "Se o preço está barato ou caro: preço-teto, preço justo, P/L e P/VP."

    def avaliar(self, r, ctx):
        o = Opiniao()
        mb, mg = r.get("margem_bazin"), r.get("margem_graham")
        if _ok(mb):
            if mb >= 0.15:
                o.add(2, f"Bem barata: {_p(mb)} abaixo do preço-teto.")
            elif mb >= 0:
                o.add(1, f"Abaixo do preço-teto ({_p(mb)} de margem).")
            elif mb <= -0.20:
                o.add(-2, f"Cara para renda: {_p(-mb)} acima do preço-teto.")
            else:
                o.add(-1, f"Um pouco acima do preço-teto ({_p(-mb)}).")
        if _ok(mg) and mg >= 0.30:
            o.add(1, f"Preço justo de Graham {_p(mg)} acima do preço atual.")
        md_ = r.get("margem_ddm")
        if _ok(md_):
            o.argumentos.append(f"Pelo modelo de dividendos descontados (Gordon), o preço justo é "
                                f"{_p(abs(md_))} {'acima' if md_ >= 0 else 'abaixo'} do preço atual.")
            if md_ >= 0.15:
                o.add(1, "Os dividendos futuros, trazidos a valor presente, justificam um preço bem maior.")
        g = r.get("grau_Valor")
        if g and g != "—":
            o.argumentos.append(f"Nota de Valor comparada ao setor: {g}.")
        pl = r.get("pl")
        if _ok(pl) and pl > 20:
            o.add(-1, f"P/L alto ({pl:.0f} anos de lucro no preço).")
        elif _ok(pl) and 0 < pl < 7:
            o.argumentos.append(f"P/L baixo ({pl:.1f}).".replace(".", ","))
        o.voto = int(np.clip(o.voto, -2, 2))
        return o


class Tendencia(Agente):
    id, nome, icone, peso = "tendencia", "Analista de Tendência", "📈", 0.6
    apelido = "Téo"
    especialidade = "O momento do preço: média de 200 dias, quedas em andamento, distância do topo."

    def avaliar(self, r, ctx):
        o = Opiniao()
        p = ctx["precos"].get(r["ticker"])
        if p is None or len(p) < 260:
            o.argumentos.append("Histórico curto para analisar tendência.")
            return o
        ult = float(p.iloc[-1])
        mm200 = float(p.iloc[-200:].mean())
        d = ult / mm200 - 1
        r3 = ult / float(p.iloc[-63]) - 1
        topo = float(p.iloc[-252:].max())
        if r3 <= -0.25:
            o.add(-1, f"Queda forte em andamento ({_p(r3)} em 3 meses): melhor esperar estabilizar.")
        elif d <= -0.10 and r["nota"] >= 60:
            o.add(1, f"Boa empresa {_p(-d)} abaixo da média de 200 dias: desconto temporário.")
        elif d >= 0.25:
            o.add(-1, f"Preço esticado: {_p(d)} acima da média de 200 dias.")
        else:
            o.argumentos.append(f"Preço {_p(d)} em relação à média de 200 dias; sem extremos.")
        o.argumentos.append(f"Está {_p(1 - ult / topo)} abaixo da máxima de 12 meses.")
        return o


class Noticias(Agente):
    id, nome, icone, peso = "noticias", "Analista de Notícias", "📰", 0.6
    apelido = "Nina"
    especialidade = "O que a imprensa diz da empresa nos últimos 30 dias (tom e riscos)."
    GRAVES = ["recuperacao judicial", "fraude", "falencia", "calote", "corta dividendos", "suspende dividendos",
              "investigacao", "operacao da policia", "rombo"]

    def avaliar(self, r, ctx):
        o = Opiniao()
        itens = ctx["noticias"].get(r["ticker"], [])
        if not itens:
            o.argumentos.append("Sem notícias coletadas para esta ação.")
            return o
        pos = sum(1 for x in itens if x["tom"] == "positiva")
        neg = sum(1 for x in itens if x["tom"] == "negativa")
        graves = [x for x in itens if any(g in _norm(x["titulo"]) for g in self.GRAVES)]
        if graves:
            o.add(-2, f"Notícia grave: “{graves[0]['titulo']}” ({graves[0]['fonte']}).")
            o.veto = any(g in _norm(x["titulo"]) for x in graves for g in ("recuperacao judicial", "fraude", "falencia"))
        elif neg >= pos + 2:
            o.add(-1, f"Noticiário negativo: {neg} negativas × {pos} positivas.")
        elif pos >= neg + 2:
            o.add(1, f"Noticiário positivo: {pos} positivas × {neg} negativas.")
        else:
            o.argumentos.append(f"Noticiário equilibrado ({pos} positivas, {neg} negativas).")
        prov = [x for x in itens if "Proventos" in x["assuntos"] and x["tom"] == "positiva"]
        if prov:
            o.argumentos.append(f"Notícia de proventos: “{prov[0]['titulo']}”.")
        return o


class Previsor(Agente):
    id, nome, icone, peso = "previsor", "Previsora do próximo mês", "🔮", 0.5
    apelido = "Íris"
    especialidade = "Chance de subir ou cair no próximo mês, pelo comportamento da ação em situações parecidas."

    def avaliar(self, r, ctx):
        o = Opiniao()
        pv = ctx["previsoes"].get(r["ticker"])
        fator = ctx.get("fator_previsor", 0.0)
        if not pv:
            o.argumentos.append("Sem histórico suficiente para prever.")
            return o
        if fator <= 0:
            o.argumentos.append("No teste histórico, as previsões de curto prazo não bateram o chute: "
                                "não estou votando (honestidade acima de tudo).")
            return o
        if pv["direcao"] == "Alta":
            o.add(1, f"{_p(pv['prob_alta'], 0)} de chance de subir no próximo mês (mediana {_p(pv['ret_mediano'])}).")
        elif pv["direcao"] == "Queda":
            o.add(-1, f"Só {_p(pv['prob_alta'], 0)} de chance de subir no próximo mês: pode valer esperar para comprar.")
        else:
            o.argumentos.append(f"Próximo mês indefinido ({_p(pv['prob_alta'], 0)} de chance de alta).")
        return o


class Risco(Agente):
    id, nome, icone, peso = "risco", "Gestor de Risco", "🛡️", 1.0
    apelido = "Rex"
    especialidade = "Protege o patrimônio: veta dado duvidoso e prejuízo, mede oscilação e compara com a renda fixa."

    def avaliar(self, r, ctx):
        o = Opiniao()
        if not _ok(r.get("lpa")) or r["lpa"] <= 0:
            o.add(-2, "VETO: empresa com prejuízo.")
            o.veto = True
        if r.get("confianca") == "Baixa":
            o.add(-2, f"VETO até conferir: dados inconsistentes ({r.get('avisos_dados') or 'ver aba Empresa'}).")
            o.veto = True
        vol = r.get("volatilidade")
        if _ok(vol) and vol > 0.55:
            o.add(-1, f"Oscila demais ({_p(vol, 0)} ao ano).")
        elif _ok(vol) and vol < 0.25:
            o.add(1, f"Ação estável (oscilação de {_p(vol, 0)} ao ano).")
        pf = r.get("payout_fcl")
        if pf == float("inf"):
            o.add(-1, "Paga dividendos com caixa livre negativo: está se financiando para pagar.")
        dd = r.get("queda_max_5a")
        if _ok(dd) and dd < -0.50:
            o.add(-1, f"Já caiu {_p(-dd, 0)} do topo nos últimos 5 anos.")
        rf = ctx["macro"].get("cdi_liquido")
        dy = r.get("dy_previsto") if _ok(r.get("dy_previsto")) else r.get("dy_medio_5a")
        if _ok(rf) and _ok(dy) and dy < rf * 0.5:
            o.argumentos.append(f"Os proventos ({_p(dy)}) rendem bem menos que a renda fixa ({_p(rf)}): o retorno depende da valorização.")
        exp = ctx["exposicao_setor"].get(r["setor"], 0.0)
        if exp > 0.30:
            o.add(-1, f"Você já tem {_p(exp, 0)} da carteira no setor {r['setor']}: concentração.")
        o.voto = int(np.clip(o.voto, -2, 2))
        return o


def _r(x) -> str:
    return "—" if not _ok(x) else f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class Proventos(Agente):
    id, nome, icone, peso = "proventos", "Previsor de Proventos", "💵", 1.2
    apelido = "Otto"
    especialidade = "Quanto a ação vai pagar nos próximos 12 meses e a chance de cortar os proventos — testado no passado."

    def avaliar(self, r, ctx):
        o = Opiniao()
        x = ctx.get("oraculos", {}).get(r["ticker"])
        if not x or not _ok(x.get("otto_prov_12m")):
            o.argumentos.append("Sem histórico de proventos suficiente para prever.")
            return o
        prev, pc, ac, n = x["otto_prov_12m"], x.get("otto_prob_corte"), x.get("otto_acerto"), int(x.get("otto_anos_testados") or 0)
        dy = prev / r["preco"] if _ok(r.get("preco")) and r["preco"] else float("nan")
        faixa = (f" (faixa provável {_r(x.get('otto_prov_p10'))} a {_r(x.get('otto_prov_p90'))})"
                 if _ok(x.get("otto_prov_p10")) and _ok(x.get("otto_prov_p90")) else "")
        o.argumentos.append(f"Prevejo {_r(prev)} por ação nos próximos 12 meses{faixa} — {_p(dy)} sobre o preço de hoje.")
        if n:
            o.argumentos.append(f"No teste dos últimos {n} anos (sem olhar o futuro), meu método errou por menos de 25% em {_p(ac, 0)} das vezes.")
        motivo = f" ({x['otto_motivos_corte']})" if x.get("otto_motivos_corte") else ""
        if _ok(pc) and pc >= 0.40:
            o.add(-2, f"Risco ALTO de cortar os proventos: {_p(pc, 0)} de chance{motivo}.")
        elif _ok(pc) and pc >= 0.28:
            o.add(-1, f"Risco de corte acima do normal: {_p(pc, 0)}{motivo}.")
        elif n >= 3 and _ok(ac) and ac >= 0.6 and _ok(pc) and pc <= 0.15:
            o.add(2, f"Proventos muito previsíveis e risco de corte baixo ({_p(pc, 0)}): ótima para o projeto de renda.")
        elif n >= 3 and _ok(ac) and ac >= 0.5 and _ok(pc) and pc <= 0.25:
            o.add(1, f"Proventos razoavelmente previsíveis; risco de corte {_p(pc, 0)}.")
        else:
            o.argumentos.append(f"Proventos pouco previsíveis (risco de corte {_p(pc, 0)}): não aposto nesta como base da renda.")
        return o


class Entrada(Agente):
    id, nome, icone, peso = "entrada", "Estrategista de Entrada", "🎯", 0.0  # não vota: diz a que preço comprar
    apelido = "Bento"
    especialidade = "A que preço pôr a ordem de compra, pela oscilação real da ação em 1 mês."

    def avaliar(self, r, ctx):
        o = Opiniao()
        x = ctx.get("oraculos", {}).get(r["ticker"])
        if not x or not _ok(x.get("bento_preco_80")):
            o.argumentos.append("Histórico curto para calcular o ponto de entrada.")
            return o
        o.argumentos.append(f"Ordem de compra a {_r(x['bento_preco_80'])}: ~80% de chance de executar no próximo mês; "
                            f"a {_r(x['bento_preco_50'])}: ~50%.")
        pt, teto = x.get("bento_prob_tocar_teto"), r.get("preco_teto_bazin")
        if _ok(teto) and _ok(r.get("preco")):
            if r["preco"] <= teto:
                o.argumentos.append(f"Já está abaixo do preço-teto ({_r(teto)}): dá para comprar sem esperar.")
            elif _ok(pt):
                o.argumentos.append(f"Para chegar ao preço-teto ({_r(teto)}) precisa cair {_p(1 - teto / r['preco'], 0)}; "
                                    f"chance disso em 1 mês: {_p(pt, 0)}.")
        o.argumentos.append("Não voto: meu papel é o preço de entrada, não o que comprar.")
        return o


class Conjunto(Agente):
    id, nome, icone, peso = "conjunto", "Cientista de Dados", "🧮", 0.7
    apelido = "Sofia"
    especialidade = "Modelo que junta vários sinais e estima a chance de render mais que as outras ações em 3 meses."

    def avaliar(self, r, ctx):
        o = Opiniao()
        x = ctx.get("oraculos", {}).get(r["ticker"])
        fator = ctx.get("fator_sofia", 0.0)
        if not x or not _ok(x.get("sofia_prob")):
            o.argumentos.append("Sem dados suficientes para o modelo.")
            return o
        if fator <= 0:
            o.argumentos.append("No teste sem colar, meu modelo não bateu o chute: não estou votando (honestidade acima de tudo).")
            return o
        q = x.get("sofia_quintil")
        o.argumentos.append(f"Chance de render mais que a mediana das ações nos próximos 3 meses: {_p(x['sofia_prob'], 0)}.")
        if _ok(q) and q > 0.8:
            o.add(1, "Está entre as 20% mais bem colocadas do modelo — o grupo que, no teste, rendeu mais que o resto.")
        elif _ok(q) and q <= 0.2:
            o.add(-1, "Está entre as 20% piores do modelo para os próximos 3 meses: pode valer esperar.")
        return o


NOMES_FATOR = {"dolar": "o dólar", "petroleo": "o petróleo", "minerio": "o minério de ferro", "juros_eua": "os juros dos EUA"}


class Macro(Agente):
    id, nome, icone, peso = "macro", "Analista de Política e Macro", "🌎", 0.5
    apelido = "Helena"
    especialidade = "Governo, juros, câmbio, commodities e relações exteriores: quem ganha e quem perde com o cenário."

    def avaliar(self, r, ctx):
        o = Opiniao()
        x = ctx.get("cenario", {}).get(r["ticker"])
        if not x:
            o.argumentos.append("Sem dados suficientes para medir a reação desta ação ao cenário.")
            return o
        sens = []
        for k, nome in NOMES_FATOR.items():
            b, t = x.get(f"beta_{k}"), x.get(f"t_{k}")
            if _ok(b) and _ok(t) and abs(t) >= 2:
                sens.append(f"{'sobe' if b > 0 else 'cai'} quando {nome} sobe (sensibilidade {b:+.2f})".replace(".", ","))
        o.argumentos.append("Reação ao cenário: " + ("; ".join(sens) + "." if sens else "nenhuma dependência clara de dólar, petróleo, minério ou juros dos EUA."))
        v, motor = x.get("vento"), x.get("motor")
        if _ok(v) and v != 0 and motor:
            o.argumentos.append(f"Com o que {NOMES_FATOR.get(motor, motor)} fez nos últimos 3 meses, o vento está "
                                f"{'a favor' if v > 0 else 'contra'} ({_p(v)}).")
        if ctx.get("fator_macro", 0) <= 0:
            o.argumentos.append("No teste sem colar, o vento macro ainda não provou vantagem: informo, mas não voto.")
            return o
        q = x.get("vento_quintil")
        if _ok(q) and q > 0.8 and _ok(v) and v > 0:
            o.add(1, "Entre as 20% com mais vento macro a favor — o grupo que, no teste, rendeu mais que o resto.")
        elif _ok(q) and q <= 0.2 and _ok(v) and v < 0:
            o.add(-1, "Entre as 20% com mais vento macro contra: cenário desfavorável para os próximos meses.")
        return o


AGENTES: list[Agente] = [Renda(), Fundamentos(), Valuation(), Tendencia(), Noticias(), Previsor(), Risco(),
                         Proventos(), Entrada(), Conjunto(), Macro()]
ESTATISTICOS = {"previsor", "proventos", "entrada", "conjunto", "macro"}  # previsões numéricas: a IA não revisa estes
POR_ID = {a.id: a for a in AGENTES}


def classificar(score: float, vetado: bool) -> str:
    if vetado:
        return "Vetado"
    return "Compra forte" if score >= 1.0 else "Compra" if score >= 0.45 else "Neutro" if score > -0.3 else "Evitar"


# ------------------------------------------------------------------ verificação cruzada: um agente confere o outro
def verificacao_cruzada(rk: pd.DataFrame, opinioes: dict, ctx: dict) -> list[dict]:
    """Cada agente revisa o trabalho de um colega e contesta quando os dados não sustentam o voto.

    Devolve a lista de achados {verificador, verificado, ticker, achado, efeito}; os votos contestados são corrigidos."""
    achados = []

    def contestar(verificador, verificado, t, achado, novo_voto=None, veto=False):
        op = opinioes[t][verificado]
        antes = op["voto"]
        if novo_voto is not None:
            op["voto"] = int(np.clip(novo_voto, -2, 2))
        if veto:
            op["veto"] = True
        v, d = POR_ID[verificador], POR_ID[verificado]
        op["argumentos"].append(f"🔍 Contestado por {v.apelido}: {achado}")
        efeito = ("voto vetado" if veto else f"voto {antes:+d} → {op['voto']:+d}") if (veto or op["voto"] != antes) else "anotado"
        achados.append({"verificador": f"{v.icone} {v.apelido}", "verificado": f"{d.icone} {d.apelido}", "ticker": t,
                        "achado": achado, "efeito": efeito})

    for _, r in rk.iterrows():
        t, ops = r["ticker"], opinioes[r["ticker"]]
        # Fausto (fundamentos) confere Dora (dividendos): o lucro sustenta os proventos?
        if ops["renda"]["voto"] > 0:
            pay, cl = r.get("payout"), r.get("cresc_lucro")
            if _ok(pay) and pay > 0.95:
                contestar("fundamentos", "renda", t, f"os proventos consomem {_p(pay, 0)} do lucro: pouca margem para manter.",
                          ops["renda"]["voto"] - 1)
            elif _ok(cl) and cl <= -0.25:
                contestar("fundamentos", "renda", t, f"o lucro caiu {_p(-cl)}; os proventos tendem a cair junto.",
                          ops["renda"]["voto"] - 1)
            elif _ok(r.get("payout_fcl")) and r["payout_fcl"] > 1.2:
                txt = ("o caixa livre é negativo" if r["payout_fcl"] == float("inf")
                       else f"os dividendos consomem {_p(r['payout_fcl'], 0)} do caixa livre")
                contestar("fundamentos", "renda", t, f"{txt}: pagamento financiado, não sustentável.", ops["renda"]["voto"] - 1)
        # Otto (previsor de proventos) confere Dora: o risco de corte desmente o otimismo com a renda?
        ox = ctx.get("oraculos", {}).get(t) or {}
        if ops["renda"]["voto"] > 0 and _ok(ox.get("otto_prob_corte")) and ox["otto_prob_corte"] >= 0.30:
            contestar("proventos", "renda", t, f"a chance de corte dos proventos está em {_p(ox['otto_prob_corte'], 0)}; "
                      "o histórico bom pode não se repetir.", ops["renda"]["voto"] - 1)
        # Dora (dividendos) confere Vitória (valuation): o preço-teto está inflado?
        if ops["valuation"]["voto"] > 0:
            dy12, dy5, g = r.get("dy_12m"), r.get("dy_medio_5a"), r.get("cresc_proventos_5a")
            if _ok(dy12) and _ok(dy5) and dy5 > 0 and dy12 > 2 * dy5:
                contestar("renda", "valuation", t, "o preço-teto usa uma média puxada por provento extraordinário recente.",
                          ops["valuation"]["voto"] - 1)
            elif _ok(g) and g <= -0.10:
                contestar("renda", "valuation", t, f"os proventos estão encolhendo {_p(-g)} ao ano: o teto pela média passada está otimista.",
                          ops["valuation"]["voto"] - 1)
        # Téo (tendência) confere Vitória: barata porque ainda está caindo?
        p = ctx["precos"].get(t)
        if ops["valuation"]["voto"] >= 2 and p is not None and len(p) > 70:
            r3 = float(p.iloc[-1]) / float(p.iloc[-63]) - 1
            if r3 <= -0.20:
                contestar("tendencia", "valuation", t, f"ficou barata caindo {_p(-r3)} em 3 meses; pode ser problema, não pechincha.", 1)
        # Vitória confere Téo: o 'desconto temporário' é mesmo desconto?
        if ops["tendencia"]["voto"] > 0 and ops["valuation"]["voto"] < 0:
            contestar("valuation", "tendencia", t, "abaixo da média de 200 dias, mas ainda cara pelo preço-teto: não é desconto.", 0)
        # Nina (notícias) confere Fausto: notícia grave contra fundamentos bons?
        if ops["fundamentos"]["voto"] > 0 and ops["noticias"]["voto"] <= -2:
            contestar("noticias", "fundamentos", t, "há notícia grave recente que pode mudar os números do balanço.",
                      ops["fundamentos"]["voto"] - 1)
        # Rex (risco) confere a base de todos: cotação recente?
        dc = r.get("data_cotacao")
        if dc and ctx.get("data"):
            atraso = len(pd.bdate_range(pd.Timestamp(dc), pd.Timestamp(ctx["data"]))) - 1
            if atraso > 4:
                contestar("risco", "valuation", t, f"a cotação usada tem {atraso} pregões de atraso; não dá para confiar no preço.", 0, veto=True)
    return achados


# ------------------------------------------------------------------ IA: cada especialista como agente Claude
ESQUEMA_VOTOS = {
    "type": "object", "additionalProperties": False, "required": ["avaliacoes"],
    "properties": {"avaliacoes": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["ticker", "voto", "argumento"],
        "properties": {"ticker": {"type": "string"}, "voto": {"type": "integer", "enum": [-2, -1, 0, 1, 2]},
                       "argumento": {"type": "string"}}}}},
}


def _revisao_ia(agente: Agente, cand: pd.DataFrame, opinioes: dict, ctx: dict, pesquisa: str | None) -> dict[str, tuple[int, str]]:
    dados = []
    for _, r in cand.iterrows():
        dados.append({"ticker": r["ticker"], "empresa": r["nome"], "setor": r["setor"],
                      **{k: (None if not _ok(r.get(k)) else (round(float(r[k]), 4) if isinstance(r[k], (int, float, np.floating)) else r[k]))
                         for k in ("preco", "preco_teto_bazin", "margem_bazin", "dy_medio_5a", "dy_12m", "anos_pagou_10",
                                   "cresc_proventos_5a", "payout", "roe", "margem_liquida", "divida_pl", "pl", "pvp",
                                   "volatilidade", "queda_max_5a", "confianca", "f_score_9", "payout_fcl",
                                   "seguranca_div", "preco_justo_ddm", "grau_Valor", "grau_Renda", "grau_Qualidade",
                                   "grau_Saúde", "grau_Momento")},
                      "parecer_das_regras": opinioes[r["ticker"]][agente.id]})
    sistema = (f"Você é {agente.apelido}, o(a) {agente.nome} de uma mesa de análise de ações brasileiras para investidor de longo prazo focado em "
               f"renda (dividendos/JCP) e aportes mensais. Sua especialidade: {agente.especialidade} "
               "Avalie APENAS pela sua especialidade, com base nos dados fornecidos (data da apuração: "
               f"{ctx['data']}) e, se houver, na pesquisa de notícias. Não invente números. Voto de -2 a +2; "
               "argumento em português simples, uma ou duas frases, citando o número ou a fonte que justifica."
               + (f" Seu histórico real: {ctx['memoria'][agente.id]}" if ctx.get("memoria", {}).get(agente.id) else ""))
    msg = "Ações candidatas (com o parecer automático das regras):\n" + json.dumps(dados, ensure_ascii=False, default=str)
    if pesquisa:
        msg += "\n\nPESQUISA DE NOTÍCIAS NA WEB (feita hoje):\n" + pesquisa
    res = ia.chamar_json(sistema, [{"role": "user", "content": msg}], ESQUEMA_VOTOS)
    if not res:
        return {}
    saida = {}
    for a in res.get("avaliacoes", []):
        t = str(a.get("ticker", "")).upper()
        if t in set(cand["ticker"]) and a.get("voto") in (-2, -1, 0, 1, 2):
            saida[t] = (int(a["voto"]), str(a.get("argumento", ""))[:400])
    return saida


def _pesquisar_noticias(cand: pd.DataFrame) -> str | None:
    lista = ", ".join(f"{r['ticker']} ({r['nome']})" for _, r in cand.iterrows())
    sistema = "Você é um pesquisador de notícias do mercado de ações brasileiro. Responda em português, citando as fontes."
    pedido = (f"Pesquise notícias dos últimos 14 dias sobre: {lista}. Para cada ação, em 1–2 linhas: o fato mais relevante "
              "para quem investe a longo prazo buscando dividendos (resultados, proventos anunciados ou cortados, dívida, "
              "fatos relevantes, governança, investigações). Diga 'nada relevante' quando for o caso. Inclua a fonte.")
    return ia.chamar(sistema, [{"role": "user", "content": pedido}], [ia.pesquisa_web(8)])


# ------------------------------------------------------------------ a reunião
def reuniao(rk: pd.DataFrame, precos: dict, noticias: dict, macro: dict, previsoes: pd.DataFrame | None = None,
            fator_previsor: float = 0.0, carteira: pd.DataFrame | None = None, data: str = "",
            usar_ia: bool = True, n_ia: int = 8, progresso=None, aprendizado: dict | None = None,
            cerebro: dict | None = None, oraculos: pd.DataFrame | None = None, fator_sofia: float = 0.0,
            cenario: pd.DataFrame | None = None, fator_macro: float = 0.0) -> dict:
    """Roda todos os agentes em todas as ações. Retorna {'consenso': DataFrame, 'opinioes': {...}, 'log': [...], 'ia': bool}."""
    exposicao = {}
    if carteira is not None and len(carteira):
        precos_rk = dict(zip(rk["ticker"], rk["preco"]))
        setor_rk = dict(zip(rk["ticker"], rk["setor"]))
        val = {t: q * (precos_rk.get(t) or 0) for t, q in zip(carteira["ticker"], carteira["quantidade"])}
        tot = sum(val.values()) or 1.0
        for t, v in val.items():
            exposicao[setor_rk.get(t, "Outros")] = exposicao.get(setor_rk.get(t, "Outros"), 0) + v / tot
    prev_map = {r["ticker"]: r.to_dict() for _, r in previsoes.iterrows()} if previsoes is not None and len(previsoes) else {}
    orac = {}
    if oraculos is not None and len(oraculos):
        oc = oraculos.copy()
        if "sofia_prob_bruta" in oc:
            oc["sofia_quintil"] = oc["sofia_prob_bruta"].rank(pct=True)
        orac = {r_["ticker"]: r_.to_dict() for _, r_ in oc.iterrows()}
    ctx = {"precos": precos, "noticias": noticias or {}, "macro": macro or {}, "previsoes": prev_map,
           "fator_previsor": fator_previsor, "exposicao_setor": exposicao, "data": data, "memoria": {},
           "oraculos": orac, "fator_sofia": fator_sofia, "fator_macro": fator_macro,
           "cenario": ({r_["ticker"]: r_.to_dict() for _, r_ in cenario.iterrows()} if cenario is not None and len(cenario) else {})}
    pa = (cerebro or {}).get("por_agente")
    if pa is not None and len(pa):
        for _, m in pa.iterrows():
            ctx["memoria"][m["agente"]] = (f"dos seus {int(m['conferidos'])} votos já conferidos, {_p(m['acerto'])} acertaram a direção "
                                           "em relação à média do mercado. Aprenda com isso: seja mais cauteloso se o acerto for baixo.")

    falar = progresso or (lambda _m: None)
    aprendizado = aprendizado or {}
    opinioes: dict[str, dict[str, dict]] = {t: {} for t in rk["ticker"]}
    log = []
    for ag in AGENTES:
        falar(f"{ag.icone} **{ag.apelido}** ({ag.nome}) está analisando {len(rk)} empresas...")
        escritorio.status(ag.id, "trabalhando", f"analisando {len(rk)} empresas")
        t0 = time.perf_counter()
        pos = neg = vetos = 0
        for _, r in rk.iterrows():
            try:
                o = ag.avaliar(r, ctx)
            except Exception as e:  # noqa: BLE001
                o = Opiniao(0, [f"Não consegui analisar ({e})."])
            opinioes[r["ticker"]][ag.id] = {"voto": int(np.clip(o.voto, -2, 2)), "argumentos": o.argumentos, "veto": o.veto}
            pos += o.voto > 0
            neg += o.voto < 0
            vetos += o.veto
        log.append(f"{ag.icone} {ag.apelido} ({ag.nome}): analisou {len(rk)} empresas em {time.perf_counter() - t0:.2f}s — "
                   f"{pos} a favor, {neg} contra" + (f", {vetos} veto(s)" if vetos else "") + ".")
        falar("   ✓ " + log[-1])
        escritorio.registrar(ag.id, log[-1].split(": ", 1)[-1])
        escritorio.status(ag.id, "pausa", "análise do dia entregue")

    usou_ia = False
    if usar_ia and ia.disponivel():
        pre = _consenso(rk, opinioes)
        cand = rk.set_index("ticker").loc[pre.sort_values("placar", ascending=False).head(n_ia)["ticker"]].reset_index()
        print(f"  🪙 Mesa com IA: revisando as {len(cand)} melhores candidatas (cada especialista é um agente Claude)...")
        falar(f"📰 **Nina** está pesquisando notícias na internet sobre {len(cand)} candidatas...")
        escritorio.status("noticias", "trabalhando", "pesquisando notícias na internet")
        pesquisa = _pesquisar_noticias(cand)
        if pesquisa:
            log.append("📰 Nina (IA): pesquisou a internet sobre as candidatas.")
            falar("   ✓ " + log[-1])
            escritorio.registrar("noticias", f"pesquisou na internet notícias de {len(cand)} candidatas")
        for ag in AGENTES:
            if ag.id in ESTATISTICOS:
                continue  # previsão é estatística e testada no passado; a IA não acrescenta aqui
            falar(f"{ag.icone} **{ag.apelido}** (IA) está revisando as {len(cand)} melhores candidatas...")
            escritorio.status(ag.id, "trabalhando", f"revisando com IA as {len(cand)} melhores candidatas")
            votos = _revisao_ia(ag, cand, opinioes, ctx, pesquisa if ag.id in ("noticias", "risco") else None)
            for t, (v, arg) in votos.items():
                op = opinioes[t][ag.id]
                op["voto_regras"] = op["voto"]
                # meio-termo entre regras e IA; empate arredonda na direção da IA
                op["voto"] = int(op["voto"] + np.sign(v - op["voto"]) * int(np.ceil(abs(v - op["voto"]) / 2)))
                op["argumentos"].append(f"🪙 IA: {arg}")
            if votos:
                usou_ia = True
                log.append(f"{ag.icone} {ag.apelido} (IA): revisou {len(votos)} candidatas.")
                falar("   ✓ " + log[-1])
                escritorio.registrar(ag.id, f"revisou com IA as {len(votos)} melhores candidatas")
            escritorio.status(ag.id, "pausa", "revisão com IA entregue")

    falar("🔍 **Verificação cruzada**: cada agente está conferindo o trabalho de um colega...")
    escritorio.status([a.id for a in AGENTES], "trabalhando", "conferindo o trabalho de um colega")
    achados = verificacao_cruzada(rk, opinioes, ctx)
    for quem in sorted({v["verificador"] for v in achados}):
        n_ = sum(1 for v in achados if v["verificador"] == quem)
        alvo = next(a.id for a in AGENTES if quem.endswith(a.apelido))
        escritorio.registrar(alvo, f"conferiu o trabalho de colegas e fez {n_} contestação(ões)")
    escritorio.status([a.id for a in AGENTES], "pausa", "reunião do dia encerrada")
    log.append(f"🔍 Verificação cruzada: {len(achados)} contestação(ões) entre os agentes "
               f"({sum(1 for a in achados if a['efeito'] != 'anotado')} votos corrigidos).")
    falar("   ✓ " + log[-1])
    cons = _consenso(rk, opinioes, aprendizado)
    if aprendizado:
        falar("🧠 Pesos ajustados pelo placar real: " + ", ".join(f"{POR_ID[a].apelido} ×{f:.2f}".replace(".", ",")
                                                               for a, f in aprendizado.items() if a in POR_ID))
    falar(f"🪙 **AURUM** consolidou os votos: {resumo_texto({'consenso': cons})}.")
    return {"consenso": cons, "opinioes": opinioes, "log": log, "ia": usou_ia, "fator_previsor": fator_previsor,
            "verificacoes": achados, "aprendizado": aprendizado,
            "hora": time.strftime("%Y-%m-%dT%H:%M")}


def _consenso(rk: pd.DataFrame, opinioes: dict, aprendizado: dict | None = None) -> pd.DataFrame:
    aprendizado = aprendizado or {}
    peso = {a.id: a.peso * aprendizado.get(a.id, 1.0) for a in AGENTES}
    linhas = []
    soma_pesos = sum(peso.values())
    for t in rk["ticker"]:
        ops = opinioes[t]
        placar = sum(ops[a.id]["voto"] * peso[a.id] for a in AGENTES if a.id in ops) / soma_pesos
        vetado = any(o.get("veto") for o in ops.values())
        a_favor = sum(1 for o in ops.values() if o["voto"] > 0)
        contra = sum(1 for o in ops.values() if o["voto"] < 0)
        linhas.append({"ticker": t, "placar": round(placar, 2), "consenso": classificar(placar, vetado),
                       "a_favor": a_favor, "contra": contra, "vetado": vetado,
                       "vetado_por": ", ".join(POR_ID[a].apelido for a, o in ops.items() if o.get("veto"))})
    return pd.DataFrame(linhas)



def votos_icones(ops: dict) -> str:
    m = {2: "🟢🟢", 1: "🟢", 0: "⚪", -1: "🔴", -2: "🔴🔴"}
    return " ".join(f"{POR_ID[a].icone}{'⛔' if o.get('veto') else m[o['voto']]}" for a, o in ops.items())


def resumo_texto(mesa: dict, n: int = 3) -> str:
    c = mesa["consenso"]
    fortes = c[c["consenso"] == "Compra forte"].sort_values("placar", ascending=False)["ticker"].head(n).tolist()
    compra = c[c["consenso"] == "Compra"].sort_values("placar", ascending=False)["ticker"].head(n).tolist()
    vet = c[c["vetado"]]["ticker"].head(5).tolist()
    partes = []
    if fortes:
        partes.append("compra forte em " + ", ".join(fortes))
    if compra:
        partes.append("compra em " + ", ".join(compra))
    if vet:
        partes.append("vetadas: " + ", ".join(vet))
    return "; ".join(partes) or "sem consenso de compra hoje"
