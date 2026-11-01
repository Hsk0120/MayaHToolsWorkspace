@echo off
setlocal
pushd "%~dp0"
py -3.12 tools\build_cpp_windows.py --product --test --install-project %*
set "QPE_BUILD_RESULT=%ERRORLEVEL%"
popd
exit /b %QPE_BUILD_RESULT%
