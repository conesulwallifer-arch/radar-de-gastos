@echo off
REM Apuracao diaria do Radar de Acoes. Agende no "Agendador de Tarefas" do Windows (dias uteis, 19h).
cd /d "%~dp0"
python apurar.py
