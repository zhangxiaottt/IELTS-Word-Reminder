@echo off
REM ============================================
REM  雅思单词悬浮记忆工具 - Java 服务层启动脚本
REM  用法: run.bat [port]   默认端口 21001
REM ============================================
setlocal
set ROOT=%~dp0
java -cp "%ROOT%out;%ROOT%lib\*" com.ielts.reminder.server.Main %1
endlocal
