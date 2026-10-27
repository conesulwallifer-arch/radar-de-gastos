@echo off
REM Atualiza o AURUM para a versao mais nova do GitHub, mantendo os seus dados (dados_acoes) e o config.env.
title AURUM - atualizar
cd /d "%~dp0"
set PASTA=%TEMP%\aurum_atualizacao
echo.
echo  Baixando a versao mais nova do AURUM...
if exist "%PASTA%" rmdir /s /q "%PASTA%"
mkdir "%PASTA%"
curl -L -s -f -o "%PASTA%\aurum.zip" https://github.com/conesulwallifer-arch/radar-de-gastos/archive/refs/heads/claude/tender-ritchie-x701ww.zip
if errorlevel 1 (
  echo  [ERRO] Nao consegui baixar. Confira a internet e tente de novo.
  pause
  exit /b 1
)
tar -xf "%PASTA%\aurum.zip" -C "%PASTA%"
if not exist "%PASTA%\radar-de-gastos-claude-tender-ritchie-x701ww\radar_acoes\app.py" (
  echo  [ERRO] O arquivo baixado veio incompleto. Tente de novo.
  pause
  exit /b 1
)

set EQUIPE=0
for /f %%a in ('python -c "import segundo_plano as s; print(int(s.ligada()[0]))" 2^>nul') do set EQUIPE=%%a
echo  Desligando o painel e a equipe para trocar os arquivos...
call "Fechar Painel.bat" >nul 2>&1
if "%EQUIPE%"=="1" python segundo_plano.py desligar >nul 2>&1

echo  Copiando os arquivos novos (seus dados ficam como estao)...
robocopy "%PASTA%\radar-de-gastos-claude-tender-ritchie-x701ww\radar_acoes" "%~dp0." /E /NFL /NDL /NJH /NJS /NP /XD dados_acoes /XF config.env "Atualizar AURUM.bat" >nul
if errorlevel 8 (
  echo  [ERRO] Falha ao copiar os arquivos. Feche janelas do AURUM abertas e tente de novo.
  pause
  exit /b 1
)
echo  Conferindo os componentes...
python -m pip install -q -r requirements.txt
if errorlevel 1 echo  [aviso] Nao consegui atualizar algum componente; o AURUM deve funcionar mesmo assim. Se der erro, me mande um print.
copy /y "%PASTA%\radar-de-gastos-claude-tender-ritchie-x701ww\radar_acoes\Atualizar AURUM.bat" "%~dp0Atualizar AURUM.novo.bat" >nul 2>&1

if "%EQUIPE%"=="1" (
  echo  Religando a Equipe 24h...
  python segundo_plano.py ligar >nul 2>&1
)
rmdir /s /q "%PASTA%" >nul 2>&1
REM o proprio atualizador e trocado por ultimo, depois que esta janela fechar (um .bat nao pode se sobrescrever enquanto roda)
if exist "%~dp0Atualizar AURUM.novo.bat" start "" /min cmd /c "timeout /t 12 >nul & move /y "%~dp0Atualizar AURUM.novo.bat" "%~dp0Atualizar AURUM.bat" >nul"
echo.
echo  ===============================================
echo   AURUM atualizado! Abrindo o painel...
echo  ===============================================
start "" "Abrir Painel (sem janela).vbs"
timeout /t 6 >nul 2>&1
exit /b 0
