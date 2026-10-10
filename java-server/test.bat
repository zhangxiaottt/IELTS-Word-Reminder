@echo off
REM ============================================
REM  雅思单词悬浮记忆工具 - Java 服务层测试脚本
REM  用法: test.bat   (编译并运行全部 JUnit 测试)
REM ============================================
setlocal
set ROOT=%~dp0
call "%ROOT%build.bat"
if errorlevel 1 exit /b 1
javac -encoding UTF-8 -cp "%ROOT%out;%ROOT%lib\*" -d "%ROOT%out" ^
  "%ROOT%src\test\java\com\ielts\reminder\*.java"
if errorlevel 1 (
  echo [ERROR] 测试代码编译失败
  exit /b 1
)
java -jar "%ROOT%lib\junit-platform-console-standalone-1.10.2.jar" ^
  --class-path "%ROOT%out;%ROOT%lib\*" --scan-class-path
endlocal
