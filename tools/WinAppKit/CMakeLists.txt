# WinAppKit: Windowsアプリ(FramePlayerなど)を配布するための汎用の道具。
# 今はアイコン作成(IconBuilder)だけ。インストーラーも、ここに足していく予定。
# Windows標準の機能だけを使い、外部ライブラリには依存しない。
cmake_minimum_required(VERSION 3.20)
project(WinAppKit LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# 配布先にVisual C++ ランタイムを入れなくて済むよう、ランタイムを静的リンクする。
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_compile_options(/utf-8 /W4)

# SVGで描いたアイコンから .ico を作る。
add_executable(IconBuilder src/IconBuilder.cpp)
target_compile_definitions(IconBuilder PRIVATE UNICODE _UNICODE NOMINMAX)
target_link_libraries(IconBuilder PRIVATE d2d1 windowscodecs shlwapi ole32)
