@echo off
setlocal EnableDelayedExpansion

::----------------------------------------------------------------
:: Install pip package groups (requirements\<name>.txt) into
:: site-packages\<Maya version>\<name>, using the mayapy of each version.
:: modules\pip_<name>.mod puts a group on PYTHONPATH; a disabled .mod is
:: created in modules_disabled for a group that has none.
::
::   install_packages.bat                    all groups, all installed Maya versions
::   install_packages.bat 2026 2027          all groups, given versions
::   install_packages.bat 2026 scipy libigl  given groups, given versions
::
:: Numbers are Maya versions, other words are group names.
:: MAYA_INSTALL_ROOT overrides "C:\Program Files\Autodesk".
::----------------------------------------------------------------
CD /d %~dp0

IF "%MAYA_INSTALL_ROOT%" == "" SET "MAYA_INSTALL_ROOT=C:\Program Files\Autodesk"
SET "HELPER=%~dp0..\tools\install_maya_packages.py"

SET "VERSIONS="
SET "GROUPS="
FOR %%A IN (%*) DO (
    ECHO %%A| FINDSTR /R "^[0-9][0-9]*$" >NUL && (SET "VERSIONS=!VERSIONS! %%A") || (SET "GROUPS=!GROUPS! %%A")
)
IF "%VERSIONS%" == "" SET "VERSIONS=2022 2023 2024 2025 2026 2027"

SET FOUND=0
SET FAILED=
FOR %%V IN (%VERSIONS%) DO (
    SET "MAYAPY=%MAYA_INSTALL_ROOT%\Maya%%V\bin\mayapy.exe"
    IF EXIST "!MAYAPY!" (
        SET FOUND=1
        ECHO.
        ECHO ==== Maya %%V ====
        "!MAYAPY!" "%HELPER%" --requirements-dir "%~dp0requirements" --target-root "%~dp0site-packages\%%V" --modules-dir "%~dp0modules" --disabled-modules-dir "%~dp0modules_disabled" --groups!GROUPS!
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
    ECHO [ERROR] Some groups failed for Maya:%FAILED%
    SET RESULT=1
) ELSE (
    ECHO Done.
)

:: Keep the window open when started by double-click
ECHO %CMDCMDLINE% | FIND /I "%~nx0" >NUL && PAUSE
EXIT /B %RESULT%
