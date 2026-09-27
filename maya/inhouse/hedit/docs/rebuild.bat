@echo off
setlocal

rem hedit ドキュメントを .venv の Python で作り直す。手順は README.md を参照。
set "HEDIT_DOCS_PYTHON=%~dp0.venv\Scripts\python.exe"
set "HEDIT_DOCS_OUTPUT=%~dp0_build\html"
set "HEDIT_DOCS_RESULT=1"

if not exist "%HEDIT_DOCS_PYTHON%" (
    echo Documentation Python environment was not found.
    echo Follow the setup instructions in "%~dp0README.md" first.
    goto finish
)

rem Sphinx は出力先の古いファイルを削除しないため、毎回空の状態から作り直す。
if exist "%HEDIT_DOCS_OUTPUT%" rmdir /s /q "%HEDIT_DOCS_OUTPUT%"

"%HEDIT_DOCS_PYTHON%" -m sphinx -E -a -b html -W --keep-going "%~dp0." "%HEDIT_DOCS_OUTPUT%"
set "HEDIT_DOCS_RESULT=%ERRORLEVEL%"
if not "%HEDIT_DOCS_RESULT%"=="0" (
    echo.
    echo Documentation build failed. Check the messages above.
    goto finish
)

echo.
echo Documentation build succeeded.
echo Open: "%HEDIT_DOCS_OUTPUT%\index.html"

:finish
echo.
if /I not "%~1"=="--no-pause" pause
exit /b %HEDIT_DOCS_RESULT%
