"""Gera o pacote (JSON compacto) que o painel web lê.

  python exportar.py                      # Brasil todo (limita gastos pelo --max-gastos)
  python exportar.py --uf MS              # só MS
  python exportar.py --uf MS --municipio DOURADOS
  python exportar.py --cargo Vereador Prefeito

Saída: dados/pacote_radar.json  → carregue no painel ("Carregar pacote").
"""
import argparse
import datetime as dt
import json

import duckdb
import pandas as pd

from radar.detectores import CATALOGO
from radar.util import DADOS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", nargs="+")
    ap.add_argument("--municipio", nargs="+")
    ap.add_argument("--cargo", nargs="+", help="ex.: 'Deputado Federal' Senador Prefeito Vereador")
    ap.add_argument("--max-gastos", type=int, default=120_000, help="limite de gastos no pacote (alertados sempre entram)")
    ap.add_argument("--saida", default=str(DADOS / "pacote_radar.json"))
    a = ap.parse_args()

    con = duckdb.connect(str(DADOS / "radar.duckdb"), read_only=True)
    p = con.execute("SELECT * FROM politicos").df()
    g = con.execute("SELECT * FROM gastos").df()
    al = con.execute("SELECT * FROM alertas").df()
    con.close()

    if a.uf:
        p = p[p["uf"].isin([u.upper() for u in a.uf])]
    if a.municipio:
        p = p[p["municipio"].fillna("").str.upper().isin([m.upper() for m in a.municipio])]
    if a.cargo:
        p = p[p["cargo"].str.lower().isin([c.lower() for c in a.cargo])]
    g = g[g["politico_id"].isin(p["politico_id"])]
    al = al[al["politico_id"].isin(p["politico_id"])]

    alertados = set(al["gasto_id"].dropna()) | {i for ids in al.get("gastos_ids", pd.Series(dtype=str)).dropna() for i in str(ids).split(",")}
    if len(g) > a.max_gastos:
        marca = g["id"].isin(alertados)
        resto = g[~marca].nlargest(max(0, a.max_gastos - int(marca.sum())), "valor")
        g_out = pd.concat([g[marca], resto])
        print(f"Aviso: {len(g):,} gastos no recorte; exportando {len(g_out):,} (todos os alertados + os maiores). "
              "Use --uf/--municipio para ver tudo.".replace(",", "."))
    else:
        g_out = g
    g_out = g_out.sort_values("data", ascending=False)

    pid = {v: i for i, v in enumerate(p["politico_id"])}
    dic = lambda s: {v: i for i, v in enumerate(pd.unique(s.fillna("")))}
    d_cat, d_forn, d_fonte = dic(g_out["categoria"]), dic(g_out["fornecedor"] + "\t" + g_out["fornecedor_doc"]), dic(g_out["fonte"])
    gidx = {v: i for i, v in enumerate(g_out["id"])}

    pacote = {
        "meta": {
            "gerado": dt.datetime.now().isoformat(timespec="minutes"),
            "recorte": {"uf": a.uf, "municipio": a.municipio, "cargo": a.cargo},
            "total_gastos_recorte": int(len(g)), "gastos_no_pacote": int(len(g_out)),
            "valor_total": float(g["valor"].sum()),
            "exemplo": False,
        },
        "catalogo": {k: list(v) for k, v in CATALOGO.items()},
        "fontes": list(d_fonte), "categorias": list(d_cat),
        "fornecedores": [f.split("\t") for f in d_forn],
        "politicos": [[r.nome, r.cargo, r.partido or "", r.uf or "", r.municipio or "", round(float(r.total), 2),
                       int(r.n_gastos), int(r.n_alertas), int(r.indice), r.fontes] for r in p.itertuples()],
        # gastos em colunas: politico, data, fonte, categoria, fornecedor, nº doc, valor, url
        "gastos": {
            "p": g_out["politico_id"].map(pid).tolist(),
            "d": pd.to_datetime(g_out["data"]).dt.strftime("%Y-%m-%d").fillna("").tolist(),
            "f": g_out["fonte"].fillna("").map(d_fonte).tolist(),
            "c": g_out["categoria"].fillna("").map(d_cat).tolist(),
            "s": (g_out["fornecedor"].fillna("") + "\t" + g_out["fornecedor_doc"].fillna("")).map(d_forn).tolist(),
            "n": g_out["documento"].fillna("").tolist(),
            "v": g_out["valor"].round(2).tolist(),
            "u": g_out["url_doc"].fillna("").tolist(),
            "o": g_out["descricao"].fillna("").astype(str).str[:160].tolist() if "descricao" in g_out else [],
        },
        "alertas": [[gidx.get(r.gasto_id, -1) if isinstance(r.gasto_id, str) else -1, pid[r.politico_id], r.codigo,
                     str(r.detalhe or ""), round(float(r.valor or 0), 2),
                     [gidx[i] for i in str(getattr(r, "gastos_ids", "") or "").split(",") if i in gidx][:200]]
                    for r in al.itertuples() if r.politico_id in pid],
    }
    with open(a.saida, "w", encoding="utf-8") as f:
        json.dump(pacote, f, ensure_ascii=False, separators=(",", ":"))
    import os
    print(f"Pacote salvo em {a.saida} ({os.path.getsize(a.saida)/1e6:.1f} MB): "
          f"{len(p)} políticos, {len(g_out)} gastos, {len(pacote['alertas'])} alertas")


if __name__ == "__main__":
    main()
