"""Radar de Gastos — coleta dados oficiais, roda os detectores e grava tudo em dados/radar.duckdb.

Exemplos:
  python coletar.py                                   # padrão: CEAP/CEAPS 2023–ano atual, TSE 2022 e 2024, Brasil todo
  python coletar.py --ufs MS                          # só MS no TSE (bem mais rápido)
  python coletar.py --anos 2025 2026 --eleicoes 2024  # recorte
  python coletar.py --so-detectar                     # reprocessa alertas sem baixar de novo
"""
import argparse
import datetime as dt
import unicodedata

import duckdb
import pandas as pd

from radar import detectores
from radar.fontes import GASTOS, camara, empresas, importar, municipio, senado, tse
from radar.util import DADOS, normaliza_doc

BANCO = DADOS / "radar.duckdb"


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode()
    return " ".join(t.upper().split())


def unificar_ids(g: pd.DataFrame, cands: pd.DataFrame) -> pd.DataFrame:
    """Mesmo político em fontes diferentes passa a ter o mesmo id (P-<CPF ou nome+nascimento>).

    Câmara e Senado são ligados ao TSE pelo CPF (quando o TSE não mascarou) ou pelo
    nome de urna/nome civil + UF dos candidatos a deputado federal e senador."""
    g["fornecedor_doc"] = g["fornecedor_doc"].map(normaliza_doc)
    parl = g["fonte"].isin(["CEAP Câmara", "CEAPS Senado"])
    if parl.any():
        pessoas_cpf, por_nome = set(), {}
        if not cands.empty:
            fed = cands[cands["cargo"].str.contains("Deputado Federal|Senador", case=False, na=False)]
            fed = fed.sort_values(["eleito", "ano"], ascending=False)
            pessoas_cpf = set(cands["pessoa"])
            for r in fed.itertuples():
                for n in (r.nome_urna, r.nome):
                    por_nome.setdefault((norm(n), r.uf), r.pessoa)
        def achar(cpf, nome, uf):
            if cpf and cpf in pessoas_cpf:
                return cpf
            return por_nome.get((norm(nome), uf)) or (cpf if cpf else None)
        sub = g.loc[parl]
        ids = [achar(c, n, u) for c, n, u in zip(sub["politico_cpf"].fillna(""), sub["politico_nome"], sub["uf"])]
        g.loc[parl, "politico_id"] = [("P-" + i) if i else old for i, old in zip(ids, sub["politico_id"])]
    return g


def montar_politicos(g: pd.DataFrame, cands: pd.DataFrame, indice: pd.DataFrame) -> pd.DataFrame:
    g = g.sort_values("data")
    p = g.groupby("politico_id").agg(
        nome=("politico_nome", "last"), cargo=("cargo", "last"), partido=("partido", "last"),
        uf=("uf", "last"), municipio=("municipio", "last"), cpf=("politico_cpf", "last"),
        total=("valor", "sum"), n_gastos=("valor", "size"),
        fontes=("fonte", lambda s: ", ".join(sorted(set(s)))),
    ).reset_index()
    p = p.merge(indice, on="politico_id", how="left")
    p[["pontos", "n_alertas", "indice"]] = p[["pontos", "n_alertas", "indice"]].fillna(0).astype(int)
    return p.sort_values(["indice", "total"], ascending=False)


