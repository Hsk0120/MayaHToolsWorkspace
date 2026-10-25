@echo off
setlocal

set "MLIB_DOCS_PYTHON=%~dp0.venv\Scripts\python.exe"
set "MLIB_DOCS_SOURCE=%~dp0source"
set "MLIB_DOCS_OUTPUT=%~dp0_build\html"
set "MLIB_DOCS_RESULT=1"

if not exist "%MLIB_DOCS_PYTHON%" (
    echo Documentation Python environment was not found.
    echo Run "%~dp0setup.bat" first. See README.md for details.
    goto finish
)

rem Sphinx never deletes files from an existing output folder, so files that
rem were removed from the sources (for example old _static assets) would stay
rem in the build. Start every rebuild from an empty output folder.
if exist "%MLIB_DOCS_OUTPUT%" rmdir /s /q "%MLIB_DOCS_OUTPUT%"
if exist "%MLIB_DOCS_OUTPUT%" (
    echo Could not remove the previous build output: "%MLIB_DOCS_OUTPUT%"
    echo Close programs that are using files in it, then run this again.
    goto finish
)

"%MLIB_DOCS_PYTHON%" -m sphinx -E -a -b html -W --keep-going "%MLIB_DOCS_SOURCE%" "%MLIB_DOCS_OUTPUT%"
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
