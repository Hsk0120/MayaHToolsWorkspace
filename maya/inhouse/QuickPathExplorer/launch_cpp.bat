@echo off
setlocal
set "PATH=C:\Program Files\Autodesk\Maya2027\bin;%PATH%"
set "QT_QPA_PLATFORM_PLUGIN_PATH=C:\Program Files\Autodesk\Maya2027\plugins\platforms"
"%~dp0..\..\..\.maya-output\plugin-build\QuickPathExplorer\2027\Release\QuickPathExplorer.exe" %*
