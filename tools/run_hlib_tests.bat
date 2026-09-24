@echo off
setlocal
if defined HLIB_TEST_PYTHON goto run
for %%V in (2022 2023 2024 2025 2026 2027) do (
    if exist "%ProgramFiles%\Autodesk\Maya%%V\bin\mayapy.exe" set "HLIB_TEST_PYTHON=%ProgramFiles%\Autodesk\Maya%%V\bin\mayapy.exe"
)
if defined HLIB_TEST_PYTHON goto run
echo Python 3.7+ executable is required. Set HLIB_TEST_PYTHON.
exit /b 2
:run
"%HLIB_TEST_PYTHON%" "%~dp0run_hlib_tests.py" %*
exit /b %errorlevel%
