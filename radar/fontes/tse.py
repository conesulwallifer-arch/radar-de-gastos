"""TSE — candidatos, bens declarados e prestação de contas de campanha.

É a única fonte NACIONAL e padronizada, gasto a gasto, para prefeitos e vereadores
(eleições municipais: 2020, 2024) e também para deputados/senadores (2018, 2022).

Portal: https://dadosabertos.tse.jus.br
"""
import re

import pandas as pd

from ..util import BRUTO, baixar, chave_pessoa, col, cpf_valido, csvs_do_zip, ler_csv, normaliza_doc, so_digitos, valor_br
from . import GASTOS

CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"
URL_CAND = CDN + "/consulta_cand/consulta_cand_{ano}.zip"
URL_REDES = CDN + "/consulta_cand/rede_social_candidato_{ano}.zip"
URL_BENS = CDN + "/bem_candidato/bem_candidato_{ano}.zip"
URL_CONTAS = CDN + "/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip"

ELEITO = re.compile(r"^ELEITO", re.I)


def _ler(zipurl: str, nome_local: str, padrao: str, ufs: list[str] | None, forcar=False,
         usecols=None, filtro=None) -> pd.DataFrame:
    """Lê os CSVs por UF de um zip do TSE, em streaming e em blocos (não estoura a memória)."""
    z = baixar(zipurl, BRUTO / "tse" / nome_local, forcar)
    if z is None:
        return pd.DataFrame()
    partes = []
    arquivos = csvs_do_zip(z, padrao)
    tem_uf = any(not n.upper().endswith("_BRASIL.CSV") for n, _ in arquivos)
    for nome, abrir in arquivos:
        # o arquivo _BRASIL repete todos os estaduais: pulamos para não duplicar
        if tem_uf and nome.upper().endswith("_BRASIL.CSV"):
            continue
        if ufs and not tem_uf:
            f0 = filtro
            filtro = (lambda b, f0=f0: (f0(b) if f0 else b).pipe(lambda x: x[x["SG_UF"].isin(ufs)] if "SG_UF" in x else x))
        uf_arq = re.search(r"_([A-Z]{2})\.csv$", nome, re.I)
        if ufs and uf_arq and uf_arq.group(1).upper() not in ufs:
            continue
        print(f"    lendo {nome.split('/')[-1]}")
        df = ler_csv(abrir, encoding="latin-1", usecols=usecols, filtro=filtro)
        if len(df):
            partes.append(df)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


COLS_CAND = ["SQ_CANDIDATO", "NR_CPF_CANDIDATO", "NM_CANDIDATO", "NM_URNA_CANDIDATO", "DS_CARGO",
             "SG_UF", "NM_UE", "SG_PARTIDO", "DS_SIT_TOT_TURNO", "DT_NASCIMENTO",
             "CD_ELEICAO", "SG_UE", "NR_CANDIDATO", "DS_GRAU_INSTRUCAO", "DS_OCUPACAO"]
COLS_DESP = ["SQ_CANDIDATO", "DS_CARGO", "NM_CANDIDATO", "SG_PARTIDO", "SG_UF", "NM_UE", "DT_DESPESA",
             "DS_ORIGEM_DESPESA", "NM_FORNECEDOR", "NR_CPF_CNPJ_FORNECEDOR", "NR_DOCUMENTO", "SQ_DESPESA",
             "VR_DESPESA_CONTRATADA", "DS_DESPESA"]
COLS_REC = ["SQ_CANDIDATO", "NR_CPF_CNPJ_DOADOR", "NM_DOADOR", "VR_RECEITA"]


def candidatos(ano: int, ufs=None, forcar=False) -> pd.DataFrame:
    df = _ler(URL_CAND.format(ano=ano), f"consulta_cand_{ano}.zip", r"consulta_cand_.*\.csv$", ufs, forcar, usecols=COLS_CAND)
    if df.empty:
        return df
    g = lambda c: df[c] if c in df.columns else ""
    out = pd.DataFrame({
        "ano": ano,
        "sq": g("SQ_CANDIDATO"),
        "cpf": g("NR_CPF_CANDIDATO").map(so_digitos) if "NR_CPF_CANDIDATO" in df else "",
        "nome": g("NM_CANDIDATO"),
        "nome_urna": g("NM_URNA_CANDIDATO"),
        "cargo": g("DS_CARGO").str.title(),
        "uf": g("SG_UF"),
        "municipio": g("NM_UE"),
        "partido": g("SG_PARTIDO"),
        "situacao": g("DS_SIT_TOT_TURNO"),
        "cd_eleicao": g("CD_ELEICAO"),
        "sg_ue": g("SG_UE"),
        "numero": g("NR_CANDIDATO"),
        "instrucao": g("DS_GRAU_INSTRUCAO"),
        "ocupacao": g("DS_OCUPACAO"),
        "nascimento": g("DT_NASCIMENTO"),
    })
    # o TSE mascara o CPF em várias bases (ex.: "-4"): só aceitamos CPF válido
    out["cpf"] = out["cpf"].map(lambda c: c if isinstance(c, str) and len(c) == 11 and cpf_valido(c) else "")
    nasc = g("DT_NASCIMENTO") if "DT_NASCIMENTO" in df else pd.Series([""] * len(df), index=df.index)
    out["pessoa"] = [chave_pessoa(c, n, d) for c, n, d in zip(out["cpf"], out["nome"], nasc)]
    out["eleito"] = out["situacao"].fillna("").str.match(ELEITO)
    # um candidato pode aparecer em 2 turnos: fica a linha "mais eleita"
    return out.sort_values("eleito", ascending=False).drop_duplicates("sq")


