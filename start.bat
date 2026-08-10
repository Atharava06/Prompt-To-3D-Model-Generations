@echo off
title Prompt-to-3D Launcher
echo ============================================
echo   Prompt-to-3D — Starting Backend + Frontend
echo ============================================
echo.

:: ── Backend ──────────────────────────────────────────────────────────────────
echo [1/2] Starting Backend (FastAPI on http://127.0.0.1:8000) ...
start "PT3 Backend" cmd /k "cd /d %~dp0PT3-backend && call venv\Scripts\activate && python run.py"

:: Give the server a moment to boot before the browser opens
timeout /t 3 /nobreak >nul

:: ── Frontend ─────────────────────────────────────────────────────────────────
echo [2/2] Starting Frontend (Vite on http://localhost:5173) ...
start "PT3 Frontend" cmd /k "cd /d %~dp0PT3-frontend && npm run dev"

echo.
echo Both servers are starting in separate windows.
echo   Backend  → http://127.0.0.1:8000
echo   Frontend → http://localhost:5173
echo.
echo Close those windows (or press Ctrl+C inside them) to stop.
pause
