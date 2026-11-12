@echo off
setlocal

set "MLIB_DOCS_PYTHON=%~dp0.venv\Scripts\python.exe"
set "MLIB_DOCS_SOURCE=%~dp0source"
set "MLIB_DOCS_OUTPUT=%~dp0_build\html"
set "MLIB_DOCS_MAYAPY_FILE=%~dp0.mayapy-site\mayapy-path.txt"
set "MLIB_DOCS_RESULT=1"

if exist "%MLIB_DOCS_PYTHON%" goto clean
rem setup.bat used mayapy when no Python was found: run Sphinx with the same
rem mayapy and the packages it installed into .mayapy-site.
if exist "%MLIB_DOCS_MAYAPY_FILE%" set /p MLIB_DOCS_PYTHON=<"%MLIB_DOCS_MAYAPY_FILE%"
if not exist "%MLIB_DOCS_PYTHON%" (
    echo Documentation Python environment was not found.
    echo Run "%~dp0setup.bat" first. See README.md for details.
    goto finish
)
set "PYTHONNOUSERSITE=1"
set "PYTHONPATH=%~dp0.mayapy-site"

:clean
rem Sphinx never deletes files from an existing output folder, so files that
rem were removed from the sources (for example old _static assets) would stay
rem in the build. Start every rebuild from an empty output folder.
if exist "%MLIB_DOCS_OUTPUT%" rmdir /s /q "%MLIB_DOCS_OUTPUT%"
if exist "%MLIB_DOCS_OUTPUT%" (
    echo Could not remove the previous build output: "%MLIB_DOCS_OUTPUT%"
    echo Close programs that are using files in it, then run this again.
    goto finish
)

rem -n reports cross references that do not resolve (nitpick_ignore_regex in conf.py lists the allowed ones).
"%MLIB_DOCS_PYTHON%" -m sphinx -E -a -b html -n -W --keep-going "%MLIB_DOCS_SOURCE%" "%MLIB_DOCS_OUTPUT%"
set "MLIB_DOCS_RESULT=%ERRORLEVEL%"
if not "%MLIB_DOCS_RESULT%"=="0" (
    echo.
    echo Documentation build failed. Check the messages above.
    goto finish
)

echo.
echo Documentation build succeeded.
echo Open: "%MLIB_DOCS_OUTPUT%\index.html"

:finish
echo.
if /I not "%~1"=="--no-pause" pause
exit /b %MLIB_DOCS_RESULT%
