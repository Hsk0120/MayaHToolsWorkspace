# FramePlayer: コマ送りと2本比較に特化したWindows専用の動画プレイヤー。
# Windows標準機能(Media Foundation / Win32 / GDI)だけを使い、外部ライブラリには依存しない。
cmake_minimum_required(VERSION 3.20)
project(FramePlayer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# 配布先にVisual C++ ランタイムを入れなくて済むよう、ランタイムを静的リンクする。
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

# 画面に依存しない読み込み処理。プレイヤー本体と確認用ツールで共有する。
add_library(frameplayer_core STATIC
    src/core/Clip.cpp
    src/core/FrameSource.cpp
    src/core/MediaFoundationSource.cpp
    src/core/Mp4SampleTable.cpp
)
target_include_directories(frameplayer_core PUBLIC src)
target_compile_definitions(frameplayer_core PUBLIC UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
target_compile_options(frameplayer_core PUBLIC /utf-8 /W4 /permissive-)
target_link_libraries(frameplayer_core PUBLIC mfplat mfreadwrite mfuuid ole32 d3d11)

add_executable(FramePlayer WIN32
    src/app/main.cpp
    src/app/PlayerWindow.cpp
)
target_link_libraries(FramePlayer PRIVATE frameplayer_core user32 gdi32 shell32 winmm)

# 配布用: `cmake --install build --config Release` でexeを release/ へコピーする(release/ はGit管理対象)。
# ビルドのたびに管理対象のexeが変わらないよう、コピーはインストールを実行したときだけ行う。
install(TARGETS FramePlayer RUNTIME DESTINATION "${CMAKE_CURRENT_SOURCE_DIR}/release")

# コマ番号が正確に読めているかを確かめる確認用ツール(配布対象外)。
add_executable(FramePlayerVerify tests/verify_frame_index.cpp)
target_link_libraries(FramePlayerVerify PRIVATE frameplayer_core)
