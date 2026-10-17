@echo off
rem One command: install, download models, build the web app, start the server. Safe to run again.
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv || goto :fail )
call .venv\Scripts\activate.bat
python -c "import locallens" 2>nul || (
  echo Installing Python packages...
  python -m pip install --quiet --upgrade pip
  pip install --quiet llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
  pip install --quiet -e ".[dev]" || goto :fail
)
if not exist models\qwen2.5-0.5b-instruct-q4_k_m.gguf (
  echo Downloading the models ^(one time, needs internet^)...
  python scripts\download_model.py || goto :fail
)
if not exist data\synthetic\orders.csv python scripts\make_synthetic_data.py
if not exist web\dist\index.html (
  where npm >nul 2>nul || ( echo Node.js is needed once to build the web app: https://nodejs.org & goto :fail )
  pushd web
  call npm ci --silent && call npm run build --silent
  popd
)
echo LocalLens is starting at http://127.0.0.1:8000
python -m locallens.server
goto :eof
:fail
echo Setup failed. See the message above.
exit /b 1
