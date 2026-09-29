"""Aba 📰 Novidades: tudo o que mudou, notas e contratos mais recentes, votações e notícias."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import noticias


def _tem(con, tabela: str) -> bool:
    return bool(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [tabela]).fetchone()[0])


def render(con, f: pd.DataFrame, ufs: list, muns: list, CURTO, BRL, tabela_notas, atualizado: str = ""):
    ids = f["politico_id"].tolist()
    st.caption(("Dados oficiais atualizados em **" + atualizado + "**. " if atualizado else "")
               + "Os filtros da barra lateral (UF, município, cargo) valem aqui também.")
    t_novo, t_notas, t_vot, t_not = st.tabs(["🆕 Desde a última atualização", "🧾 Notas e contratos mais recentes",
                                              "🗳️ Votações recentes", "📰 Notícias"])

    with t_novo:
        if not _tem(con, "novidades"):
            st.info("As novidades aparecem a partir da próxima atualização (o radar compara com a coleta anterior).")
        else:
            nv = con.execute("""SELECT n.*, p.nome, p.cargo, p.uf, p.municipio FROM novidades n
                                LEFT JOIN politicos p USING (politico_id)
                                WHERE n.quando = (SELECT max(quando) FROM novidades)""").df()
            nv = nv[nv["politico_id"].isin(ids)]
            quando = con.execute("SELECT max(quando) FROM novidades").fetchone()[0]
            if nv.empty:
                st.info("Nada novo para este filtro na última atualização.")
            else:
                c = nv.groupby("tipo")["valor"].agg(["size", "sum"])
                cols = st.columns(len(c))
                for col, (tipo, r) in zip(cols, c.iterrows()):
                    rot = {"Nota nova": "Notas novas", "Novo alerta": "Alertas novos", "Contrato novo": "Contratos novos"}.get(tipo, tipo)
                    col.metric(rot, f"{int(r['size']):,}".replace(",", "."),
                               CURTO(r["sum"]), delta_color="off")
                st.caption(f"Comparação entre a coleta de {pd.Timestamp(quando):%d/%m/%Y %H:%M} e a anterior.")
                nv = nv.sort_values(["tipo", "valor"], ascending=[True, False])
                nv["link"] = nv["url"].where(nv["url"].fillna("").str.startswith("http"), None)
                st.dataframe(nv[["tipo", "nome", "cargo", "municipio", "uf", "titulo", "detalhe", "valor", "data_ref", "link"]],
                             hide_index=True, width="stretch", column_config={
                                 "tipo": "Tipo", "nome": "Político / órgão", "cargo": "Cargo", "municipio": "Município",
                                 "uf": "UF", "titulo": st.column_config.TextColumn("O que", width="large"),
                                 "detalhe": st.column_config.TextColumn("Detalhe", width="large"),
                                 "valor": st.column_config.NumberColumn("Valor (R$)", format="localized"),
                                 "data_ref": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                 "link": st.column_config.LinkColumn("Documento", display_text="abrir")})

    with t_notas:
        dias = st.select_slider("Últimos", options=[7, 15, 30, 60, 90], value=30, format_func=lambda d: f"{d} dias", key="nv_dias")
        g = con.execute(f"""SELECT g.*, p.nome, p.cargo FROM gastos g JOIN politicos p USING (politico_id)
                            WHERE g.data >= current_date - INTERVAL {int(dias)} DAY AND g.data <= current_date
                            ORDER BY g.data DESC, g.valor DESC LIMIT 5000""").df()
        g = g[g["politico_id"].isin(ids)]
        if g.empty:
            st.info("Nenhum lançamento com data nesse intervalo para este filtro. As fontes oficiais publicam com atraso "
                    "(a cota parlamentar leva de dias a semanas; contratos, até 20 dias).")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Lançamentos", f"{len(g):,}".replace(",", "."))
            c2.metric("Valor", CURTO(g["valor"].sum()))
            c3.metric("Políticos / órgãos", g["politico_id"].nunique())
            g["fornecedor"] = g["nome"].str.title() + " → " + g["fornecedor"].fillna("")
            tabela_notas(g, key="nv_notas")

    with t_vot:
        if not _tem(con, "votos"):
            st.info("As votações aparecem depois de rodar o Atualizar Radar com a versão nova.")
        else:
            v = con.execute("""SELECT casa, votacao_id, data, proposicao, tipo, ementa, descricao, resultado,
                                      count(*) FILTER (WHERE voto ILIKE 'sim') sim,
                                      count(*) FILTER (WHERE voto ILIKE 'não' OR voto ILIKE 'nao') nao,
                                      count(*) total
                               FROM votos GROUP BY ALL ORDER BY data DESC LIMIT 400""").df()
            c1, c2 = st.columns([1, 2])
            so_pec = c1.checkbox("Só PECs (mudanças na Constituição)", key="nv_pec")
            busca = c2.text_input("Buscar tema (ex.: imposto, aposentadoria, salário)", key="nv_busca")
            if so_pec:
                v = v[v["tipo"].str.upper().eq("PEC") | v["proposicao"].str.upper().str.startswith("PEC")]
            if busca:
                alvo = v["ementa"].fillna("") + " " + v["descricao"].fillna("") + " " + v["proposicao"].fillna("")
                v = v[alvo.str.contains(busca, case=False, na=False)]
            st.caption("Clique numa votação para ver como votou cada parlamentar do filtro (UF) da barra lateral.")
            for r in v.head(40).itertuples():
                titulo = f"{pd.Timestamp(r.data):%d/%m/%Y} · {r.casa} · {r.proposicao} — {r.resultado or ''} (Sim {r.sim} × Não {r.nao})"
                with st.expander(titulo):
                    st.markdown(f"**O que foi votado:** {r.descricao or '—'}")
                    if r.ementa:
                        st.markdown(f"**Ementa:** {r.ementa}")
                    vv = con.execute("""SELECT v.voto, p.nome, p.partido, p.uf FROM votos v
                                        JOIN ids_externos i ON i.id_origem = (CASE WHEN v.casa = 'Câmara' THEN 'CD-' ELSE 'SF-' END) || v.parlamentar_id
                                        JOIN politicos p ON p.politico_id = i.politico_id
                                        WHERE v.casa = ? AND v.votacao_id = ?""", [r.casa, r.votacao_id]).df()
                    if ufs:
                        vv = vv[vv["uf"].isin(ufs)]
                    if vv.empty:
                        st.caption("Nenhum parlamentar do filtro atual nesta votação.")
                    else:
                        st.dataframe(vv.sort_values(["voto", "nome"]), hide_index=True, width="stretch",
                                     column_config={"voto": "Voto", "nome": "Parlamentar", "partido": "Partido", "uf": "UF"})

    with t_not:
        if muns:
            padrao = f"{muns[0].title()} prefeitura OR câmara municipal"
        elif ufs:
            padrao = f"deputados {ufs[0]} OR senadores {ufs[0]}"
        else:
            padrao = "Câmara dos Deputados OR Senado votação"
        termo = st.text_input("Buscar notícias sobre", value=padrao, key="nv_termo")
        noticias.mostrar(termo, 20)