def main():
    hoje = dt.date.today().year
    ap = argparse.ArgumentParser()
    ap.add_argument("--anos", nargs="+", type=int, default=list(range(2023, hoje + 1)), help="anos da cota parlamentar")
    ap.add_argument("--eleicoes", nargs="+", type=int, default=[2022, 2024], help="eleições do TSE (2024=prefeitos/vereadores)")
    ap.add_argument("--municipio", nargs="+", default=[], metavar="NOME:IBGE",
                    help="gastos do mandato municipal (PNCP + planilhas em dados/importar). Ex.: DOURADOS:5003702")
    ap.add_argument("--ufs", nargs="+", default=None, help="filtra o TSE por UF (ex.: MS SP)")
    ap.add_argument("--todos-candidatos", action="store_true", help="inclui gastos de campanha de não eleitos")
    ap.add_argument("--top-cnpj", type=int, default=400, help="quantos CNPJs consultar na Receita (0 desliga)")
    ap.add_argument("--cnpj-por-politico", type=int, default=5, help="maiores CNPJs de cada político do recorte a consultar")
    ap.add_argument("--forcar", action="store_true", help="baixa tudo de novo, ignorando cache")
    ap.add_argument("--so-detectar", action="store_true", help="não baixa: só roda os detectores sobre o banco")
    a = ap.parse_args()
    if a.ufs:
        a.ufs = [u.upper() for u in a.ufs]

    con = duckdb.connect(str(BANCO))
    if not a.so_detectar:
        partes = []
        for ano in a.anos:
            print(f"Câmara {ano}...");  partes.append(camara.coletar(ano, a.forcar))
            print(f"Senado {ano}...");  partes.append(senado.coletar(ano, a.forcar))
        cands, bens_, recs = [], [], []
        for el in a.eleicoes:
            print(f"TSE {el}: candidatos, bens e contas...")
            c = tse.candidatos(el, a.ufs, a.forcar)
            if c.empty:
                continue
            cands.append(c)
            bens_.append(tse.bens(el, a.ufs, a.forcar))
            # anteriores (2018/2020) só para comparar patrimônio
            gas, rec = tse.contas(el, c, a.ufs, not a.todos_candidatos, a.forcar)
            partes.append(gas); recs.append(rec)
        for el in {e - 4 for e in a.eleicoes}:
            print(f"TSE {el}: candidatos e bens (comparação de patrimônio)...")
            c = tse.candidatos(el, a.ufs, a.forcar)
            if not c.empty:
                cands.append(c); bens_.append(tse.bens(el, a.ufs, a.forcar))

        cands = pd.concat(cands, ignore_index=True) if cands else pd.DataFrame(columns=["ano", "sq", "cpf", "nome", "nome_urna", "cargo", "uf", "municipio", "partido", "situacao", "eleito"])
        for mun in a.municipio:
            nome_m, _, ibge = mun.partition(":")
            print(f"Município {nome_m}: contratos no PNCP e planilhas dos portais...")
            if ibge:
                partes.append(municipio.coletar([ibge], a.anos, a.forcar))
            partes.append(importar.coletar(nome_m, (a.ufs or ["MS"])[0], cands))
        g = pd.concat([p for p in partes if not p.empty], ignore_index=True).reindex(columns=GASTOS, fill_value="")
        id_orig = g["politico_id"].copy()
        g = unificar_ids(g, cands)
        parl = g["fonte"].isin(["CEAP Câmara", "CEAPS Senado"])
        ids_ext = (pd.DataFrame({"politico_id": g.loc[parl, "politico_id"], "id_origem": id_orig[parl]})
                   .drop_duplicates().reset_index(drop=True))
        print("TSE: redes sociais dos eleitos...")
        redes = [tse.redes_sociais(int(an), cands.loc[(cands["ano"] == an) & cands["eleito"], "sq"], a.ufs, a.forcar)
                 for an in sorted(set(cands["ano"].unique()) & set(a.eleicoes))] if len(cands) else []
        redes = pd.concat(redes, ignore_index=True) if redes else pd.DataFrame(columns=["ano", "sq", "url"])
        # datas digitadas erradas na origem (ano 0023, 2049...) ficam em branco
        g["data"] = pd.to_datetime(g["data"], errors="coerce")
        ruim = (g["data"].dt.year < 2000) | (g["data"].dt.year > dt.date.today().year)
        g.loc[ruim, "data"] = pd.NaT
        print(f"{len(g):,} gastos coletados".replace(",", "."))

        print("Sanções CEIS/CNEP..."); sanc = empresas.sancoes(a.forcar)
        emp = pd.DataFrame()
        if a.top_cnpj:
            cnpj = g[g["fornecedor_doc"].str.len() == 14]
            top = cnpj.groupby("fornecedor_doc")["valor"].sum().sort_values(ascending=False).head(a.top_cnpj).index.tolist()
            # + os maiores fornecedores de CADA político do recorte (para os cruzamentos de sócios)
            loc = cnpj[cnpj["uf"].isin(a.ufs)] if a.ufs else cnpj[cnpj["fonte"] != "CEAP Câmara"]
            por_pol = (loc.groupby(["politico_id", "fornecedor_doc"])["valor"].sum().reset_index()
                       .sort_values("valor", ascending=False))
            eh_org = por_pol["politico_id"].str.startswith("ORG")
            # órgãos municipais: os 80 maiores fornecedores; políticos: os N maiores
            por_pol = pd.concat([por_pol[eh_org].groupby("politico_id").head(80),
                                 por_pol[~eh_org].groupby("politico_id").head(a.cnpj_por_politico)])
            top = list(dict.fromkeys(top + por_pol["fornecedor_doc"].tolist()))
            print(f"Receita: consultando {len(top)} CNPJs (os já consultados vêm do cache)...")
            emp = empresas.enriquecer_cnpjs(top, limite=3000)

        for nome, df in {"gastos": g, "candidatos": cands,
                         "bens": pd.concat(bens_, ignore_index=True) if bens_ else pd.DataFrame(columns=["ano", "sq", "valor"]),
                         "receitas": pd.concat(recs, ignore_index=True) if recs else pd.DataFrame(columns=["ano", "sq", "politico_cpf", "doador_doc", "doador", "valor"]),
                         "sancoes": sanc, "empresas": emp, "ids_externos": ids_ext, "redes": redes}.items():
            if df.shape[1] == 0:
                continue
            con.register("tmp", df)
            con.execute(f"CREATE OR REPLACE TABLE {nome} AS SELECT * FROM tmp")
            con.unregister("tmp")

    t = lambda n: con.execute(f"SELECT * FROM {n}").df() if con.execute(
        f"SELECT count(*) FROM information_schema.tables WHERE table_name='{n}'").fetchone()[0] else pd.DataFrame()
    g, cands = t("gastos"), t("candidatos")
    print("Rodando detectores...")
    alertas = detectores.rodar(g, cands, t("bens"), t("receitas"), t("sancoes"), t("empresas"))
    politicos = montar_politicos(g, cands, detectores.indice_atencao(alertas))
    for nome, df in {"alertas": alertas, "politicos": politicos}.items():
        con.register("tmp", df)
        con.execute(f"CREATE OR REPLACE TABLE {nome} AS SELECT * FROM tmp")
        con.unregister("tmp")
    con.close()
    print(f"\nPronto: {len(g):,} gastos · {len(politicos):,} políticos · {len(alertas):,} alertas".replace(",", "."))
    print("Veja no navegador:  streamlit run app.py")
    print("Gere o pacote do painel web:  python exportar.py --uf MS")


if __name__ == "__main__":
    main()
