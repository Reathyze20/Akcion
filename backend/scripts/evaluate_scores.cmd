@echo off
rem ============================================================================
rem  Akcion - denni vyhodnoceni skore
rem ============================================================================
rem  Obalka pro scripts\evaluate_scores.py, na kterou miri uloha v Planovaci
rem  uloh (Task Scheduler). Duvody, proc obalka a ne primo python.exe:
rem
rem   1. LOG. Planovac ulozi jen navratovy kod. "Uloha probehla" a "uloha
rem      probehla a nic nezmerila" jsou dve ruzne veci a bez logu je
rem      nerozeznas.
rem   2. INTERPRET. Na PATH je jako prvni obcas obchodni zastupce python.exe
rem      z WindowsApps, ktery jen otevre Microsoft Store. Uloha by tise
rem      nedelala nic. Tady je cesta urcena napevno, s kontrolou.
rem   3. KODOVANI. PYTHONIOENCODING=utf-8 udrzi cestinu v logu citelnou.
rem
rem  Bez diakritiky zamerne: .cmd soubory cte cmd.exe v kodove strance 852
rem  a diakritika v nich dela nesmysly.
rem ============================================================================

setlocal

set "PYTHON=C:\Users\reath\AppData\Local\Programs\Python\Python312\python.exe"
rem %~dp0 je slozka teto obalky (scripts\), o uroven vys je backend.
rem Odvozene, ne napevno: presun projektu tak nerozbije ulohu.
for %%I in ("%~dp0..") do set "BACKEND=%%~fI"
set "LOGDIR=%BACKEND%\logs"
set "LOG=%LOGDIR%\evaluate_scores.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

rem Rotace pri 1 MB. Denni beh je par radku, takze se to stane jednou za roky,
rem ale log, ktery roste bez konce, je log, ktery nikdo neotevre.
if exist "%LOG%" for %%A in ("%LOG%") do if %%~zA GTR 1048576 move /y "%LOG%" "%LOG%.old" >nul

rem Zaloha pro pripad, ze se Python prestehuje (upgrade, reinstalace).
if not exist "%PYTHON%" set "PYTHON=C:\Users\reath\AppData\Local\Programs\Python\Launcher\py.exe -3"

echo.>> "%LOG%"
echo ===== %date% %time% =====>> "%LOG%"

set PYTHONIOENCODING=utf-8
%PYTHON% "%BACKEND%\scripts\evaluate_scores.py" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" echo [CHYBA] navratovy kod %RC%>> "%LOG%"

endlocal & exit /b %RC%
