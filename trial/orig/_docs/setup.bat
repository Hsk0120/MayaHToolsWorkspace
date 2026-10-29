@echo off
setlocal

set "MLIB_DOCS_ENV=%~dp0.venv"
set "MLIB_DOCS_PYTHON=%~dp0.venv\Scripts\python.exe"
set "MLIB_DOCS_RESULT=1"

rem Reuse an existing environment. Do not replace a broken one automatically.
if exist "%MLIB_DOCS_ENV%" goto existing_environment

rem Prefer the Windows Python launcher, then Python available on PATH.
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv "%MLIB_DOCS_ENV%"
    if errorlevel 1 goto create_failed
    goto install
)
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    python -m venv "%MLIB_DOCS_ENV%"
    if errorlevel 1 goto create_failed
    goto install
)
echo Python 3.11 or newer was not found.
echo Install Python for Windows, then run this batch again.
echo See "%~dp0README.md" for the download link and setup steps.
goto finish

:existing_environment
if exist "%MLIB_DOCS_PYTHON%" goto install
echo The existing .venv does not contain Scripts\python.exe.
echo It was left unchanged. See the troubleshooting section in README.md.
goto finish

:install
"%MLIB_DOCS_PYTHON%" -c "import sys; print(sys.version); sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 (
    echo The existing .venv requires Python 3.11 or newer.
    echo See the troubleshooting section in README.md.
    goto finish
)

"%MLIB_DOCS_PYTHON%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo Dependency installation failed. Check the messages and network connection.
    goto finish
)
"%MLIB_DOCS_PYTHON%" -m pip check
if errorlevel 1 goto finish
"%MLIB_DOCS_PYTHON%" -m sphinx --version
if errorlevel 1 goto finish
"%MLIB_DOCS_PYTHON%" -c "import autoapi; from importlib.metadata import version; print('sphinx-autoapi: ' + version('sphinx-autoapi'))"
if errorlevel 1 goto finish

set "MLIB_DOCS_RESULT=0"
echo.
echo Documentation setup succeeded.
echo Next, run "%~dp0rebuild.bat" to build the HTML pages.
goto finish

:create_failed
echo Could not create the documentation Python environment.
echo Check the messages above and the troubleshooting section in README.md.

:finish
echo.
if /I not "%~1"=="--no-pause" pause
exit /b %MLIB_DOCS_RESULT%
