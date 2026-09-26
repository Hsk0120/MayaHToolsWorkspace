@echo off
setlocal

set "HLIB_DOCS_PYTHON=%~dp0.venv\Scripts\python.exe"
set "HLIB_DOCS_OUTPUT=%~dp0_build\html"
set "HLIB_DOCS_RESULT=1"

if not exist "%HLIB_DOCS_PYTHON%" (
    echo Documentation Python environment was not found.
    echo Follow the setup instructions in "%~dp0README.md" first.
    goto finish
)

rem Sphinx never deletes files from an existing output folder, so files that
rem were removed from the sources (for example old _static assets) would stay
rem in the build. Start every rebuild from an empty output folder.
if exist "%HLIB_DOCS_OUTPUT%" rmdir /s /q "%HLIB_DOCS_OUTPUT%"
if exist "%HLIB_DOCS_OUTPUT%" (
    echo Could not remove the previous build output: "%HLIB_DOCS_OUTPUT%"
    echo Close programs that are using files in it, then run this again.
    goto finish
)

"%HLIB_DOCS_PYTHON%" -m sphinx -E -a -b html -W --keep-going "%~dp0." "%HLIB_DOCS_OUTPUT%"
set "HLIB_DOCS_RESULT=%ERRORLEVEL%"
if not "%HLIB_DOCS_RESULT%"=="0" (
    echo.
    echo Documentation build failed. Check the messages above.
    goto finish
)

echo.
echo Documentation build succeeded.
echo Open: "%HLIB_DOCS_OUTPUT%\index.html"

:finish
echo.
if /I not "%~1"=="--no-pause" pause
exit /b %HLIB_DOCS_RESULT%
