"""Gastos do MANDATO municipal (prefeitura, câmara, fundos, autarquias).

1) PNCP — Portal Nacional de Contratações Públicas (obrigatório pela Lei 14.133):
   todos os contratos, empenhos publicados e atas de cada órgão do município,
   com link para a página do contrato e seus arquivos (PDF).
   API pública: https://pncp.gov.br/api/consulta
2) Importador de planilhas exportadas dos portais de transparência locais
   (pagamentos, empenhos, liquidações, diárias) — veja importar.py.
"""
from __future__ import annotations

import datetime as dt
import json
import time

import pandas as pd
import requests

from ..util import DADOS, UA, normaliza_doc
from . import GASTOS

API = "https://pncp.gov.br/api/consulta/v1"
CACHE = DADOS / "bruto" / "pncp"
MODALIDADES = range(1, 14)  # leilão, diálogo, concurso, concorrência, pregão, dispensa, inexigibilidade...


def _get(path: str, params: dict, tentativas=4):
    for i in range(tentativas):
        try:
            r = requests.get(f"{API}/{path}", params=params, headers=UA, timeout=60)
            if r.status_code == 204:
                return {"data": [], "totalPaginas": 0}
            if r.status_code == 429:
                time.sleep(5 * (i + 1)); continue
            if r.status_code >= 400:
                return {"erro": r.status_code, "data": [], "totalPaginas": 0}
            return r.json()
        except (requests.RequestException, ValueError):
            time.sleep(3 * (i + 1))
    return {"data": [], "totalPaginas": 0}


def _janelas(anos: list[int]):
    """Janelas trimestrais (a API do PNCP limita o intervalo de datas por consulta)."""
    import calendar
    hoje = dt.date.today()
    for a in anos:
        for m in (1, 4, 7, 10):
            ini = dt.date(a, m, 1)
            if ini > hoje:
                return
            fim = dt.date(a, m + 2, calendar.monthrange(a, m + 2)[1])
            yield ini.strftime("%Y%m%d"), min(fim, hoje).strftime("%Y%m%d")


def _paginar(path, params, tam=50):
    pag, itens = 1, []
    while True:
        j = _get(path, {**params, "pagina": pag, "tamanhoPagina": tam})
        itens += j.get("data") or []
        if pag >= (j.get("totalPaginas") or 0):
            return itens
        pag += 1
        time.sleep(0.15)


def descobrir_orgaos(ibge: str, anos: list[int]) -> dict[str, str]:
    """Todos os órgãos MUNICIPAIS do município que publicam no PNCP (prefeitura, câmara, fundos, autarquias)."""
    arq = CACHE / f"orgaos_{ibge}.json"
    orgaos = json.loads(arq.read_text()) if arq.exists() else {}
    if orgaos and time.time() - arq.stat().st_mtime < 7 * 86400:
        return orgaos  # lista de órgãos muda pouco: revisita 1x por semana
    for de, ate in _janelas(anos[-1:]):  # o último ano já revela os órgãos ativos
        for m in MODALIDADES:
            for it in _paginar("contratacoes/publicacao", {"dataInicial": de, "dataFinal": ate,
                                                          "codigoModalidadeContratacao": m, "codigoMunicipioIbge": ibge}):
                o = it.get("orgaoEntidade") or {}
                if o.get("esferaId") == "M" and o.get("cnpj"):
                    orgaos[o["cnpj"]] = o.get("razaoSocial", "")
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(orgaos, ensure_ascii=False))
    return orgaos


def contratos(cnpj: str, anos: list[int], forcar=False) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    todos = []
    ano_atual = dt.date.today().year
    for a in anos:
        arq = CACHE / f"contratos_{cnpj}_{a}.json"
        # anos fechados ficam em cache; o ano corrente é sempre rebaixado
        recente = arq.exists() and time.time() - arq.stat().st_mtime < 86400
        if arq.exists() and not forcar and (a < ano_atual or recente):
            todos += json.loads(arq.read_text())
            continue
        itens = []
        for de, ate in _janelas([a]):
            itens += _paginar("contratos", {"dataInicial": de, "dataFinal": ate, "cnpjOrgao": cnpj}, tam=500)
        arq.write_text(json.dumps(itens, ensure_ascii=False))
        todos += itens
    return todos


def coletar(ibges: list[str], anos: list[int], forcar=False) -> pd.DataFrame:
    linhas = []
    for ibge in ibges:
        print(f"  PNCP: descobrindo órgãos municipais ({ibge})...")
        orgaos = descobrir_orgaos(ibge, anos)
        for cnpj, nome in orgaos.items():
            itens = contratos(cnpj, anos, forcar)
            print(f"    {nome[:55]:<55} {len(itens):>6} contratos/empenhos")
            for c in itens:
                u = c.get("unidadeOrgao") or {}
                o = c.get("orgaoEntidade") or {}
                tipo = (c.get("tipoContrato") or {}).get("nome", "")
                cat = (c.get("categoriaProcesso") or {}).get("nome", "")
                ano, seq = c.get("anoContrato"), c.get("sequencialContrato")
                linhas.append({
                    "id": "PNCP-" + str(c.get("numeroControlePNCP") or f"{cnpj}-{ano}-{seq}"),
                    "fonte": "Contratos PNCP",
                    "cargo": "Órgão municipal",
                    "politico_id": "ORG-" + cnpj,
                    "politico_cpf": "",
                    "politico_nome": (o.get("razaoSocial") or nome).upper(),
                    "partido": "",
                    "uf": u.get("ufSigla", ""),
                    "municipio": str(u.get("municipioNome", "")).upper(),
                    "data": c.get("dataAssinatura") or c.get("dataVigenciaInicio"),
                    "categoria": f"{cat} · {tipo}".strip(" ·").upper(),
                    "fornecedor": c.get("nomeRazaoSocialFornecedor", ""),
                    "fornecedor_doc": normaliza_doc(str(c.get("niFornecedor") or "")),
                    "documento": str(c.get("numeroContratoEmpenho") or ""),
                    "valor": float(c.get("valorGlobal") or c.get("valorInicial") or 0),
                    "url_doc": f"https://pncp.gov.br/app/contratos/{cnpj}/{ano}/{seq}" if ano and seq else "",
                    "descricao": str(c.get("objetoContrato") or "")[:500],
                })
    df = pd.DataFrame(linhas)
    if df.empty:
        return pd.DataFrame(columns=GASTOS)
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["ano"], df["mes"] = df["data"].dt.year, df["data"].dt.month
    return df.drop_duplicates("id").reindex(columns=GASTOS, fill_value="")
