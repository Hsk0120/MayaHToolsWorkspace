@echo off
setlocal
if exist "%~dp0QuickPathExplorer.exe" (
    "%~dp0QuickPathExplorer.exe" %*
    exit /b
)
if defined QPE_PYTHON (
    "%QPE_PYTHON%" "%~dp0python\quickPathExplorer.py" %*
    exit /b
)
python -c "import PySide6" >nul 2>&1
if not errorlevel 1 (
    set "QT_QPA_PLATFORM_PLUGIN_PATH="
    set "QT_PLUGIN_PATH="
    python "%~dp0python\quickPathExplorer.py" %*
    exit /b
)
for %%V in (2027 2026 2025 2024 2023 2022) do (
    if exist "C:\Program Files\Autodesk\Maya%%V\bin\mayapy.exe" (
        set "QT_QPA_PLATFORM_PLUGIN_PATH=C:\Program Files\Autodesk\Maya%%V\plugins\platforms"
        "C:\Program Files\Autodesk\Maya%%V\bin\mayapy.exe" "%~dp0python\quickPathExplorer.py" %*
        exit /b
    )
)
echo Install requirements.txt into your Python, or use the standalone build.
pause
