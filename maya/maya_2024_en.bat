@echo off

::----------------------------------------------------------------
::Move Current Directory
::----------------------------------------------------------------
CD /d %~dp0

:: This is Maya Core Settings Bat
SET MAYA_CORE = ./maya_core.bat

::----------------------------------------------------------------
::Startup Maya
::  Args:
::      MAYA_EXE = "C:\Program Files\Autodesk\Maya2022\bin\maya.exe" 
::      MAYA_UI_LANGUAGE = "en_US"
::      OPEN_FILE=%3
::      MEL=%4
::----------------------------------------------------------------

CALL MAYA_CORE 2024 en_US

EXIT