def redes_sociais(ano: int, sqs, ufs=None, forcar=False) -> pd.DataFrame:
    """Sites e redes sociais que o candidato declarou ao TSE (Instagram, Facebook, etc.)."""
    sqs = set(sqs)
    try:
        df = _ler(URL_REDES.format(ano=ano), f"rede_social_candidato_{ano}.zip", r"rede_social_candidato_.*\.csv$",
                  ufs, forcar, usecols=["SQ_CANDIDATO", "DS_URL"], filtro=lambda b: b[b["SQ_CANDIDATO"].isin(sqs)])
    except Exception as e:  # noqa: BLE001
        print(f"  redes sociais {ano}: {e}")
        return pd.DataFrame(columns=["ano", "sq", "url"])
    if df.empty:
        return pd.DataFrame(columns=["ano", "sq", "url"])
    out = pd.DataFrame({"ano": ano, "sq": df["SQ_CANDIDATO"], "url": df["DS_URL"].fillna("").str.strip()})
    return out[out["url"] != ""].drop_duplicates()


def bens(ano: int, ufs=None, forcar=False) -> pd.DataFrame:
    df = _ler(URL_BENS.format(ano=ano), f"bem_candidato_{ano}.zip", r"bem_candidato_.*\.csv$", ufs, forcar,
               usecols=["SQ_CANDIDATO", "VR_BEM_CANDIDATO"])
    if df.empty:
        return pd.DataFrame(columns=["ano", "sq", "valor"])
    df["valor"] = valor_br(df["VR_BEM_CANDIDATO"])
    t = df.groupby("SQ_CANDIDATO", as_index=False)["valor"].sum().rename(columns={"SQ_CANDIDATO": "sq"})
    t["ano"] = ano
    return t


def contas(ano: int, cands: pd.DataFrame, ufs=None, so_eleitos=True, forcar=False):
    """Retorna (gastos no esquema unificado, receitas)."""
    zipurl, local = URL_CONTAS.format(ano=ano), f"prestacao_contas_candidatos_{ano}.zip"
    alvo = cands[cands["eleito"]] if so_eleitos else cands
    alvo = alvo.set_index("sq")
    sqs = set(alvo.index)
    so_alvo = lambda b: b[b["SQ_CANDIDATO"].isin(sqs)]
    desp = _ler(zipurl, local, r"despesas_contratadas_candidatos_.*\.csv$", ufs, forcar, COLS_DESP, so_alvo)
    rec = _ler(zipurl, local, r"receitas_candidatos_\d{4}_[A-Z]{2}\.csv$", ufs, forcar, COLS_REC, so_alvo)

    gastos = pd.DataFrame(columns=GASTOS)
    if not desp.empty:
        d = desp[desp["SQ_CANDIDATO"].isin(alvo.index)].copy()
        c = alvo.reindex(d["SQ_CANDIDATO"].values)
        cpf = c["cpf"].fillna("").values
        sq = d["SQ_CANDIDATO"].values
        gastos = pd.DataFrame({
            "fonte": f"Campanha {ano} (TSE)",
            "cargo": d["DS_CARGO"].str.title().values,
            "politico_id": ("P-" + c["pessoa"]).values,
            "politico_cpf": cpf,
            "politico_nome": d["NM_CANDIDATO"].values,
            "partido": d["SG_PARTIDO"].values,
            "uf": d["SG_UF"].values,
            "municipio": d["NM_UE"].values,
            "data": pd.to_datetime(d["DT_DESPESA"], dayfirst=True, errors="coerce").values,
            "categoria": d[col(d, "DS_ORIGEM_DESPESA")].str.upper().values,
            "fornecedor": d[col(d, "NM_FORNECEDOR")].values,
            "fornecedor_doc": d[col(d, "NR_CPF_CNPJ_FORNECEDOR")].map(normaliza_doc).values,
            "documento": d[col(d, "NR_DOCUMENTO")].fillna("").values if col(d, "NR_DOCUMENTO") else "",
            "valor": valor_br(d["VR_DESPESA_CONTRATADA"]).values,
            "url_doc": "",
            "descricao": d["DS_DESPESA"].fillna("").values if "DS_DESPESA" in d else "",
        })
        gastos["ano"] = gastos["data"].dt.year
        gastos["mes"] = gastos["data"].dt.month
        gastos["id"] = f"TSE{ano}-" + d[col(d, "SQ_DESPESA") or "SQ_CANDIDATO"].astype(str).values + "-" + pd.Series(range(len(d))).astype(str).values
        gastos = gastos.reindex(columns=GASTOS, fill_value="")

    receitas = pd.DataFrame(columns=["ano", "sq", "politico_id", "politico_cpf", "doador_doc", "doador", "valor"])
    if not rec.empty:
        r = rec
        receitas = pd.DataFrame({
            "ano": ano,
            "sq": r["SQ_CANDIDATO"].values,
            "politico_id": ("P-" + cands.set_index("sq")["pessoa"].reindex(r["SQ_CANDIDATO"].values).fillna("?")).values,
            "politico_cpf": cands.set_index("sq")["cpf"].reindex(r["SQ_CANDIDATO"].values).fillna("").values,
            "doador_doc": r[col(r, "NR_CPF_CNPJ_DOADOR")].map(normaliza_doc).values,
            "doador": r[col(r, "NM_DOADOR")].values,
            "valor": valor_br(r["VR_RECEITA"]).values,
        })
    return gastos, receitas
