@echo off
REM Liga o agente JARVIS: vigia o pregao a cada 30 min e faz a apuracao completa as 18h30.
REM Deixe esta janela aberta (ou agende no Agendador de Tarefas para iniciar com o Windows).
cd /d "%~dp0"
python agente.py
pause
