@echo off
REM ============================================
REM  IELTS Review - Java LocalServer launcher
REM  Usage: run.bat [port]   default port 21001
REM ============================================
setlocal
set ROOT=%~dp0
java -cp "%ROOT%out;%ROOT%lib\*" com.ielts.reminder.server.Main %1
if errorlevel 1 (
  echo.
  echo [ERROR] Java server exited. Check that java 11+ is installed.
  pause
)
endlocal
