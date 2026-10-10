@echo off
REM ============================================
REM  雅思单词悬浮记忆工具 - Java 服务层构建脚本
REM  用法: build.bat   (编译到 out/ 目录)
REM ============================================
setlocal
set ROOT=%~dp0
if not exist "%ROOT%out" mkdir "%ROOT%out"
javac -encoding UTF-8 -cp "%ROOT%lib\*" -d "%ROOT%out" ^
  "%ROOT%src\main\java\com\ielts\reminder\config\*.java" ^
  "%ROOT%src\main\java\com\ielts\reminder\data\*.java" ^
  "%ROOT%src\main\java\com\ielts\reminder\api\*.java" ^
  "%ROOT%src\main\java\com\ielts\reminder\article\*.java" ^
  "%ROOT%src\main\java\com\ielts\reminder\server\*.java"
if errorlevel 1 (
  echo [ERROR] 编译失败，请检查 javac 是否在 PATH 中
  exit /b 1
)
echo [OK] 编译完成: out/
endlocal
