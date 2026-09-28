"""Empresas: sanções (CEIS/CNEP — CGU) e cadastro na Receita (abertura, situação, sócios)."""
import datetime as dt
import json
import time

import pandas as pd
import requests

from ..util import BRUTO, DADOS, UA, baixar, col, csvs_do_zip, ler_csv, so_digitos

URL_SANCAO = "https://portaldatransparencia.gov.br/download-de-dados/{base}/{data}"
CACHE_CNPJ = DADOS / "cache_cnpj.json"


def sancoes(forcar=False) -> pd.DataFrame:
    """Baixa o arquivo mais recente do CEIS e do CNEP (tenta os últimos 15 dias)."""
    partes = []
    for base in ("ceis", "cnep"):
        candidatos = []
        for d in range(4):  # tenta os últimos dias; depois cai no último arquivo guardado
            data = (dt.date.today() - dt.timedelta(days=d)).strftime("%Y%m%d")
            z = baixar(URL_SANCAO.format(base=base, data=data), BRUTO / "cgu" / f"{base}_{data}.zip", forcar)
            if z is not None:
                candidatos = [z]
                break
        if not candidatos:
            guardados = sorted((BRUTO / "cgu").glob(f"{base}_*.zip"))
            if guardados:
                print(f"  {base.upper()}: usando o arquivo já baixado {guardados[-1].name}")
                candidatos = [guardados[-1]]
        for z in candidatos:
            for _, b in csvs_do_zip(z, r"\.csv$"):
                df = ler_csv(b, encoding="latin-1")
                c_doc = col(df, "CPF OU CNPJ DO SANCIONADO")
                if not c_doc:
                    continue
                partes.append(pd.DataFrame({
                    "cadastro": base.upper(),
                    "doc": df[c_doc].map(so_digitos),
                    "nome": df[col(df, "NOME DO SANCIONADO", "NOME INFORMADO PELO ÓRGÃO SANCIONADOR")],
                    "tipo": df[col(df, "CATEGORIA DA SANÇÃO")] if col(df, "CATEGORIA DA SANÇÃO") else "",
                    "orgao": df[col(df, "ÓRGÃO SANCIONADOR")] if col(df, "ÓRGÃO SANCIONADOR") else "",
                    "inicio": pd.to_datetime(df[col(df, "DATA INÍCIO SANÇÃO")], dayfirst=True, errors="coerce"),
                    "fim": pd.to_datetime(df[col(df, "DATA FINAL SANÇÃO")], dayfirst=True, errors="coerce"),
                }))
            break
    if not partes:
        print("  CEIS/CNEP: não foi possível baixar (o detector de sanções ficará desligado)")
        return pd.DataFrame(columns=["cadastro", "doc", "nome", "tipo", "orgao", "inicio", "fim"])
    return pd.concat(partes, ignore_index=True)


def _consulta(cnpj: str) -> dict | None:
    for url in (f"https://minhareceita.org/{cnpj}", f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}"):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(10)
        except requests.RequestException:
            pass
    return None


def enriquecer_cnpjs(cnpjs: list[str], limite: int = 500, pausa: float = 0.4) -> pd.DataFrame:
    """Consulta dados da Receita dos CNPJs mais relevantes (com cache em disco)."""
    cache = json.loads(CACHE_CNPJ.read_text()) if CACHE_CNPJ.exists() else {}
    novos = [c for c in cnpjs if c not in cache][:limite]
    for i, c in enumerate(novos, 1):
        cache[c] = _consulta(c) or {}
        if i % 25 == 0:
            print(f"  CNPJ {i}/{len(novos)}")
            CACHE_CNPJ.write_text(json.dumps(cache))
        time.sleep(pausa)
    CACHE_CNPJ.write_text(json.dumps(cache))

    linhas = []
    for c in cnpjs:
        j = cache.get(c) or {}
        if not j:
            continue
        socios = j.get("qsa") or []
        linhas.append({
            "cnpj": c,
            "abertura": j.get("data_inicio_atividade"),
            "situacao": j.get("descricao_situacao_cadastral"),
            "data_situacao": j.get("data_situacao_cadastral"),
            "cnae": j.get("cnae_fiscal_descricao"),
            "capital": j.get("capital_social"),
            "porte": j.get("porte") or j.get("descricao_porte"),
            "municipio_empresa": j.get("municipio"),
            "uf_empresa": j.get("uf"),
            "socios": "; ".join(str(s.get("nome_socio", "")) for s in socios),
            "socios_docs": "; ".join(so_digitos(str(s.get("cnpj_cpf_do_socio", ""))) for s in socios),
        })
    df = pd.DataFrame(linhas)
    if not df.empty:
        df["abertura"] = pd.to_datetime(df["abertura"], errors="coerce")
        df["data_situacao"] = pd.to_datetime(df["data_situacao"], errors="coerce")
    return df
