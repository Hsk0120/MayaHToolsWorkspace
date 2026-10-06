cmake_minimum_required(VERSION 3.15)

project(pluginLoadProbe)

# ソースはUTF-8。Mayaのバージョンによって既定の文字コードが違うため明示する
if(MSVC)
    add_compile_options(/utf-8)
endif()

# Mayaのdevkitの共通設定(tools/build_maya_plugin.pyがDEVKIT_LOCATIONとMAYA_VERSIONを渡す)
include("$ENV{DEVKIT_LOCATION}/cmake/pluginEntry.cmake")

set(PROJECT_NAME pluginLoadProbe)
set(SOURCE_FILES src/plugin.cpp)

# 切り分けのため、Qt・COMなどは使わずMaya本体の最小限のライブラリだけをリンクする
set(LIBRARIES
     OpenMaya
     Foundation
)

build_plugin()

# 出力先: release/plug-ins/windows/<Mayaの年>/pluginLoadProbe.mll (Git対象外)
set(PROBE_RELEASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/release/plug-ins/windows/${MAYA_VERSION}")
set_target_properties(${PROJECT_NAME} PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY_DEBUG          "${PROBE_RELEASE_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_RELEASE        "${PROBE_RELEASE_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO "${PROBE_RELEASE_DIR}"
    RUNTIME_OUTPUT_DIRECTORY_MINSIZEREL     "${PROBE_RELEASE_DIR}"
    PDB_OUTPUT_DIRECTORY_DEBUG              "${CMAKE_CURRENT_BINARY_DIR}/pdb"
    PDB_OUTPUT_DIRECTORY_RELEASE            "${CMAKE_CURRENT_BINARY_DIR}/pdb"
)
