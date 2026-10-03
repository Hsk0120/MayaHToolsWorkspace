# FramePlayer: コマ送りと2本比較に特化したWindows専用の動画プレイヤー。
# Windows標準機能(Media Foundation / Win32 / GDI)だけを使い、外部ライブラリには依存しない。
cmake_minimum_required(VERSION 3.20)
project(FramePlayer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# 配布先にVisual C++ ランタイムを入れなくて済むよう、ランタイムを静的リンクする。
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

# 映像のシェーダー(HLSL)は、Windows SDKのfxcでバイトコードの.hへ変換して埋め込む(実行時にコンパイルしない)。
set(FRAMEPLAYER_PROGRAM_FILES_X86 "ProgramFiles(x86)")
set(FRAMEPLAYER_SDK_BIN "$ENV{${FRAMEPLAYER_PROGRAM_FILES_X86}}/Windows Kits/10/bin")
file(GLOB FRAMEPLAYER_FXC_CANDIDATES "${FRAMEPLAYER_SDK_BIN}/*/x64/fxc.exe")
list(SORT FRAMEPLAYER_FXC_CANDIDATES ORDER DESCENDING)
set(FRAMEPLAYER_FXC_HINTS "${FRAMEPLAYER_SDK_BIN}/${CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION}/x64")
foreach(candidate IN LISTS FRAMEPLAYER_FXC_CANDIDATES)
    get_filename_component(candidate_dir "${candidate}" DIRECTORY)
    list(APPEND FRAMEPLAYER_FXC_HINTS "${candidate_dir}")
endforeach()
find_program(FXC_EXECUTABLE fxc HINTS ${FRAMEPLAYER_FXC_HINTS} REQUIRED)
set(FRAMEPLAYER_SHADER_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/src/core/shaders/FrameShaders.hlsl")
set(FRAMEPLAYER_SHADER_DIR "${CMAKE_CURRENT_BINARY_DIR}/shaders")
set(FRAMEPLAYER_SHADER_HEADERS)
foreach(entry IN ITEMS VSFullscreen:vs PSDownscale:ps PSConvert:ps PSPresent:ps)
    string(REPLACE ":" ";" parts "${entry}")
    list(GET parts 0 name)
    list(GET parts 1 stage)
    set(header "${FRAMEPLAYER_SHADER_DIR}/${name}.h")
    add_custom_command(OUTPUT "${header}"
        COMMAND "${CMAKE_COMMAND}" -E make_directory "${FRAMEPLAYER_SHADER_DIR}"
        COMMAND "${FXC_EXECUTABLE}" /nologo /O3 /WX /T ${stage}_4_0 /E ${name} /Vn g_${name} /Fh "${header}"
                "${FRAMEPLAYER_SHADER_SOURCE}"
        DEPENDS "${FRAMEPLAYER_SHADER_SOURCE}"
        COMMENT "Compiling shader ${name}"
        VERBATIM)
    list(APPEND FRAMEPLAYER_SHADER_HEADERS "${header}")
endforeach()

# 画面に依存しない読み込み処理。プレイヤー本体と確認用ツールで共有する。
add_library(frameplayer_core STATIC
    ${FRAMEPLAYER_SHADER_HEADERS}
    src/core/ColorInfo.cpp
    src/core/FrameRenderer.cpp
    src/core/Clip.cpp
    src/core/FrameSource.cpp
    src/core/MediaFoundationSource.cpp
    src/core/Mp4SampleTable.cpp
    src/core/AudioPlayer.cpp
    src/core/GpuDevice.cpp
    src/core/KeyframeThumbnails.cpp
)
target_include_directories(frameplayer_core PUBLIC src PRIVATE "${FRAMEPLAYER_SHADER_DIR}")
target_compile_definitions(frameplayer_core PUBLIC UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
target_compile_options(frameplayer_core PUBLIC /utf-8 /W4 /permissive-)
target_link_libraries(frameplayer_core PUBLIC mfplat mfreadwrite mfuuid ole32 d3d11 dxgi propsys)

add_executable(FramePlayer WIN32
    src/app/main.cpp
    src/app/PlayerWindow.cpp
    src/app/PlayerWindowControls.cpp
    src/app/VideoView.cpp
    src/app/SyncServer.cpp
    src/app/SyncAuth.cpp
    src/app/Ui.cpp
    src/app/Settings.cpp
    src/app/FramePlayer.rc
)
target_link_libraries(FramePlayer PRIVATE frameplayer_core user32 gdi32 shell32 advapi32 d2d1 dwrite dxgi dwmapi comctl32 uxtheme ws2_32 bcrypt)

# 配布用: `cmake --install build --config Release` でexeをこのフォルダ(パッケージ直下)へコピーする(Git管理対象)。
# ビルドのたびに管理対象のexeが変わらないよう、コピーはインストールを実行したときだけ行う。
install(TARGETS FramePlayer RUNTIME DESTINATION "${CMAKE_CURRENT_SOURCE_DIR}")

# コマ番号が正確に読めているかを確かめる確認用ツール(配布対象外)。
add_executable(FramePlayerVerify tests/verify_frame_index.cpp)
target_link_libraries(FramePlayerVerify PRIVATE frameplayer_core)

# 色の正確さを確かめる確認用ツール(配布対象外)。tests/make_color_testdata.py で作った動画と期待値を使う。
add_executable(FramePlayerColorCheck tests/verify_color.cpp)
target_link_libraries(FramePlayerColorCheck PRIVATE frameplayer_core)
