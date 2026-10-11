@echo off
setlocal
set "QT_QPA_PLATFORM_PLUGIN_PATH=C:\Program Files\Autodesk\Maya2027\plugins\platforms"
"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" "%~dp0python\quickPathExplorer.py" %*
