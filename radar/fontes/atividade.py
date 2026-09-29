"""Atuação no Legislativo: como cada deputado e senador VOTOU (PECs, PLs, MPs...) — dados oficiais.

Câmara: https://dadosabertos.camara.leg.br/api/v2/votacoes (plenário) + /votacoes/{id}/votos
Senado: https://legis.senado.leg.br/dadosabertos/senador/{codigo}/votacoes.json?ano=AAAA
Tudo fica em cache (votação já encerrada não muda).
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from ..util import BRUTO, UA

CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"
HEAD = {**UA, "Accept": "application/json"}
PASTA = BRUTO / "votacoes"
COLS = ["casa", "votacao_id", "data", "proposicao", "tipo", "ementa", "descricao", "resultado", "parlamentar_id", "voto"]


def _get(url: str, params=None, tentativas=4):
    for i in range(tentativas):
        try:
            r = requests.get(url, params=params, headers=HEAD, timeout=60)
            if r.status_code == 429:
                time.sleep(5 * (i + 1)); continue
            if r.status_code >= 400:
                return None
            return r.json()
        except (requests.RequestException, ValueError):
            time.sleep(2 * (i + 1))
    return None


def _cache(nome: str, url: str, params=None, sempre=False):
    arq = PASTA / nome
    if arq.exists() and not sempre:
        return json.loads(arq.read_text(encoding="utf-8"))
    js = _get(url, params)
    if js is not None:
        PASTA.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
    return js


def _achar(obj, chave):
    if isinstance(obj, dict):
        if chave in obj:
            return obj[chave]
        for v in obj.values():
            r = _achar(v, chave)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _achar(v, chave)
            if r is not None:
                return r
    return None


def _lista(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


# ----------------------------------------------------------------------------- Câmara
def _votacoes_do_mes(ano: int, mes: int) -> list[str]:
    ini = dt.date(ano, mes, 1)
    if ini > dt.date.today():
        return []
    fim = dt.date(ano, mes, calendar.monthrange(ano, mes)[1])
    atual = fim >= dt.date.today() - dt.timedelta(days=3)
    js = _cache(f"cd_lista_{ano}_{mes:02d}.json", f"{CAMARA}/votacoes",
                {"idOrgao": 180, "dataInicio": ini.isoformat(), "dataFim": min(fim, dt.date.today()).isoformat(),
                 "itens": 200, "ordem": "ASC", "ordenarPor": "dataHoraRegistro"}, sempre=atual)
    return [str(v["id"]) for v in (js or {}).get("dados", [])]


def _votacao_camara(vid: str) -> list[dict]:
    det = _cache(f"cd_{vid}.json", f"{CAMARA}/votacoes/{vid}")
    votos = _cache(f"cd_{vid}_votos.json", f"{CAMARA}/votacoes/{vid}/votos")
    vs = (votos or {}).get("dados") or []
    if not vs:  # votação simbólica: não há voto individual
        return []
    d = (det or {}).get("dados") or {}
    props = d.get("proposicoesAfetadas") or []
    p = props[0] if props else {}
    prop = f"{p.get('siglaTipo', '')} {p.get('numero', '')}/{p.get('ano', '')}".strip() if p else ""
    ementa = p.get("ementa") or ((d.get("ultimaApresentacaoProposicao") or {}).get("descricao") or "")
    res = {1: "Aprovada", 0: "Rejeitada"}.get(d.get("aprovacao"), "")
    return [{"casa": "Câmara", "votacao_id": vid, "data": (d.get("dataHoraRegistro") or d.get("data") or "")[:10],
             "proposicao": prop or "(sem proposição)", "tipo": p.get("siglaTipo", ""), "ementa": str(ementa)[:400],
             "descricao": str(d.get("descricao") or "")[:400], "resultado": res,
             "parlamentar_id": str((v.get("deputado_") or {}).get("id", "")), "voto": v.get("tipoVoto", "")}
            for v in vs]


def camara(anos: list[int], log=print) -> pd.DataFrame:
    ids = []
    for a in anos:
        for m in range(1, 13):
            ids += _votacoes_do_mes(a, m)
    ids = list(dict.fromkeys(ids))
    log(f"  Câmara: {len(ids)} votações no plenário; baixando votos nominais (cache)...")
    with ThreadPoolExecutor(6) as ex:
        linhas = [r for lote in ex.map(_votacao_camara, ids) for r in lote]
    return pd.DataFrame(linhas, columns=COLS)


# ----------------------------------------------------------------------------- Senado
def _senador(cod: str, ano: int) -> list[dict]:
    atual = ano >= dt.date.today().year
    js = _cache(f"sf_{cod}_{ano}.json", f"{SENADO}/senador/{cod}/votacoes.json", {"ano": ano}, sempre=atual)
    linhas = []
    for v in _lista(_achar(js, "Votacao")):
        if not isinstance(v, dict):
            continue
        m = v.get("IdentificacaoMateria") or v.get("Materia") or {}
        prop = m.get("DescricaoIdentificacaoMateria") or \
            f"{m.get('SiglaSubtipoMateria', '')} {m.get('NumeroMateria', '')}/{m.get('AnoMateria', '')}".strip()
        sess = v.get("SessaoPlenaria") or {}
        linhas.append({"casa": "Senado", "votacao_id": str(v.get("CodigoSessaoVotacao") or v.get("CodigoVotacao") or ""),
                       "data": str(sess.get("DataSessao") or v.get("DataSessao") or "")[:10],
                       "proposicao": prop or "(sem matéria)", "tipo": m.get("SiglaSubtipoMateria", ""),
                       "ementa": str(m.get("EmentaMateria") or "")[:400],
                       "descricao": str(v.get("DescricaoVotacao") or "")[:400],
                       "resultado": str(v.get("DescricaoResultado") or ""),
                       "parlamentar_id": str(cod), "voto": str(v.get("SiglaDescricaoVoto") or v.get("DescricaoVoto") or "")})
    return linhas


def senado(cods: list[str], anos: list[int], log=print) -> pd.DataFrame:
    tarefas = [(c, a) for c in cods for a in anos]
    log(f"  Senado: votos de {len(cods)} senadores...")
    with ThreadPoolExecutor(6) as ex:
        linhas = [r for lote in ex.map(lambda t: _senador(*t), tarefas) for r in lote]
    return pd.DataFrame(linhas, columns=COLS)


def coletar(anos: list[int], ids_externos: pd.DataFrame, log=print) -> pd.DataFrame:
    partes = []
    try:
        partes.append(camara(anos, log))
    except Exception as e:  # noqa: BLE001
        log(f"  Câmara votações: falha ({e})")
    cods = sorted({i[3:] for i in ids_externos.get("id_origem", pd.Series(dtype=str)) if str(i).startswith("SF-") and str(i)[3:].isdigit()})
    if cods:
        try:
            partes.append(senado(cods, anos, log))
        except Exception as e:  # noqa: BLE001
            log(f"  Senado votações: falha ({e})")
    df = pd.concat([p for p in partes if len(p)], ignore_index=True) if any(len(p) for p in partes) else pd.DataFrame(columns=COLS)
    if len(df):
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        df = df.drop_duplicates(["casa", "votacao_id", "parlamentar_id"])
    log(f"  Votações: {df['votacao_id'].nunique() if len(df) else 0} votações nominais · {len(df):,} votos".replace(",", "."))
    return df
