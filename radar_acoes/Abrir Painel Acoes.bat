@echo off
REM Abre o painel do Radar de Acoes no navegador.
cd /d "%~dp0"
python -m streamlit run app.py
