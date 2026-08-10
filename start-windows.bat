@echo off
setlocal enabledelayedexpansion

echo ====================================
echo  AIOps Agent - One-Click Start
echo ====================================
echo.

REM [1/6] Check venv
echo [1/6] Checking venv...
if not exist .venv\Scripts\python.exe (
    echo   [info] Creating venv...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -e . -q
    echo   [ok] venv created
) else (
    echo   [ok] venv ready
)
set PYTHON_CMD=.venv\Scripts\python.exe
echo.

REM [2/6] Docker containers (Milvus + Prometheus)
echo [2/6] Starting Docker containers...
docker start milvus-etcd milvus-minio milvus-standalone milvus-attu prometheus >nul 2>&1
if errorlevel 1 (
    echo   [warn] Some containers missing, trying compose...
    docker compose -f vector-database.yml up -d >nul 2>&1
    docker start prometheus >nul 2>&1
)
echo   [info] Waiting for Milvus healthy (max 2 min)...
set /a tries=0
:wait_milvus
set /a tries+=1
set MH=
for /f "tokens=*" %%s in ('docker inspect --format "{{.State.Health.Status}}" milvus-standalone 2^>nul') do set MH=%%s
if "!MH!"=="healthy" goto milvus_ok
if !tries! GEQ 24 (
    echo   [warn] Milvus not healthy yet, continuing...
    goto milvus_ok
)
timeout /t 5 /nobreak >nul
goto wait_milvus
:milvus_ok
echo   [ok] Milvus ready
echo.

REM [3/6] Ollama check
echo [3/6] Checking Ollama (:11434)...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo   [warn] Ollama NOT running! Please start Ollama manually
) else (
    echo   [ok] Ollama online
)
echo.

REM [4/6] LLM Gateway (:8006, skip if already running)
echo [4/6] Starting LLM Gateway (:8006)...
netstat -ano | findstr :8006 | findstr LISTENING >nul 2>&1
if errorlevel 1 (
    start "LLM Gateway" /min %PYTHON_CMD% llm_gateway.py
    echo   [ok] Gateway started
) else (
    echo   [info] Gateway already running, skip
)
echo.

REM [5/6] FastAPI (:9900, skip if already running)
echo [5/6] Starting FastAPI (:9900)...
netstat -ano | findstr :9900 | findstr LISTENING >nul 2>&1
if errorlevel 1 (
    start "AIOpsAgent" /min %PYTHON_CMD% -m uvicorn app.main:app --host 0.0.0.0 --port 9900
    echo   [ok] FastAPI started
) else (
    echo   [info] FastAPI already running, skip
)
echo.

REM [6/6] Health check
echo [6/6] Health check (wait 8s)...
timeout /t 8 /nobreak >nul
echo.
curl -s http://localhost:9900/health
echo.
echo.
echo ====================================
echo  DONE!
echo  Web UI:      http://localhost:9900
echo  API Docs:    http://localhost:9900/docs
echo  Attu:        http://127.0.0.1:8000
echo  Stop:        stop-windows.bat
echo ====================================
pause



