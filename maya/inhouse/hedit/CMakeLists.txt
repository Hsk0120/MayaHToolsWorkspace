cmake_minimum_required(VERSION 3.15)

project(hedit)

# ソースはUTF-8。Mayaのバージョンによって既定の文字コードが違うため明示する
if(MSVC)
    add_compile_options(/utf-8 /Zc:__cplusplus /permissive-)
    # M_PIなどの数学定数を、どのヘッダーより先にWindows標準の定義で用意する。
    # MayaとQtはそれぞれ条件付きで同じ名前を定義するため、#includeの順番によって再定義の警告(C4005)が出る。
    add_compile_definitions(_USE_MATH_DEFINES)
endif()

# group CMake predefined targets
set_property(GLOBAL PROPERTY USE_FOLDERS ON)
set_property(GLOBAL PROPERTY PREDEFINED_TARGETS_FOLDER "CMakeTargets")

# include the project setting file
include("$ENV{DEVKIT_LOCATION}/cmake/pluginEntry.cmake")

# MayaのSDKには未同梱のQtデバッグ用プラグインを参照するCMake情報がある。
# moc不要の実装なので、使用するReleaseのQtライブラリだけを明示する。
if(MAYA_VERSION VERSION_GREATER_EQUAL 2025)
    foreach(component Core Gui Widgets)
        list(APPEND PACKAGE_LIBS "$ENV{DEVKIT_LOCATION}/Qt/lib/Qt6${component}.lib")
        list(APPEND INCLUDE_DIRS "$ENV{DEVKIT_LOCATION}/Qt/include/Qt${component}")
    endforeach()
    list(APPEND INCLUDE_DIRS "$ENV{DEVKIT_LOCATION}/Qt/include")
    add_compile_definitions(QT_CORE_LIB QT_GUI_LIB QT_WIDGETS_LIB)
endif()

# Maya 2022-2024(Qt5): 手動でQt5を設定
if(MAYA_VERSION VERSION_LESS 2025)
    # MayaにはRelease版のQtしかないため、Debug構成でもRelease版を使用
    # この設定はfind_packageより前に行う必要がある
    set(CMAKE_MAP_IMPORTED_CONFIG_DEBUG "Release;RelWithDebInfo;MinSizeRel;")
    set(CMAKE_MAP_IMPORTED_CONFIG_RELWITHDEBINFO "Release;RelWithDebInfo;MinSizeRel;")

    # Qt5のファイル存在チェックを無効化（Mayaにはリリース版のみ存在）
    macro(_qt5_Core_check_file_exists file)
        # 何もしない（存在チェックをスキップ）
    endmacro()
    macro(_qt5_Gui_check_file_exists file)
    endmacro()
    macro(_qt5_Widgets_check_file_exists file)
    endmacro()

    # Qtプラグインの自動ロードを無効化（存在しないプラグインでエラーになるため）
    set(Qt5_NO_LINK_QTMAIN ON)
    set(CMAKE_AUTOMOC OFF)
    set(CMAKE_AUTORCC OFF)
    set(CMAKE_AUTOUIC OFF)

    # Qt5のCMakeパスを設定
    set(CMAKE_PREFIX_PATH "$ENV{DEVKIT_LOCATION}/lib/cmake/Qt5")

    # Qt5パッケージを検索
    find_package(Qt5 COMPONENTS Core Widgets Gui REQUIRED)

    # Qt関連のライブラリを追加
    set(PACKAGE_LIBS ${PACKAGE_LIBS} Qt5::Core Qt5::Widgets Qt5::Gui)

    # Qtインクルードディレクトリを追加
    set(INCLUDE_DIRS ${INCLUDE_DIRS} "$ENV{DEVKIT_LOCATION}/include")
endif()

# ---- 版 ----
# src/version.h の HEDIT_VERSION を唯一の定義とし、出力先のフォルダー名にも使う。
file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/src/version.h" HEDIT_VERSION_LINE REGEX "^#define HEDIT_VERSION ")
string(REGEX MATCH "\"([^\"]+)\"" _ "${HEDIT_VERSION_LINE}")
set(HEDIT_VERSION "${CMAKE_MATCH_1}")
if(NOT HEDIT_VERSION)
    message(FATAL_ERROR "HEDIT_VERSION was not found in src/version.h")
