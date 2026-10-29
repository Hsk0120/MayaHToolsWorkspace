@echo off
setlocal

::----------------------------------------------------------------
:: Generate the mlib type stubs (*.pyi next to each maya\inhouse\mlib\*.py)
:: for VS Code (Pylance) completion and signature help, from the docstrings.
:: The .py sources are not changed. Commit the updated .pyi with the .py.
::
::   generate_mlib_stubs.bat            regenerate the stubs
::   generate_mlib_stubs.bat --report   also list annotations left out
::   generate_mlib_stubs.bat --check    only check that the stubs are current
::
:: Needs Python 3.9 or later: py -3, python, or mayapy of Maya 2027-2025.
::----------------------------------------------------------------
SET "SCRIPT=%~dp0generate_mlib_stubs.py"

WHERE py >NUL 2>&1 && (py -3 "%SCRIPT%" %* & GOTO :done)
WHERE python >NUL 2>&1 && (python "%SCRIPT%" %* & GOTO :done)
FOR %%V IN (2027 2026 2025) DO (
    IF EXIST "C:\Program Files\Autodesk\Maya%%V\bin\mayapy.exe" (
        "C:\Program Files\Autodesk\Maya%%V\bin\mayapy.exe" "%SCRIPT%" %*
        GOTO :done
    )
)
ECHO [ERROR] Python 3.9 or later was not found.
EXIT /b 2

:done
EXIT /b %ERRORLEVEL%
