"""Câmara dos Deputados — Cota para o Exercício da Atividade Parlamentar (CEAP).

Arquivo anual oficial: https://www.camara.leg.br/cotas/Ano-AAAA.csv.zip
Dicionário: https://dadosabertos.camara.leg.br/howtouse/2023-12-26-dados-ceap.html
"""
import pandas as pd

from ..util import BRUTO, baixar, col, csvs_do_zip, ler_csv, so_digitos, valor_br
from . import GASTOS

URL = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"


def coletar(ano: int, forcar=False) -> pd.DataFrame:
    z = baixar(URL.format(ano=ano), BRUTO / "camara" / f"Ano-{ano}.csv.zip", forcar)
    if z is None:
        return pd.DataFrame(columns=GASTOS)
    partes = [ler_csv(b) for _, b in csvs_do_zip(z, r"\.csv$")]
    return normalizar(pd.concat(partes, ignore_index=True))


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    g = lambda *c: df[col(df, *c)] if col(df, *c) else pd.Series([""] * len(df))
    # vlrLiquido já desconta glosa; é o que efetivamente saiu do caixa público
    out = pd.DataFrame({
        "fonte": "CEAP Câmara",
        "cargo": "Deputado Federal",
        "politico_id": "CD-" + g("ideCadastro", "nuDeputadoId").fillna(""),
        "politico_cpf": g("cpf").map(so_digitos),
        "politico_nome": g("txNomeParlamentar").str.strip(),
        "partido": g("sgPartido"),
        "uf": g("sgUF"),
        "municipio": "",
        "data": pd.to_datetime(g("datEmissao").str[:10], errors="coerce"),
        "ano": pd.to_numeric(g("numAno"), errors="coerce"),
        "mes": pd.to_numeric(g("numMes"), errors="coerce"),
        "categoria": g("txtDescricao").str.strip().str.upper(),
        "fornecedor": g("txtFornecedor").str.strip(),
        "fornecedor_doc": g("txtCNPJCPF").map(so_digitos),
        "documento": g("txtNumero").fillna("").str.strip(),
        "valor": valor_br(g("vlrLiquido")),
        "url_doc": g("urlDocumento").fillna(""),
        "descricao": (g("txtDescricaoEspecificacao").fillna("") + " " + g("txtPassageiro").fillna("") + " " + g("txtTrecho").fillna("")).str.strip(),
    })
    # linhas de liderança/partido (sem deputado) ficam fora
    out = out[out["politico_nome"].notna() & ~out["politico_nome"].str.upper().str.startswith(("LIDERANÇA", "LIDERANCA", "LID."), na=False)]
    # sem URL no CSV: monta o link do PDF da nota no site da Câmara
    ide, cad, ano = g("ideDocumento").fillna(""), g("nuDeputadoId", "ideCadastro").fillna(""), g("numAno").fillna("")
    pdf = "https://www.camara.leg.br/cota-parlamentar/documentos/publ/" + cad + "/" + ano + "/" + ide + ".pdf"
    vazio = out["url_doc"].fillna("").str.strip() == ""
    out.loc[vazio, "url_doc"] = pdf.reindex(out.index)[vazio].where(ide.reindex(out.index)[vazio] != "", "")
    out["id"] = "CD" + g("ideDocumento").fillna("").reindex(out.index).astype(str) + "-" + out.index.astype(str)
    return out.reindex(columns=GASTOS, fill_value="")
