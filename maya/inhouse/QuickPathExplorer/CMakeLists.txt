cmake_minimum_required(VERSION 3.24)
project(QuickPathExplorer LANGUAGES C CXX RC)
# MayaはホストのQtへリンクする。Windows静的版はnative/で別に構成する。
set(QPE_PRODUCT_BUILD ON CACHE BOOL "Build the production plugin name and command")
set(QPE_OUTPUT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/release/plug-ins/windows" CACHE PATH "Product plugin directory")
add_subdirectory(maya-native)
