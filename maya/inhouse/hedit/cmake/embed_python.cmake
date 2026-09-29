# src/python/ の .py ファイルを、C++ から読める配列にしたヘッダーを作る。
#
# hedit.mll 単体で動くよう、補完・構文チェック用の Python はプラグインの中に入れて配る。
# Python は普通の .py ファイルとして編集し、ビルドのたびにこのスクリプトがヘッダーへ変換する
# (CMakeLists.txt の add_custom_command から呼ばれる)。
#
# 使い方:
#   cmake -DSOURCE_DIR=<src/python> -DOUTPUT=<生成するヘッダー> -P embed_python.cmake
#
# モジュール名はフォルダー構成から決める:
#   hedit/__init__.py   → hedit(パッケージ)
#   hedit/bridge.py     → hedit.bridge
#   heditor/__init__.py → heditor(パッケージ)

if(NOT SOURCE_DIR OR NOT OUTPUT)
    message(FATAL_ERROR "embed_python.cmake: SOURCE_DIR and OUTPUT are required")
endif()

file(GLOB_RECURSE python_files RELATIVE "${SOURCE_DIR}" "${SOURCE_DIR}/*.py")
list(SORT python_files)

set(arrays "")
set(entries "")
set(index 0)
foreach(relative IN LISTS python_files)
    # "hedit/bridge.py" → "hedit.bridge"、"hedit/__init__.py" → "hedit"
    string(REGEX REPLACE "\\.py$" "" module "${relative}")
    set(is_package "false")
    if(module MATCHES "/__init__$")
        string(REGEX REPLACE "/__init__$" "" module "${module}")
        set(is_package "true")
    endif()
    string(REPLACE "/" "." module "${module}")

    # ファイルの中身を16進数で読み、"0x69,0x6d,..." の形にする。最後に0を足してC文字列として使えるようにする。
    file(READ "${SOURCE_DIR}/${relative}" content HEX)
    string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," bytes "${content}")
    # 1行が長くなりすぎないよう、24バイトごとに改行する。
    string(REGEX REPLACE "((0x[0-9a-f][0-9a-f],){24})" "\\1\n    " bytes "${bytes}")

    string(APPEND arrays "// ${relative}\ninline const unsigned char kSource${index}[] = {\n    ${bytes}0x00\n};\n\n")
    string(APPEND entries "    {\"${module}\", ${is_package}, reinterpret_cast<const char*>(kSource${index})},\n")
    math(EXPR index "${index} + 1")
endforeach()

set(header "// このファイルは cmake/embed_python.cmake がビルド時に自動で作る。直接編集しないこと。\n")
string(APPEND header "// 元のファイル: src/python/ の .py\n")
string(APPEND header "#pragma once\n#include \"plugin/embedded_python.h\"\n\n")
string(APPEND header "namespace hedit {\nnamespace embedded {\nnamespace generated {\n\n")
string(APPEND header "${arrays}")
string(APPEND header "}  // namespace generated\n\n")
string(APPEND header "/// 同梱するPythonモジュールの一覧(モジュール名の順)。\n")
string(APPEND header "inline const PythonModule kPythonModules[] = {\n")
string(REPLACE "kSource" "generated::kSource" entries "${entries}")
string(APPEND header "${entries}")
string(APPEND header "};\n\n}  // namespace embedded\n}  // namespace hedit\n")

# 内容が変わらなければ書き直さない(不要な再コンパイルを避ける)。
set(previous "")
if(EXISTS "${OUTPUT}")
    file(READ "${OUTPUT}" previous)
endif()
if(NOT previous STREQUAL header)
    file(WRITE "${OUTPUT}" "${header}")
endif()
