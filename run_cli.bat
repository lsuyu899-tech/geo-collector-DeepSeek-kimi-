@echo off
setlocal
cd /d "%~dp0"

python --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found.
  pause
  exit /b 1
)

set "INPUT_FILE=questions.csv"
set /p INPUT_FILE=Input file path [default: questions.csv]:
if "%INPUT_FILE%"=="" set "INPUT_FILE=questions.csv"

set "OUTPUT_FILE=results.csv"
set /p OUTPUT_FILE=Output file path [default: results.csv]:
if "%OUTPUT_FILE%"=="" set "OUTPUT_FILE=results.csv"

echo.
echo Paste API keys below. If already set in system env, press Enter to skip.
set /p MOONSHOT_API_KEY=MOONSHOT_API_KEY:
set /p ARK_API_KEY=ARK_API_KEY:
set /p ARK_MODEL=ARK_MODEL (Doubao model/endpoint, e.g. ep-xxxx):
set /p DEEPSEEK_API_KEY=DEEPSEEK_API_KEY (optional):

if not "%MOONSHOT_API_KEY%"=="" set "MOONSHOT_API_KEY=%MOONSHOT_API_KEY%"
if not "%ARK_API_KEY%"=="" set "ARK_API_KEY=%ARK_API_KEY%"
if not "%ARK_MODEL%"=="" set "ARK_MODEL=%ARK_MODEL%"
if not "%DEEPSEEK_API_KEY%"=="" set "DEEPSEEK_API_KEY=%DEEPSEEK_API_KEY%"

set "KIMI_MODEL=kimi-k2.5"
set /p KIMI_MODEL=Kimi model [default: kimi-k2.5]:
if "%KIMI_MODEL%"=="" set "KIMI_MODEL=kimi-k2.5"

set "DEEPSEEK_MODE=api"
set /p DEEPSEEK_MODE=DeepSeek mode [skip/api, default: api]:
if "%DEEPSEEK_MODE%"=="" set "DEEPSEEK_MODE=api"

set "PROVIDERS=kimi,doubao,deepseek"
set /p PROVIDERS=Providers [default: kimi,doubao,deepseek]:
if "%PROVIDERS%"=="" set "PROVIDERS=kimi,doubao,deepseek"

set "WORKERS=2"
set /p WORKERS=Workers [default: 2]:
if "%WORKERS%"=="" set "WORKERS=2"

echo.
echo Running...
python ".\collector.py" ^
  --input "%INPUT_FILE%" ^
  --output "%OUTPUT_FILE%" ^
  --question-column question ^
  --providers %PROVIDERS% ^
  --deepseek-mode %DEEPSEEK_MODE% ^
  --workers %WORKERS% ^
  --kimi-model %KIMI_MODEL% ^
  --resume

echo.
echo Done. Output: %OUTPUT_FILE%
pause
endlocal
