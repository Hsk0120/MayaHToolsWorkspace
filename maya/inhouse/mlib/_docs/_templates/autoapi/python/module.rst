{#-
  mlib のモジュール/パッケージページ。
  独自の書式にするのは mlib.cmds(コマンド一覧)と mlib.cmds.<コマンド名>(各コマンド)だけ。
  それ以外は sphinx-autoapi に同梱された既定テンプレートへそのまま委ねる。
  "autoapi-packaged/" 接頭辞は conf.py の _prepare_jinja_env で登録している。
-#}
{% set command_package = package_name ~ ".cmds" %}
{% if obj.id == command_package %}
{{ package_name }} コマンドリファレンス
{{ "=" * (package_name|length + 30) }}

.. py:module:: {{ command_package }}

コマンド名を選ぶと、構文・戻り値・フラグ・使用例を確認できます。
Python では ``{{ command_package }}.<コマンド名>()`` として呼び出します。
``{{ package_name }}.<コマンド名>()`` も同じ関数の公開入口です。

.. toctree::
   :maxdepth: 1

{% for command_module in obj.submodules|sort %}
   {{ command_module.include_path }}
{% endfor %}

{% elif obj.id.startswith(command_package ~ ".") %}
{#- 取得コマンドはcmdsとルートの公開入口を、同じ署名・説明にまとめる。 -#}
{% set command_name = obj.short_name %}
{% set entry_point = obj.functions|selectattr("short_name", "equalto", command_name)|first %}
{% set synopsis = obj.docstring
    |replace(".. rubric:: Examples", "Examples\n--------")
    |replace(".. rubric:: サンプル", "Examples\n--------") %}
{{ command_name }}
{{ "=" * command_name|length }}

.. py:module:: {{ obj.name }}
   :no-index:

.. contents:: Go to
   :local:
   :depth: 1

{% if entry_point %}
.. py:currentmodule:: {{ package_name }}

.. py:function:: {{ command_name }}({{ entry_point.args }})
                 cmds.{{ command_name }}({{ entry_point.args }})
   :no-index-entry:

   {{ entry_point.docstring|indent(3) }}

{% endif %}

Synopsis
--------

.. autoapi-nested-parse::

   {{ synopsis|indent(3) }}

{% else %}
{% include "autoapi-packaged/python/module.rst" %}
{% endif %}
