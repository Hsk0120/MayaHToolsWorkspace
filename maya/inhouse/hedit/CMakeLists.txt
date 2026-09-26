cmake_minimum_required(VERSION 3.15)

project(hedit)

# ソースはUTF-8。Mayaのバージョンによって既定の文字コードが違うため明示する
if(MSVC)
    add_compile_options(/utf-8 /Zc:__cplusplus /permissive-)
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

# specify project name
set(PROJECT_NAME hedit)

# set SOURCE_FILES
set(SOURCE_FILES src/editor.cpp src/editor.h src/explorer.cpp src/explorer.h src/spelling.cpp src/spelling.h src/plugin.cpp)

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

add_executable(hedit_ui_smoke src/editor.cpp src/explorer.cpp src/spelling.cpp tests/ui_smoke.cpp)
target_include_directories(hedit_ui_smoke PRIVATE src ${INCLUDE_DIRS})
target_link_libraries(hedit_ui_smoke PRIVATE ${PACKAGE_LIBS} ole32)
set_target_properties(hedit_ui_smoke PROPERTIES CXX_STANDARD 17)

# set output directory for the Maya plugin (.mll)
set_target_properties(${PROJECT_NAME} PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY_DEBUG          "${CMAKE_CURRENT_SOURCE_DIR}/release/plug-ins/windows/${MAYA_VERSION}/0.2.10"
    RUNTIME_OUTPUT_DIRECTORY_RELEASE        "${CMAKE_CURRENT_SOURCE_DIR}/release/plug-ins/windows/${MAYA_VERSION}/0.2.10"
    RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO "${CMAKE_CURRENT_SOURCE_DIR}/release/plug-ins/windows/${MAYA_VERSION}/0.2.10"
    RUNTIME_OUTPUT_DIRECTORY_MINSIZEREL     "${CMAKE_CURRENT_SOURCE_DIR}/release/plug-ins/windows/${MAYA_VERSION}/0.2.10"
)

# output .pdb to build/pdb
set_target_properties(${PROJECT_NAME} PROPERTIES
    PDB_OUTPUT_DIRECTORY_DEBUG              "${CMAKE_CURRENT_BINARY_DIR}/pdb/0.2.10"
    PDB_OUTPUT_DIRECTORY_RELEASE            "${CMAKE_CURRENT_BINARY_DIR}/pdb/0.2.10"
)

