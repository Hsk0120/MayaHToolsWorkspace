{#-
  hlib のモジュール/パッケージページ。
  独自の書式にするのは hlib.cmds(コマンド一覧)と hlib.cmds.<コマンド名>(各コマンド)だけ。
  それ以外は sphinx-autoapi に同梱された既定テンプレートへそのまま委ねる。
  "autoapi-packaged/" 接頭辞は conf.py の _prepare_jinja_env で登録している。
-#}
{% set command_package = "hlib.cmds" %}
{% if obj.id == command_package %}
hlib コマンドリファレンス
========================================

.. py:module:: {{ command_package }}

コマンド名を選ぶと、構文・戻り値・フラグ・使用例を確認できます。
Python では ``hlib.<コマンド名>()`` として呼び出します。

.. toctree::
   :maxdepth: 1

{% for command_module in obj.submodules|sort %}
   {{ command_module.include_path }}
{% endfor %}

{% elif obj.id.startswith(command_package ~ ".") %}
{#- コマンド名と同名の関数を、hlib 直下の公開名として掲載する。 -#}
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
.. py:currentmodule:: hlib

.. py:function:: {{ command_name }}({{ entry_point.args }})
   :no-index-entry:
{% endif %}

Synopsis
--------

.. autoapi-nested-parse::

   {{ synopsis|indent(3) }}

{% else %}
{% include "autoapi-packaged/python/module.rst" %}
{% endif %}
