@echo off
setlocal
rem Generate IDE files outside the source tree. Default Maya version: 2027.
set "MCE_MAYA_VERSION=%~1"
if not defined MCE_MAYA_VERSION set "MCE_MAYA_VERSION=2027"
set "MCE_PYTHON=%ProgramFiles%\Autodesk\Maya%MCE_MAYA_VERSION%\bin\mayapy.exe"
if not exist "%MCE_PYTHON%" (
    echo Maya Python was not found: "%MCE_PYTHON%"
    exit /b 2
)
"%MCE_PYTHON%" "%~dp0..\..\..\tools\build_maya_plugin.py" "%~dp0." --versions %MCE_MAYA_VERSION% --generate-only
exit /b %errorlevel%
