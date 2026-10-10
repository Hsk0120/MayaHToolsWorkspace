@echo off
setlocal EnableDelayedExpansion

::----------------------------------------------------------------
:: Install pip packages listed in requirements.txt into
:: site-packages\<Maya version>, using the mayapy of each version.
:: Only maya_core.bat adds that folder to PYTHONPATH.
::
::   install_packages.bat            all installed Maya versions
::   install_packages.bat 2026 2027  only the given versions
::
:: MAYA_INSTALL_ROOT overrides "C:\Program Files\Autodesk".
::----------------------------------------------------------------
CD /d %~dp0

IF "%MAYA_INSTALL_ROOT%" == "" SET "MAYA_INSTALL_ROOT=C:\Program Files\Autodesk"
SET "REQUIREMENTS=%~dp0requirements.txt"
SET "HELPER=%~dp0..\tools\install_maya_packages.py"

IF "%~1" == "" (
    SET "VERSIONS=2022 2023 2024 2025 2026 2027"
) ELSE (
    SET "VERSIONS=%*"
)

SET FOUND=0
SET FAILED=
FOR %%V IN (%VERSIONS%) DO (
    SET "MAYAPY=%MAYA_INSTALL_ROOT%\Maya%%V\bin\mayapy.exe"
    IF EXIST "!MAYAPY!" (
        SET FOUND=1
        ECHO.
        ECHO ==== Maya %%V ====
        "!MAYAPY!" "%HELPER%" --requirements "%REQUIREMENTS%" --target "%~dp0site-packages\%%V"
        IF ERRORLEVEL 1 SET "FAILED=!FAILED! %%V"
    ) ELSE (
        ECHO [SKIP] Maya %%V is not installed: !MAYAPY!
    )
)

ECHO.
SET RESULT=0
IF "%FOUND%" == "0" (
    ECHO [ERROR] No Maya was found under "%MAYA_INSTALL_ROOT%".
    SET RESULT=1
) ELSE IF NOT "%FAILED%" == "" (
    ECHO [ERROR] Failed for Maya:%FAILED%
    SET RESULT=1
) ELSE (
    ECHO Done.
)

:: Keep the window open when started by double-click
ECHO %CMDCMDLINE% | FIND /I "%~nx0" >NUL && PAUSE
EXIT /B %RESULT%
