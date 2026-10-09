{#-
  hlib のモジュール/パッケージページ。
  独自の書式にするのは hlib.cmds(コマンド一覧)と hlib.cmds.<コマンド名>(各コマンド)だけ。
  それ以外は sphinx-autoapi に同梱された既定テンプレートへそのまま委ねる。
  "autoapi-packaged/" 接頭辞は conf.py の _prepare_jinja_env で登録している。
-#}
{{ prepare_getter_docs(obj) }}
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
{% if preferred_command(command_module) %}
   {{ command_module.include_path }}
{% endif %}
{% endfor %}

{% elif obj.id.startswith(command_package ~ ".") %}
{#- 取得コマンドはcmdsとルートの公開入口を、同じ署名・説明にまとめる。 -#}
{% set command_name = obj.short_name %}
{% set short_name = short_command(obj) %}
{% set entry_point = obj.functions|selectattr("short_name", "equalto", command_name)|first %}
{% set synopsis = obj.docstring
    |replace(".. rubric:: Examples", "Examples\n--------")
    |replace(".. rubric:: サンプル", "Examples\n--------") %}
{% if short_name %}
:orphan:

{% endif %}
{{ command_name }}
{{ "=" * command_name|length }}

.. py:module:: {{ obj.name }}
   :no-index:

{% if short_name %}
.. raw:: html

   <span id="{{ package_name }}.{{ command_name }}"></span>

取得APIの説明・使用例は :py:func:`{{ package_name }}.{{ short_name }}` を参照してください。

{% else %}
.. contents:: Go to
   :local:
   :depth: 1

{% if entry_point %}
.. py:currentmodule:: {{ package_name }}

.. py:function:: {{ command_name }}({{ entry_point.args }}){{ ("\n                 cmds." ~ command_name ~ "(" ~ entry_point.args ~ ")") if entry_point.hlib_getter_id is defined else "" }}
   :no-index-entry:
{% if entry_point.hlib_getter_id is defined %}

   {{ entry_point.docstring|indent(3) }}

.. raw:: html

   <span id="{{ command_package }}.{{ entry_point.hlib_getter_id.rsplit('.', 1)[-1] }}"></span>

{% endif %}
{% endif %}

Synopsis
--------

.. autoapi-nested-parse::

   {{ synopsis|indent(3) }}

{% endif %}
{% else %}
{% for function in obj.functions %}
{% if function.hlib_getter_id is defined %}
.. raw:: html

   <span id="{{ function.hlib_getter_id }}"></span>

{% endif %}
{% endfor %}
{% include "autoapi-packaged/python/module.rst" %}
{% endif %}
