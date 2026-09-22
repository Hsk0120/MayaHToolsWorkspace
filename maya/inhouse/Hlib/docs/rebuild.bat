@echo off
setlocal

set "HLIB_DOCS_PYTHON=%~dp0.venv\Scripts\python.exe"
set "HLIB_DOCS_RESULT=1"

if not exist "%HLIB_DOCS_PYTHON%" (
    echo Documentation Python environment was not found.
    echo Follow the setup instructions in "%~dp0README.md" first.
    goto finish
)

"%HLIB_DOCS_PYTHON%" -m sphinx -E -a -b html -W --keep-going "%~dp0." "%~dp0_build\html"
set "HLIB_DOCS_RESULT=%ERRORLEVEL%"
if not "%HLIB_DOCS_RESULT%"=="0" (
    echo.
    echo Documentation build failed. Check the messages above.
    goto finish
)

echo.
echo Documentation build succeeded.
echo Open: "%~dp0_build\html\index.html"

:finish
echo.
if /I not "%~1"=="--no-pause" pause
exit /b %HLIB_DOCS_RESULT%
