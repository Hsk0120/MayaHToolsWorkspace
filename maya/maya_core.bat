@echo off

::----------------------------------------------------------------
::Move Current Directory
::----------------------------------------------------------------
CD /d %~dp0

::----------------------------------------------------------------
::Args
::----------------------------------------------------------------
SET MAYA_VERSION=%1
SET MAYA_UI_LANGUAGE=%2
SET OPEN_FILE=%3
SET MEL=%4
SET PYTHON_SCRIPT=%5

SET MAYA_EXE="C:\Program Files\Autodesk\Maya%MAYA_VERSION%\bin\maya.exe"

::----------------------------------------------------------------
::General
::----------------------------------------------------------------
SET PATH_BAT=%~DP0
SET MAYA_DISABLE_CIP=1
SET MAYA_FORCE_PANEL_FOCUS=0
SET MAYA_SHOW_OUTPUT_WINDOW=1

::----------------------------------------------------------------
::Set Maya.env directory
::----------------------------------------------------------------
SET MAYA_ENV_DIR=%USERPROFILE%\Documents\maya\%MAYA_VERSION%
SET MAYA_ENV_FILE=%MAYA_ENV_DIR%\Maya.env
IF EXIST "%MAYA_ENV_FILE%" (
    FOR /F "usebackq eol=# tokens=* delims=" %%L IN ("%MAYA_ENV_FILE%") DO (
        IF NOT "%%L"=="" (
            FOR /F "tokens=1* delims==" %%A IN ("%%L") DO (
                SET "ENV_NAME=%%A"
                SET "ENV_VALUE=%%B"
                CALL SET "ENV_VALUE=%%ENV_VALUE:$=%%%"
                CALL SET "%%ENV_NAME%%=%%ENV_VALUE%%"
                ECHO Loaded ENV: %%A=%%B
            )
        )
    )
)

::---------------------------------------------------
::MEL Tools
::---------------------------------------------------
SET MAYA_MEL_1=%PATH_BAT%inhouse\mel;
SET MAYA_MEL_2=%PATH_BAT%package\mel;
SET MAYA_SCRIPT_PATH=%MAYA_MEL_1%%MAYA_MEL_2%;%MAYA_SCRIPT_PATH%

::----------------------------------------------------------------
::Python Tools
::----------------------------------------------------------------
SET PATH_INHOUSE=%PATH_BAT%inhouse;
SET PATH_USERSETUP=%PATH_BAT%inhouse\HTools;
SET PYTHONPATH=%PATH_INHOUSE%;%PATH_USERSETUP%;%PYTHONPATH%

::----------------------------------------------------------------
::Plugin Tools
::----------------------------------------------------------------
SET PATH_PLUGIN=%PATH_BAT%inhouse\plugin;
SET MAYA_PLUG_IN_PATH=%PATH_PLUGIN%;%MAYA_PLUG_IN_PATH%

::----------------------------------------------------------------
::Maya Modules
::----------------------------------------------------------------
SET MAYA_MODULE_PATH=%PATH_BAT%modules;%MAYA_MODULE_PATH%

::----------------------------------------------------------------
::Slack
::----------------------------------------------------------------
IF "%SLACK_API_BOT_TOKEN%" == "" (
    ECHO [WARN] SLACK_API_BOT_TOKEN is not set. Slack notifications will be disabled.
)

::----------------------------------------------------------------
::Install PIP and Packages
::----------------------------------------------------------------
::CALL %PATH_BAT%site-packages\install_pip.bat

::----------------------------------------------------------------
::Run MayaBatch
::----------------------------------------------------------------
IF NOT {%MAYA_EXE:mayabatch.exe=%} == {%MAYA_EXE%} (
    START /WAIT "" %MAYA_EXE% -file %OPEN_FILE% -script %MEL% -log "%PATH_BAT%mayabatch.log"
    EXIT
)

::----------------------------------------------------------------
::Run MayaPy
::----------------------------------------------------------------
IF NOT {%MAYA_EXE:mayapy.exe=%} == {%MAYA_EXE%} (
    CALL %MAYA_EXE% %PYTHON_SCRIPT%
    EXIT
)

::----------------------------------------------------------------
::Run Maya
::----------------------------------------------------------------
if "%OPEN_FILE%" == "" ( 
    START "" %MAYA_EXE% -hideConsole
) else (ff
    START "" %MAYA_EXE% -hideConsole -file %OPEN_FILE%
)
EXIT
