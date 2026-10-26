@echo off
REM Abre o painel AURUM no navegador (http://localhost:8501).
REM Deixe esta janela aberta enquanto usa o painel: fechar = desligar o painel.
cd /d "%~dp0"
title AURUM - painel

python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [ERRO] Python nao encontrado.
  echo  Instale em https://www.python.org/downloads/ e marque "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

python -c "import streamlit, yfinance, altair" >nul 2>&1
if errorlevel 1 (
  echo  Primeira vez: instalando os componentes do sistema. Aguarde alguns minutos...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo  [ERRO] Nao consegui instalar. Tire um print desta janela e mande para o suporte.
    pause
    exit /b 1
  )
)

echo.
echo  ============================================================
echo   AURUM ligando... o navegador abre sozinho em alguns segundos.
echo   Endereco: http://localhost:8501
echo   NAO FECHE esta janela enquanto estiver usando o painel.
echo  ============================================================
echo.
python -m streamlit run app.py --server.port 8501
echo.
echo  O painel foi encerrado. Se apareceu algum erro acima, tire um print.
pause
