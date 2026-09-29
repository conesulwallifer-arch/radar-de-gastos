"""ICMS, IPVA e ITCD de todos os estados, mês a mês (Tesouro Nacional / SICONFI, RREO Anexo 3).

API aberta: https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo
O RREO é bimestral e traz os últimos 12 meses de cada tributo. Os estados publicam
até 30 dias depois do fim do bimestre.
"""
from __future__ import annotations

import json
import time
import unicodedata

import pandas as pd
import requests

from radar.util import DADOS, UA

API = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo"
PASTA = DADOS / "bruto" / "siconfi"
UFS = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE",
       24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP",
       41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}
TRIBUTOS = {"icms": "ICMS", "ipva": "IPVA", "itcd": "ITCD (herança e doação)", "itcmd": "ITCD (herança e doação)"}


def _n(s) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c)).strip().lower()


def _rreo(ente: int, ano: int, periodo: int, esfera: str = "E") -> list[dict]:
    """Baixa (com cache em disco) o Anexo 3 do RREO. Resposta vazia é rechecada após 12 h."""
    arq = PASTA / f"rreo3_{ente}_{ano}_{periodo}.json"
    if arq.exists():
        itens = json.loads(arq.read_text(encoding="utf-8"))
        if itens or time.time() - arq.stat().st_mtime < 12 * 3600:
            return itens
    params = {"an_exercicio": ano, "nr_periodo": periodo, "co_tipo_demonstrativo": "RREO",
              "no_anexo": "RREO-Anexo 03", "co_esfera": esfera, "id_ente": ente}
    itens, offset = [], 0
    for _ in range(10):
        r = requests.get(API, params={**params, "offset": offset}, headers=UA, timeout=60)
        r.raise_for_status()
        js = r.json()
        itens += js.get("items", [])
        if not js.get("hasMore"):
            break
        offset += js.get("limit", 5000)
    PASTA.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(itens, ensure_ascii=False), encoding="utf-8")
    return itens


def _mensal(itens: list[dict], ano: int, periodo: int) -> pd.DataFrame:
    """Converte colunas <MR-k> em datas reais."""
    ult = pd.Timestamp(ano, 2 * periodo, 1)
    linhas = []
    for it in itens:
        trib = TRIBUTOS.get(_n(it.get("conta")))
        col = str(it.get("coluna", "")).strip()
        if not trib or not col.startswith("<MR"):
            continue
        k = col.strip("<>").replace("MR", "").strip() or "0"
        try:
            k = abs(int(k))
        except ValueError:
            continue
        linhas.append((ult - pd.DateOffset(months=k), trib, float(it.get("valor") or 0)))
    df = pd.DataFrame(linhas, columns=["data", "tributo", "valor"])
    # a mesma conta pode aparecer em mais de uma seção: fica com o maior (bruto)
    return df.groupby(["data", "tributo"], as_index=False)["valor"].max()


def ultimo_periodo(ano: int, ente: int = 35) -> int | None:
    for p in range(6, 0, -1):
        try:
            if _rreo(ente, ano, p):
                return p
        except Exception:  # noqa: BLE001
            continue
    return None


def coletar(anos: list[int] | None = None, log=print) -> pd.DataFrame:
    """Série mensal por UF: data, uf, tributo, valor. Usa o relatório mais recente de cada ano
    (que cobre os últimos 12 meses) e, para anos fechados, o 6º bimestre."""
    hoje = pd.Timestamp.now()
    anos = anos or [hoje.year - 1, hoje.year]
    partes = []
    for ano in sorted(anos):
        p_ref = 6 if ano < hoje.year else ultimo_periodo(ano)
        if p_ref is None:
            continue
        for ente, uf in UFS.items():
            for p in range(p_ref, 0, -1):          # estado atrasado: pega o bimestre anterior
                try:
                    itens = _rreo(ente, ano, p)
                except Exception as e:  # noqa: BLE001
                    log(f"  SICONFI {uf} {ano}/{p}: {e}")
                    itens = []
                if itens:
                    m = _mensal(itens, ano, p)
                    partes.append(m.assign(uf=uf, ano_rel=ano))
                    break
    if not partes:
        return pd.DataFrame(columns=["data", "uf", "tributo", "valor"])
    df = pd.concat(partes, ignore_index=True)
    # o relatório mais novo prevalece quando dois cobrem o mesmo mês
    df = df.sort_values("ano_rel").drop_duplicates(["data", "uf", "tributo"], keep="last")
    return df.drop(columns="ano_rel").sort_values(["data", "uf"]).reset_index(drop=True)


def ritmo(df: pd.DataFrame, agora: pd.Timestamp | None = None) -> dict | None:
    """Acumulado real do ano (até o último mês publicado por todos) + ritmo dos últimos 12 meses."""
    agora = agora or pd.Timestamp.now()
    if df.empty:
        return None
    tot = df.groupby("data")["valor"].sum()
    # último mês em que a maioria dos estados já publicou
    n_uf = df.groupby("data")["uf"].nunique()
    completos = n_uf[n_uf >= n_uf.max()].index  # só meses em que TODOS os estados já publicaram
    ultimo = max(completos) if len(completos) else tot.index.max()
    tot = tot[tot.index <= ultimo]
    ult12 = tot[tot.index > ultimo - pd.DateOffset(months=12)]
    fim = ultimo + pd.offsets.MonthBegin(1)
    seg = (fim - (ultimo - pd.DateOffset(months=11))).total_seconds()
    ini_ano = pd.Timestamp(agora.year, 1, 1)
    return {"por_segundo": float(ult12.sum() / seg), "oficial_ano": float(tot[tot.index >= ini_ano].sum()),
            "base_ts": max(fim, ini_ano), "ultimo_mes": ultimo, "ult12": float(ult12.sum())}
