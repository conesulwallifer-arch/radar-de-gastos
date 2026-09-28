"""Detectores de indícios de irregularidade.

Inspirados na robô Rosie (Operação Serenata de Amor) e nos cruzamentos de bases
feitos por fiscalizadores independentes. Cada alerta é um INDÍCIO para verificação,
nunca uma prova. Todo alerta aponta para o gasto (ou político) que o originou.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .util import doc_valido, normaliza_doc

PESO = {1: 1, 2: 3, 3: 8}


def brl(v) -> str:
    return ("R$ {:,.2f}".format(float(v))).replace(",", "X").replace(".", ",").replace("X", ".")

COLS = ["gasto_id", "politico_id", "codigo", "gravidade", "titulo", "detalhe", "valor", "gastos_ids"]

CATALOGO = {
    "DOC_INVALIDO": (1, "CPF/CNPJ do fornecedor inválido", "Dígito verificador não confere — nota pode ser fria ou digitada errada."),
    "NOTA_DUPLICADA": (3, "Nota reembolsada mais de uma vez", "Mesmo fornecedor, mesmo número de documento e mesmo valor aparecem repetidos."),
    "NOTA_MENSAL": (1, "Mesmo nº de nota repetido todo mês", "O mesmo número de documento aparece em vários meses. Pode ser contrato/recibo recorrente (aluguel, locação) ou nota reaproveitada: confira as notas."),
    "FRACIONAMENTO": (2, "Várias notas no mesmo dia e fornecedor", "3+ notas do mesmo fornecedor na mesma data — possível fracionamento para driblar limites."),
    "VALOR_ATIPICO": (2, "Valor muito acima do padrão da categoria", "Valor está muito fora da distribuição de todos os gastos da mesma categoria."),
    "REFEICAO_CARA": (2, "Refeição acima do padrão do restaurante", "Valor acima de média + 3 desvios do que o próprio estabelecimento costuma cobrar (regra da Rosie)."),
    "FORNECEDOR_EXCLUSIVO": (2, "Fornecedor praticamente exclusivo", "Fornecedor recebeu valor relevante e quase tudo veio de um único político."),
    "EMPRESA_SANCIONADA": (3, "Pagamento a empresa sancionada (CEIS/CNEP)", "Empresa estava no cadastro de inidôneas/punidas da CGU na data do gasto."),
    "FORNECEDOR_DOADOR": (3, "Fornecedor doou para a campanha do político", "O mesmo CPF/CNPJ aparece como doador de campanha e como recebedor de dinheiro público do político."),
    "SOCIO_DOADOR": (3, "Sócio do fornecedor doou para a campanha", "Uma pessoa com o mesmo nome de um sócio da empresa fornecedora doou para a campanha do político que a contratou com dinheiro público."),
    "DOADOR_CONTRATADO": (3, "Doador de campanha contratado pela prefeitura/câmara", "Quem doou para a campanha de um eleito do município (ou sócio da empresa, pelo nome) depois recebeu contrato ou pagamento do órgão municipal."),
    "FORNECEDOR_CANDIDATO": (2, "Fornecedor é (ou foi) candidato", "Pagamento a pessoa que disputou eleição — verificar vínculo político."),
    "AUTO_PAGAMENTO": (3, "Político pagando a si mesmo", "CPF do fornecedor é o do próprio político."),
    "EMPRESA_RECEM_ABERTA": (2, "Empresa aberta pouco antes do pagamento", "CNPJ tinha menos de 6 meses de existência no primeiro pagamento."),
    "EMPRESA_INATIVA": (3, "Empresa baixada/inapta na data do gasto", "Situação cadastral na Receita indica que a empresa não funcionava quando emitiu a nota."),
    "SOCIO_E_POLITICO": (3, "Sócio do fornecedor tem o nome do político", "Nome de sócio da empresa idêntico ao do político pagador."),
    "SOCIO_CANDIDATO": (2, "Sócio do fornecedor foi candidato", "Sócio da empresa (nome + dígitos do CPF) consta como candidato no TSE."),
    "BENFORD": (1, "Valores fogem da Lei de Benford", "Distribuição do 1º dígito dos valores destoa do padrão natural — comum em números inventados."),
    "VALORES_REDONDOS": (1, "Excesso de valores redondos", "Proporção alta de notas com valores cheios (múltiplos de R$ 100)."),
    "PATRIMONIO_SALTO": (2, "Patrimônio declarado cresceu muito", "Bens declarados ao TSE cresceram mais de 3x entre eleições (e + R$ 500 mil)."),
}


def _alerta(df: pd.DataFrame, codigo: str, detalhe: pd.Series | str = "") -> pd.DataFrame:
    grav, titulo, _ = CATALOGO[codigo]
    return pd.DataFrame({
        "gasto_id": df.get("id", pd.Series([None] * len(df), index=df.index)),
        "politico_id": df["politico_id"],
        "codigo": codigo,
        "gravidade": grav,
        "titulo": titulo,
        "detalhe": detalhe if isinstance(detalhe, pd.Series) else detalhe,
        "valor": df["valor"],
        "gastos_ids": df["gastos_ids"] if "gastos_ids" in df else df.get("id", pd.Series([None] * len(df), index=df.index)),
    })[COLS]


PARLAMENTAR = ("CEAP Câmara", "CEAPS Senado")
# categorias em que várias notas iguais/no mesmo dia são normais (bilhetes, faturas, correios)
ROTINA = (r"PASSAGE|SIGEPA|TELEFON|POSTA|CORREIO|ASSINATURA|PUBLICA..O|BILHETE|A.REO|T.XI|PED.GIO|ESTACIONA"
          r"|HOSPEDAGEM|LOCOMO|ALUGUEL|IM.VE|CONDOM|ENERGIA|.GUA")


def _agrupar(x: pd.DataFrame, chaves: list[str], codigo: str, detalhe) -> pd.DataFrame:
    """Um alerta por grupo (não um por nota): aponta para a 1ª nota e soma o valor."""
    if x.empty:
        return pd.DataFrame(columns=COLS)
    gr = x.sort_values("data").groupby(chaves, as_index=False, dropna=False).agg(
        id=("id", "first"), gastos_ids=("id", lambda v: ",".join(map(str, v))),
        politico_id=("politico_id", "first"), valor=("valor", "sum"),
        n=("id", "size"), meses=("data", lambda d: d.dt.to_period("M").nunique()), data=("data", "first"), fornecedor=("fornecedor", "first"),
        fornecedor_doc=("fornecedor_doc", "first"), documento=("documento", "first"))
    return _alerta(gr, codigo, detalhe(gr))


def doc_invalido(g):
    x = g[g["fonte"].isin(PARLAMENTAR)]
    v = x["fornecedor_doc"].map(doc_valido)
    x = x[v == False]  # noqa: E712
    return _agrupar(x, ["politico_id", "fornecedor_doc"], "DOC_INVALIDO",
                    lambda r: "Documento " + r["fornecedor_doc"] + " (" + r["fornecedor"].fillna("") + ") em " + r["n"].astype(str) + " nota(s)")


def nota_duplicada(g):
    doc = g["documento"].fillna("").str.replace(r"\D", "", regex=True).str.lstrip("0")
    x = g.assign(doc_n=doc)
    x = x[x["fonte"].isin(PARLAMENTAR) & (x["doc_n"].str.len() >= 3) & (x["valor"] > 0)
          & ~x["categoria"].str.contains(ROTINA, na=False) & (x["fornecedor_doc"] != "")]
    k = ["politico_id", "fornecedor_doc", "doc_n", "valor"]
    x = x[x.duplicated(k, keep=False)]
    # mesma nota lançada em datas diferentes = reembolso em dobro; mesma data costuma ser parcela/ajuste
    x = x[x.groupby(k)["data"].transform("nunique") > 1]
    if x.empty:
        return pd.DataFrame(columns=COLS)
    # um lançamento por mês, 3+ meses = cobrança recorrente com o mesmo nº (aluguel, locação): gravidade baixa
    mes = x["data"].dt.to_period("M")
    n = x.groupby(k)["id"].transform("size")
    nm = mes.groupby([x[c] for c in k]).transform("nunique")
    ordm = mes.map(lambda m: m.ordinal)
    grp_m = ordm.groupby([x[c] for c in k])
    vao = grp_m.transform("max") - grp_m.transform("min") + 1
    # recorrente = um por mês, em meses praticamente seguidos (ex.: aluguel de jan a dez)
    recorrente = (n >= 3) & (nm == n) & (vao <= n * 1.5)
    det = lambda r: ("Nota nº " + r["documento"].astype(str) + " de " + r["fornecedor"].fillna("")
                     + " lançada " + r["n"].astype(str) + " vezes em " + r["meses"].astype(str) + " mês(es)")
    return pd.concat([_agrupar(x[~recorrente], k, "NOTA_DUPLICADA", det),
                      _agrupar(x[recorrente], k, "NOTA_MENSAL", det)], ignore_index=True)


def fracionamento(g, minimo=4):
    x = g[g["fonte"].isin(PARLAMENTAR) & g["data"].notna() & (g["fornecedor_doc"] != "")
          & ~g["categoria"].str.contains(ROTINA, na=False)]
    k = ["politico_id", "fornecedor_doc", "data"]
    n = x.groupby(k)["id"].transform("count")
    x = x[n >= minimo]
    return _agrupar(x, k, "FRACIONAMENTO",
                    lambda r: r["n"].astype(str) + " notas de " + r["fornecedor"].fillna("") + " em " + r["data"].dt.strftime("%d/%m/%Y"))


def valor_atipico(g, z_min=8.0, piso=5000):
    """Z-score robusto (mediana/MAD em log) dentro de cada fonte+categoria."""
    x = g[g["valor"] > 0].copy()
    x["lv"] = np.log(x["valor"])
    grp = x.groupby(["fonte", "categoria"])["lv"]
    med = grp.transform("median")
    mad = grp.transform(lambda s: (s - s.median()).abs().median()).replace(0, np.nan)
    n = grp.transform("count")
    x["z"] = 0.6745 * (x["lv"] - med) / mad
    x = x[(x["z"] > z_min) & (n >= 30) & (x["valor"] >= piso)]
    return _alerta(x, "VALOR_ATIPICO", "Mediana da categoria: " + np.exp(med[x.index]).map(brl).astype(str))


def refeicao_cara(g):
    x = g[g["categoria"].str.contains("ALIMENTA|REFEI", na=False) & (g["valor"] > 0)
          & ~g["fornecedor"].str.contains(r"HOTE(?:L|IS)", case=False, na=False)]
    grp = x.groupby("fornecedor_doc")["valor"]
    media, desv, n = grp.transform("mean"), grp.transform("std"), grp.transform("count")
    lim = media + 3 * desv
    y = x[(n >= 10) & (x["valor"] > lim) & (x["valor"] > 150)]
    return _alerta(y, "REFEICAO_CARA", "Padrão do local até " + lim[y.index].map(brl).astype(str))


def fornecedor_exclusivo(g, min_total=100_000, fatia=0.9):
    # aluguel do escritório, telefone etc. são exclusivos por natureza: ficam de fora
    x = g[(g["fornecedor_doc"].str.len() == 14) & (g["valor"] > 0) & g["fonte"].str.startswith("CEAP")
          & ~g["categoria"].str.contains(ROTINA, na=False)]
    tot_f = x.groupby("fornecedor_doc")["valor"].sum()
    par = x.groupby(["fornecedor_doc", "politico_id"], as_index=False).agg(valor=("valor", "sum"), fornecedor=("fornecedor", "first"))
    par["tot"] = par["fornecedor_doc"].map(tot_f)
    par = par[(par["valor"] >= min_total) & (par["valor"] / par["tot"] >= fatia)]
    par["id"] = None
    return _alerta(par, "FORNECEDOR_EXCLUSIVO",
                   par["fornecedor"] + " — " + (100 * par["valor"] / par["tot"]).round(0).astype(int).astype(str) + "% do que recebeu veio deste político")


def empresa_sancionada(g, sanc):
    if sanc is None or sanc.empty:
        return pd.DataFrame(columns=COLS)
    m = g[g["data"].notna()].merge(sanc, left_on="fornecedor_doc", right_on="doc", how="inner")
    fim = m["fim"].fillna(pd.Timestamp("2100-01-01"))
    m = m[(m["data"] >= m["inicio"]) & (m["data"] <= fim)].drop_duplicates("id")
    return _alerta(m, "EMPRESA_SANCIONADA", m["cadastro"] + ": " + m["tipo"].fillna("") + " — " + m["orgao"].fillna(""))


def fornecedor_doador(g, receitas):
    if receitas is None or receitas.empty or "politico_id" not in receitas:
        return pd.DataFrame(columns=COLS)
    doa = receitas[receitas["doador_doc"].str.len().isin([11, 14])]
    doa = doa.groupby(["politico_id", "doador_doc"], as_index=False)["valor"].sum().rename(columns={"valor": "doado"})
    # vale para cota parlamentar e para a própria campanha (quem doa e depois recebe como fornecedor)
    m = g.merge(doa, left_on=["politico_id", "fornecedor_doc"], right_on=["politico_id", "doador_doc"])
    return _agrupar(m.assign(doado=m["doado"]), ["politico_id", "fornecedor_doc"], "FORNECEDOR_DOADOR",
                    lambda r: r["fornecedor"].fillna("") + " doou na campanha e recebeu em " + r["n"].astype(str) + " nota(s)")


def socio_doador(g, receitas, emp):
    """Empresa paga pelo político tem sócio com o mesmo nome de um doador da campanha dele.
    (Desde 2015 empresas não podem doar; a doação passa a vir das pessoas por trás delas.)"""
    if receitas is None or receitas.empty or emp is None or emp.empty or "politico_id" not in receitas:
        return pd.DataFrame(columns=COLS)
    norm = lambda t: " ".join(str(t or "").upper().split())
    doadores = receitas.assign(nome_n=receitas["doador"].map(norm)).groupby(["politico_id", "nome_n"])["valor"].sum()
    doadores = doadores[doadores.index.get_level_values(1).str.len() > 8]
    if doadores.empty:
        return pd.DataFrame(columns=COLS)
    por_pol = {}
    for (pid, nome), v in doadores.items():
        por_pol.setdefault(pid, {})[nome] = v
    socios = {r.cnpj: [norm(n) for n in str(r.socios).split(";") if n.strip()] for r in emp.itertuples() if str(r.socios or "").strip()}
    x = g[g["fornecedor_doc"].isin(socios.keys()) & g["politico_id"].isin(por_pol.keys())]
    if x.empty:
        return pd.DataFrame(columns=COLS)
    alvo = []
    for (pid, cnpj), _ in x.groupby(["politico_id", "fornecedor_doc"]):
        hit = [n for n in socios[cnpj] if n in por_pol[pid]]
        if hit:
            alvo.append((pid, cnpj, "; ".join(f"{n} doou {brl(por_pol[pid][n])}" for n in hit)))
    if not alvo:
        return pd.DataFrame(columns=COLS)
    info = pd.DataFrame(alvo, columns=["politico_id", "fornecedor_doc", "quem"])
    x = x.merge(info, on=["politico_id", "fornecedor_doc"])
    return _agrupar(x, ["politico_id", "fornecedor_doc", "quem"], "SOCIO_DOADOR",
                    lambda r: r["fornecedor"].fillna("") + " — sócio " + r["quem"] + " — " + r["n"].astype(str) + " nota(s)")


def doador_contratado(g, receitas, cands, emp):
    """Contrato/pagamento de órgão municipal a quem doou (ou cujo sócio doou) para eleitos do mesmo município."""
    if receitas is None or receitas.empty or cands is None or cands.empty or "pessoa" not in cands:
        return pd.DataFrame(columns=COLS)
    norm = lambda t: " ".join(str(t or "").upper().split())
    org = g[g["cargo"].eq("Órgão municipal") & (g["valor"] > 0)]
    if org.empty:
        return pd.DataFrame(columns=COLS)
    el = cands[cands["eleito"]].drop_duplicates("sq").set_index("sq")
    r = receitas[receitas["sq"].isin(el.index)].copy()
    r["municipio"] = el["municipio"].reindex(r["sq"]).str.upper().values
    r["quem"] = (el["nome"].reindex(r["sq"]) + " (" + el["cargo"].reindex(r["sq"]) + ")").values
    r["pid"] = ("P-" + el["pessoa"].reindex(r["sq"])).values
    r["nome_n"] = r["doador"].map(norm)
    saida = []
    # 1) o próprio fornecedor (CPF/CNPJ) doou
    d1 = r[r["doador_doc"].str.len().isin([11, 14])].groupby(["municipio", "doador_doc", "quem", "pid"], as_index=False)["valor"].sum()
    m1 = org.merge(d1.rename(columns={"valor": "doado"}), left_on=["municipio", "fornecedor_doc"], right_on=["municipio", "doador_doc"])
    if not m1.empty:
        m1["det"] = m1["fornecedor"] + " doou " + m1["doado"].map(brl).astype(str) + " para " + m1["quem"]
        saida.append(m1)
    # 2) sócio da empresa fornecedora (mesmo nome) doou
    if emp is not None and not emp.empty:
        socios = [(c, norm(n)) for c, ss in zip(emp["cnpj"], emp["socios"].fillna("")) for n in ss.split(";") if len(norm(n)) > 8]
        if socios:
            sdf = pd.DataFrame(socios, columns=["fornecedor_doc", "nome_n"])
            d2 = r.groupby(["municipio", "nome_n", "quem", "pid"], as_index=False)["valor"].sum()
            m2 = org.merge(sdf, on="fornecedor_doc").merge(d2.rename(columns={"valor": "doado"}), on=["municipio", "nome_n"])
            if not m2.empty:
                m2["det"] = m2["fornecedor"] + " — sócio " + m2["nome_n"] + " doou " + m2["doado"].map(brl).astype(str) + " para " + m2["quem"]
                saida.append(m2)
    if not saida:
        return pd.DataFrame(columns=COLS)
    x = pd.concat(saida, ignore_index=True).drop_duplicates(["id", "det"])
    a_org = _agrupar(x, ["politico_id", "fornecedor_doc", "det"], "DOADOR_CONTRATADO",
                     lambda r: r["det"] + " · " + r["n"].astype(str) + " contrato(s)/pagamento(s)")
    # o mesmo alerta aparece também na página do eleito que recebeu a doação
    x2 = x.assign(politico_id=x["pid"])
    a_pol = _agrupar(x2, ["politico_id", "fornecedor_doc", "det"], "DOADOR_CONTRATADO",
                     lambda r: r["det"] + " · depois contratado pelo município em " + r["n"].astype(str) + " contrato(s)/pagamento(s)")
    return pd.concat([a_org, a_pol], ignore_index=True)


def fornecedor_candidato(g, cands):
    if cands is None or cands.empty:
        return pd.DataFrame(columns=COLS)
    auto = g[(g["politico_cpf"] != "") & (g["fornecedor_doc"] == g["politico_cpf"])]
    a1 = _alerta(auto, "AUTO_PAGAMENTO", "Fornecedor: " + auto["fornecedor"].fillna(""))
    c = cands[cands["cpf"].str.len() == 11].sort_values("ano").drop_duplicates("cpf", keep="last")
    m = g[(g["fornecedor_doc"].str.len() == 11) & (g["fornecedor_doc"] != g["politico_cpf"])].merge(
        c[["cpf", "cargo", "ano", "municipio", "partido"]].rename(columns={"partido": "p_forn", "cargo": "c_forn", "ano": "a_forn", "municipio": "m_forn"}),
        left_on="fornecedor_doc", right_on="cpf")
    a2 = _alerta(m, "FORNECEDOR_CANDIDATO",
                 "Candidato a " + m["c_forn"] + " em " + m["a_forn"].astype(str) + " (" + m["m_forn"].fillna("") + ", " + m["p_forn"].fillna("") + ")")
    return pd.concat([a1, a2], ignore_index=True)


def cadastro_empresa(g, emp, cands, dias_novo=180):
    if emp is None or emp.empty:
        return pd.DataFrame(columns=COLS)
    m = g[g["data"].notna()].merge(emp, left_on="fornecedor_doc", right_on="cnpj")
    saida = []
    primeiro = m.groupby(["politico_id", "cnpj"])["data"].transform("min")
    novo = m[(m["data"] == primeiro) & m["abertura"].notna() & ((m["data"] - m["abertura"]).dt.days.between(0, dias_novo))]
    saida.append(_alerta(novo, "EMPRESA_RECEM_ABERTA", "Aberta em " + novo["abertura"].dt.strftime("%d/%m/%Y")))
    inat = m[m["situacao"].fillna("ATIVA").str.upper().str.strip() != "ATIVA"]
    inat = inat[inat["data_situacao"].notna() & (inat["data"] > inat["data_situacao"])]
    saida.append(_alerta(inat, "EMPRESA_INATIVA", "Situação: " + inat["situacao"].fillna("") + " desde " + inat["data_situacao"].dt.strftime("%d/%m/%Y")))
    # sócios
    s = m[m["socios"].fillna("") != ""].drop_duplicates(["politico_id", "cnpj"])
    if not s.empty:
        norm = lambda t: " ".join(str(t).upper().split())
        mesmo = s[[norm(p) in [norm(x) for x in soc.split(";")] for p, soc in zip(s["politico_nome"], s["socios"])]]
        saida.append(_alerta(mesmo, "SOCIO_E_POLITICO", "Sócios: " + mesmo["socios"]))
        if cands is not None and not cands.empty:
            chave = set(zip(cands["nome"].map(norm), cands["cpf"].str[3:9]))
            hits, det = [], []
            for _, r in s.iterrows():
                achou = [n for n, d in zip(r["socios"].split(";"), r["socios_docs"].split(";"))
                         if (norm(n), d[-8:-2] if len(d) >= 8 else d) in chave and norm(n) != norm(r["politico_nome"])]
                if achou:
                    hits.append(r.name)
                    det.append("Sócio(s) candidato(s): " + ", ".join(a.strip() for a in achou))
            if hits:
                saida.append(_alerta(s.loc[hits], "SOCIO_CANDIDATO", pd.Series(det, index=hits)))
    return pd.concat(saida, ignore_index=True)


BENFORD = np.log10(1 + 1 / np.arange(1, 10))


def _freq_digitos(v: pd.Series) -> np.ndarray:
    d = v.map(lambda x: int(f"{x:e}"[0])).to_numpy()
    return np.bincount(d, minlength=10)[1:10] / max(len(d), 1)


def benford(g, min_n=400, limiar=0.045):
    """Compara o 1º dígito dos valores de cada político com o padrão de TODOS os políticos
    da mesma fonte (linha de base empírica, mais justa que a curva teórica, porque cada
    categoria de cota tem faixas de preço próprias)."""
    x = g[(g["valor"] >= 10) & g["fonte"].isin(PARLAMENTAR)]
    base = {f: _freq_digitos(s["valor"]) for f, s in x.groupby("fonte")}
    saida = []
    for (pid, fonte), s in x.groupby(["politico_id", "fonte"]):
        if len(s) < min_n:
            continue
        freq = _freq_digitos(s["valor"])
        mad = float(np.abs(freq - base[fonte]).mean())
        if mad > limiar:
            saida.append({"politico_id": pid, "id": None, "valor": float(s["valor"].sum()),
                          "det": f"{fonte}: desvio médio {mad:.3f} do padrão dos colegas em {len(s)} notas "
                                 f"(teórico Benford: {float(np.abs(freq - BENFORD).mean()):.3f})"})
    if not saida:
        return pd.DataFrame(columns=COLS)
    df = pd.DataFrame(saida)
    return _alerta(df, "BENFORD", df["det"])


def valores_redondos(g, min_n=50, fatia=0.5):
    x = g[(g["valor"] >= 500) & g["fonte"].isin(PARLAMENTAR) & ~g["categoria"].str.contains("LOCA|ALUGUEL|IM.VE", na=False)]
    r = x.assign(red=(x["valor"] % 100 == 0)).groupby("politico_id").agg(n=("red", "size"), red=("red", "mean"), valor=("valor", "sum")).reset_index()
    r = r[(r["n"] >= min_n) & (r["red"] >= fatia)]
    r["id"] = None
    return _alerta(r, "VALORES_REDONDOS", (100 * r["red"]).round(0).astype(int).astype(str) + "% das notas acima de R$ 500 têm valor cheio")


def patrimonio(cands, bens, fator=3.0, min_salto=500_000):
    if cands is None or cands.empty or bens is None or bens.empty or "pessoa" not in cands:
        return pd.DataFrame(columns=COLS)
    b = bens.merge(cands[["sq", "pessoa", "ano"]], on=["sq", "ano"]).sort_values("ano")
    b = b.groupby(["pessoa", "ano"], as_index=False)["valor"].sum()
    saida = []
    for pessoa, s_ in b.groupby("pessoa"):
        if len(s_) < 2:
            continue
        a, z = s_.iloc[-2], s_.iloc[-1]
        if a["valor"] > 0 and z["valor"] / a["valor"] >= fator and z["valor"] - a["valor"] >= min_salto:
            saida.append({"politico_id": f"P-{pessoa}", "id": None, "valor": float(z["valor"] - a["valor"]),
                          "det": f"{brl(a['valor'])} em {int(a['ano'])} → {brl(z['valor'])} em {int(z['ano'])}"})
    if not saida:
        return pd.DataFrame(columns=COLS)
    df = pd.DataFrame(saida)
    return _alerta(df, "PATRIMONIO_SALTO", df["det"])


def rodar(gastos, cands=None, bens=None, receitas=None, sanc=None, emp=None) -> pd.DataFrame:
    g = gastos.copy()
    for c in ("fornecedor_doc", "politico_cpf", "documento", "categoria", "fornecedor", "fonte"):
        g[c] = g[c].fillna("").astype(str)
    g["data"] = pd.to_datetime(g["data"], errors="coerce")
    g["fornecedor_doc"] = g["fornecedor_doc"].map(normaliza_doc)
    etapas = [
        ("doc inválido", lambda: doc_invalido(g)),
        ("nota duplicada", lambda: nota_duplicada(g)),
        ("fracionamento", lambda: fracionamento(g)),
        ("valor atípico", lambda: valor_atipico(g)),
        ("refeição cara", lambda: refeicao_cara(g)),
        ("fornecedor exclusivo", lambda: fornecedor_exclusivo(g)),
        ("empresa sancionada", lambda: empresa_sancionada(g, sanc)),
        ("fornecedor doador", lambda: fornecedor_doador(g, receitas)),
        ("sócio doador", lambda: socio_doador(g, receitas, emp)),
        ("doador contratado (município)", lambda: doador_contratado(g, receitas, cands, emp)),
        ("fornecedor candidato", lambda: fornecedor_candidato(g, cands)),
        ("cadastro da empresa", lambda: cadastro_empresa(g, emp, cands)),
        ("Benford", lambda: benford(g)),
        ("valores redondos", lambda: valores_redondos(g)),
        ("patrimônio", lambda: patrimonio(cands, bens)),
    ]
    partes = []
    for nome, f in etapas:
        try:
            a = f()
        except Exception as e:  # noqa: BLE001  — um detector com problema não derruba os outros
            print(f"  detector {nome:<22} ERRO: {type(e).__name__}: {e} (pulado)")
            continue
        print(f"  detector {nome:<22} {len(a):>7} alertas")
        partes.append(a)
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame(columns=COLS)
    out = pd.concat(partes, ignore_index=True)
    out["gastos_ids"] = out["gastos_ids"].fillna(out["gasto_id"])
    return out


def indice_atencao(alertas: pd.DataFrame) -> pd.DataFrame:
    """0–100 relativo: posição do político entre todos os que têm alerta.

    Pontos = soma, por TIPO de alerta, de peso × log2(1 + ocorrências). Assim 1 nota
    duplicada pesa, mas 500 repetições do mesmo tipo não esmagam o resto; o que sobe o
    índice é ter vários tipos diferentes e graves."""
    if alertas.empty:
        return pd.DataFrame(columns=["politico_id", "pontos", "indice", "n_alertas"])
    t = alertas.groupby(["politico_id", "codigo"]).agg(n=("codigo", "size"), grav=("gravidade", "max")).reset_index()
    t["p"] = t["grav"].map(PESO) * np.log2(1 + t["n"])
    r = t.groupby("politico_id").agg(pontos=("p", "sum"), n_alertas=("n", "sum")).reset_index()
    r["indice"] = (100 * r["pontos"].rank(pct=True, method="max")).round(0).astype(int).clip(1, 100)
    r["pontos"] = r["pontos"].round(0).astype(int)
    return r
