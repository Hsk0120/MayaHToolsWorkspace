@echo off
setlocal

rem FramePlayer ドキュメントを .venv の Python で作り直す。手順は README.md を参照。
set "FRAMEPLAYER_DOCS_PYTHON=%~dp0.venv\Scripts\python.exe"
set "FRAMEPLAYER_DOCS_OUTPUT=%~dp0_build\html"
set "FRAMEPLAYER_DOCS_RESULT=1"

if not exist "%FRAMEPLAYER_DOCS_PYTHON%" (
    echo Documentation Python environment was not found.
    echo Follow the setup instructions in "%~dp0README.md" first.
    goto finish
)

rem Sphinx は出力先の古いファイルを削除しないため、毎回空の状態から作り直す。
if exist "%FRAMEPLAYER_DOCS_OUTPUT%" rmdir /s /q "%FRAMEPLAYER_DOCS_OUTPUT%"

"%FRAMEPLAYER_DOCS_PYTHON%" -m sphinx -E -a -b html -W --keep-going "%~dp0." "%FRAMEPLAYER_DOCS_OUTPUT%"
set "FRAMEPLAYER_DOCS_RESULT=%ERRORLEVEL%"
if not "%FRAMEPLAYER_DOCS_RESULT%"=="0" (
    echo.
    echo Documentation build failed. Check the messages above.
    goto finish
)

echo.
echo Documentation build succeeded.
echo Open: "%FRAMEPLAYER_DOCS_OUTPUT%\index.html"

:finish
echo.
if /I not "%~1"=="--no-pause" pause
exit /b %FRAMEPLAYER_DOCS_RESULT%
