@echo off
echo ====================================
echo  AIOps Agent - Stop
echo ====================================
echo.

echo [1/2] Stopping app processes (9900/8006)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :9900 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8006 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo   done
echo.

echo [2/2] Stopping Docker containers (Milvus + Prometheus)...
docker stop milvus-etcd milvus-minio milvus-standalone milvus-attu prometheus >nul 2>&1
echo   done
echo.

echo ====================================
echo  Stopped! Data kept in volumes/, restored on next start
echo ====================================
pause


