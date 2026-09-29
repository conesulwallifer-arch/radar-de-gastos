"""Senado Federal — Cota para o Exercício da Atividade Parlamentar dos Senadores (CEAPS).

Fonte principal: CSV anual da transparência do Senado.
Reserva: API de dados abertos administrativos (JSON).
"""
import io

import pandas as pd
import requests

from ..util import BRUTO, UA, baixar, col, data_br, ler_csv, so_digitos, valor_br
from . import GASTOS

URL_CSV = "https://www.senado.gov.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv"
URL_API = "https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/{ano}"


def coletar(ano: int, forcar=False) -> pd.DataFrame:
    arq = baixar(URL_CSV.format(ano=ano), BRUTO / "senado" / f"despesa_ceaps_{ano}.csv", forcar)
    df = None
    if arq is not None:
        bruto = arq.read_bytes()
        # a 1ª linha é "ULTIMA ATUALIZACAO";"dd/mm/aaaa" — pula se existir
        pula = 1 if bruto[:40].upper().find(b"ULTIMA") >= 0 else 0
        df = ler_csv(io.BytesIO(bruto), encoding="latin-1", skiprows=pula)
    if df is None or df.empty:
        try:
            r = requests.get(URL_API.format(ano=ano), headers=UA, timeout=120)
            r.raise_for_status()
            df = pd.DataFrame(r.json()).astype(str)
        except Exception as e:  # noqa: BLE001
            print(f"  Senado {ano}: sem dados ({e})")
            return pd.DataFrame(columns=GASTOS)
    return normalizar(df)


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    g = lambda *c: df[col(df, *c)] if col(df, *c) else pd.Series([""] * len(df), index=df.index)
    nome = g("SENADOR", "nomeSenador").str.strip()
    out = pd.DataFrame({
        "fonte": "CEAPS Senado",
        "cargo": "Senador",
        "politico_id": "SF-" + g("codSenador").where(g("codSenador") != "", nome),
        "politico_cpf": "",
        "politico_nome": nome,
        "partido": g("partido", "siglaPartido"),
        "uf": g("uf", "siglaUF"),
        "municipio": "",
        "data": data_br(g("DATA", "data")),
        "ano": pd.to_numeric(g("ANO", "ano"), errors="coerce"),
        "mes": pd.to_numeric(g("MES", "mes"), errors="coerce"),
        "categoria": g("TIPO_DESPESA", "tipoDespesa").str.strip().str.upper(),
        "fornecedor": g("FORNECEDOR", "nomeFornecedor").str.strip(),
        "fornecedor_doc": g("CNPJ_CPF", "cpfCnpj").map(so_digitos),
        "documento": g("DOCUMENTO", "documento").fillna(""),
        "valor": valor_br(g("VALOR_REEMBOLSADO", "valorReembolsado")),
        "url_doc": "",
    })
    out["id"] = "SF" + g("COD_DOCUMENTO", "id").astype(str) + "-" + out.index.astype(str)
    out = out[out["politico_nome"] != ""]
    return completar_senadores(out).reindex(columns=GASTOS, fill_value="")


def _nn(s) -> str:
    import unicodedata
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c)).upper().split())


def completar_senadores(out: pd.DataFrame) -> pd.DataFrame:
    """O CSV da CEAPS não traz UF, partido nem código: completa pela API do Senado (legislaturas 55 a 58)."""
    import json
    arq = BRUTO / "senado" / "senadores_55_58.json"
    try:
        if not arq.exists():
            r = requests.get("https://legis.senado.leg.br/dadosabertos/senador/lista/legislatura/55/58.json",
                             headers={**UA, "Accept": "application/json"}, timeout=60)
            r.raise_for_status()
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text(r.text, encoding="utf-8")
        js = json.loads(arq.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"  Senado: não consegui completar UF/partido ({e})")
        return out
    lista = js
    for k in ("ListaParlamentarLegislatura", "Parlamentares", "Parlamentar"):
        lista = lista.get(k, lista) if isinstance(lista, dict) else lista
    mapa = {}
    for p in lista if isinstance(lista, list) else []:
        idp = p.get("IdentificacaoParlamentar", {})
        info = (str(idp.get("CodigoParlamentar", "")), idp.get("UfParlamentar", ""), idp.get("SiglaPartidoParlamentar", ""))
        for n in (idp.get("NomeParlamentar"), idp.get("NomeCompletoParlamentar")):
            if n:
                mapa.setdefault(_nn(n), info)
    achado = out["politico_nome"].map(lambda n: mapa.get(_nn(n)))
    ok = achado.notna()
    out.loc[ok, "politico_id"] = "SF-" + achado[ok].map(lambda x: x[0])
    out.loc[ok & (out["uf"].fillna("") == ""), "uf"] = achado[ok].map(lambda x: x[1])
    out.loc[ok & (out["partido"].fillna("") == ""), "partido"] = achado[ok].map(lambda x: x[2])
    print(f"  Senado: UF/partido completados para {achado[ok].map(lambda x: x[0]).nunique()} senadores")
    return out
