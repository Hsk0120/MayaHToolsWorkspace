@echo off
setlocal
rem Generate IDE files outside the source tree. Default Maya version: 2027.
set "HEDIT_MAYA_VERSION=%~1"
if not defined HEDIT_MAYA_VERSION set "HEDIT_MAYA_VERSION=2027"
set "HEDIT_PYTHON=%ProgramFiles%\Autodesk\Maya%HEDIT_MAYA_VERSION%\bin\mayapy.exe"
if not exist "%HEDIT_PYTHON%" (
    echo Maya Python was not found: "%HEDIT_PYTHON%"
    exit /b 2
)
"%HEDIT_PYTHON%" "%~dp0..\..\..\tools\build_maya_plugin.py" "%~dp0." --versions %HEDIT_MAYA_VERSION% --generate-only
exit /b %errorlevel%
