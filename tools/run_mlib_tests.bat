@echo off
setlocal
if defined MLIB_TEST_PYTHON goto run
for %%V in (2022 2023 2024 2025 2026 2027) do (
    if exist "%ProgramFiles%\Autodesk\Maya%%V\bin\mayapy.exe" set "MLIB_TEST_PYTHON=%ProgramFiles%\Autodesk\Maya%%V\bin\mayapy.exe"
)
if defined MLIB_TEST_PYTHON goto run
echo Python 3.7+ executable is required. Set MLIB_TEST_PYTHON.
exit /b 2
:run
"%MLIB_TEST_PYTHON%" "%~dp0run_mlib_tests.py" %*
exit /b %errorlevel%