endif()

# ---- 同梱するPython ----
# src/python/ の .py を、ビルド時にC++の配列(embedded_python_sources.h)へ変換する。
# .py を直したら、再ビルドで hedit.mll に反映される。
file(GLOB_RECURSE HEDIT_PYTHON_FILES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/src/python/*.py")
set(HEDIT_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(HEDIT_EMBEDDED_HEADER "${HEDIT_GENERATED_DIR}/embedded_python_sources.h")
add_custom_command(
    OUTPUT "${HEDIT_EMBEDDED_HEADER}"
    COMMAND "${CMAKE_COMMAND}"
            "-DSOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}/src/python"
            "-DOUTPUT=${HEDIT_EMBEDDED_HEADER}"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/embed_python.cmake"
    DEPENDS ${HEDIT_PYTHON_FILES} "${CMAKE_CURRENT_SOURCE_DIR}/cmake/embed_python.cmake"
    COMMENT "Embedding hedit Python sources"
)

# ---- ソース ----
# core/   : Mayaにも画面にも依存しない処理(テストしやすい)
# editor/ : Qtの編集画面(Mayaに依存しない。hedit_ui_smokeでもそのまま使う)
# plugin/ : Maya APIを使う部分(コマンド・出力の購読・ドック・メニュー)
set(HEDIT_CORE_SOURCES
    src/core/output_message.h
    src/core/completion_types.cpp src/core/completion_types.h
    src/core/completion_engine.cpp src/core/completion_engine.h
    src/core/docstrings.cpp src/core/docstrings.h
    src/core/history_text.cpp src/core/history_text.h
    src/core/json_file.cpp src/core/json_file.h
    src/core/module_scanner.cpp src/core/module_scanner.h
    src/core/python_declarations.cpp src/core/python_declarations.h
    src/core/python_literal.cpp src/core/python_literal.h
    src/core/script_file.cpp src/core/script_file.h
    src/core/script_lexer.cpp src/core/script_lexer.h
    src/core/session_data.cpp src/core/session_data.h
    src/core/symbols.cpp src/core/symbols.h
    src/core/text_search.cpp src/core/text_search.h
)
set(HEDIT_EDITOR_SOURCES
    src/editor/editor.cpp src/editor/editor.h
    src/editor/main_window.cpp src/editor/main_window_menus.cpp src/editor/main_window.h
    src/editor/code_assist.cpp src/editor/code_assist.h
    src/editor/code_editor.cpp src/editor/code_editor.h
    src/editor/edit_commands.cpp src/editor/edit_commands.h
    src/editor/editor_preferences.cpp src/editor/editor_preferences.h
    src/editor/editor_tabs.cpp src/editor/editor_tabs.h
    src/editor/explorer.cpp src/editor/explorer.h
    src/editor/find_bar.cpp src/editor/find_bar.h
    src/editor/find_icons.cpp src/editor/find_icons.h
    src/editor/hover_popup.cpp src/editor/hover_popup.h
    src/editor/numbered_text_edit.cpp src/editor/numbered_text_edit.h
    src/editor/output_panel.cpp src/editor/output_panel.h
    src/editor/problems_panel.cpp src/editor/problems_panel.h
    src/editor/session_store.cpp src/editor/session_store.h
    src/editor/spelling.cpp src/editor/spelling.h
    src/editor/syntax_highlighter.cpp src/editor/syntax_highlighter.h
    src/editor/theme.h
    src/editor/ui_scale.cpp src/editor/ui_scale.h
)
set(HEDIT_PLUGIN_SOURCES
    src/plugin/plugin.cpp
    src/plugin/hedit_command.cpp src/plugin/hedit_command.h
    src/plugin/test_command.cpp src/plugin/test_command.h
    src/plugin/editor_host.cpp src/plugin/editor_host.h
    src/plugin/output_capture.cpp src/plugin/output_capture.h
    src/plugin/python_bridge.cpp src/plugin/python_bridge.h
    src/plugin/dock.cpp src/plugin/dock.h
    src/plugin/window_menu.cpp src/plugin/window_menu.h
    src/plugin/user_paths.cpp src/plugin/user_paths.h
    src/plugin/embedded_python.cpp src/plugin/embedded_python.h
    src/plugin/mel.h
    src/version.h
    "${HEDIT_EMBEDDED_HEADER}"
)
source_group(core FILES ${HEDIT_CORE_SOURCES})
source_group(editor FILES ${HEDIT_EDITOR_SOURCES})
source_group(plugin FILES ${HEDIT_PLUGIN_SOURCES})
source_group(python FILES ${HEDIT_PYTHON_FILES})

# specify project name
set(PROJECT_NAME hedit)

# set SOURCE_FILES
set(SOURCE_FILES ${HEDIT_CORE_SOURCES} ${HEDIT_EDITOR_SOURCES} ${HEDIT_PLUGIN_SOURCES} ${HEDIT_PYTHON_FILES})
# #include "core/..." のように src/ からのパスで書けるようにする。生成したヘッダーの場所も加える。
list(APPEND INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}/src" "${HEDIT_GENERATED_DIR}")

# set linking libraries
set(LIBRARIES
     OpenMaya
     OpenMayaAnim
     OpenMayaUI
     OpenMayaRender
     Foundation
)

# Build plugin
build_plugin()
target_link_libraries(hedit ole32)
set_target_properties(hedit PROPERTIES CXX_STANDARD 17 CXX_STANDARD_REQUIRED ON)

# Maya無しでQtの画面とcore/を検証するテスト(tests/ui_smoke.cpp)。本番と同じソースをそのまま使う。
add_executable(hedit_ui_smoke ${HEDIT_CORE_SOURCES} ${HEDIT_EDITOR_SOURCES} tests/ui_smoke.cpp)
target_include_directories(hedit_ui_smoke PRIVATE src ${INCLUDE_DIRS})
target_link_libraries(hedit_ui_smoke PRIVATE ${PACKAGE_LIBS} ole32)
set_target_properties(hedit_ui_smoke PROPERTIES CXX_STANDARD 17)

# Mayaのプラグイン(.mll)の出力先。版のフォルダーは作らない(release/plug-ins/windows/<Mayaの年>/hedit.mll)。
# 版ごとにフォルダーを変えると、Mayaの「信頼済みのプラグインの場所」とオートロードの設定が版を上げるたびに外れるため。
set(HEDIT_RELEASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/release/plug-ins/windows/${MAYA_VERSION}")
set_target_properties(${PROJECT_NAME} PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY_DEBUG          "${HEDIT_RELEASE_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_RELEASE        "${HEDIT_RELEASE_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO "${HEDIT_RELEASE_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_MINSIZEREL     "${HEDIT_RELEASE_DIR}"
)

# .pdb(デバッグ情報)はビルドフォルダーへ置く。
set_target_properties(${PROJECT_NAME} PROPERTIES
    PDB_OUTPUT_DIRECTORY_DEBUG              "${CMAKE_CURRENT_BINARY_DIR}/pdb"
    PDB_OUTPUT_DIRECTORY_RELEASE            "${CMAKE_CURRENT_BINARY_DIR}/pdb"
)

if(MSVC)
    # .mllに入るpdbの場所を、作業フォルダーの絶対パスではなくファイル名だけにする(/PDBALTPATH)。
    # 制御フローガード(/guard:cf)で、不正な関数呼出しを防ぐ保護を有効にする。
    target_compile_options(${PROJECT_NAME} PRIVATE /guard:cf)
    target_link_options(${PROJECT_NAME} PRIVATE /guard:cf /PDBALTPATH:hedit.pdb)

    # ファイル情報(版・製品名)。src/version.hの版から作る。
    string(REPLACE "." ";" HEDIT_VERSION_PARTS "${HEDIT_VERSION}")
    list(GET HEDIT_VERSION_PARTS 0 HEDIT_VERSION_MAJOR)
    list(GET HEDIT_VERSION_PARTS 1 HEDIT_VERSION_MINOR)
    list(GET HEDIT_VERSION_PARTS 2 HEDIT_VERSION_PATCH)
    configure_file("${CMAKE_CURRENT_SOURCE_DIR}/cmake/hedit_version.rc.in"
                   "${CMAKE_CURRENT_BINARY_DIR}/hedit_version.rc" @ONLY)
    target_sources(${PROJECT_NAME} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/hedit_version.rc")
endif()
