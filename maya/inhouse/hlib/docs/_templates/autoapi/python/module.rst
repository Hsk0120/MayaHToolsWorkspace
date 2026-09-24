{% if obj.id == "hlib.cmds" %}
hlib コマンドリファレンス
========================================

.. py:module:: hlib.cmds

コマンド名を選ぶと、構文・戻り値・フラグ・使用例を確認できます。
Python では ``hlib.<コマンド名>()`` として呼び出します。

.. toctree::
   :maxdepth: 1

{% for module in obj.submodules|sort %}
   {{ module.include_path }}
{% endfor %}

{% elif obj.id.startswith("hlib.cmds.") %}
{{ obj.short_name }}
{{ "=" * obj.short_name|length }}

.. py:module:: {{ obj.name }}
   :no-index:

.. contents:: Go to
   :local:
   :depth: 1

{% for function in obj.functions if function.short_name == obj.short_name %}
.. py:currentmodule:: hlib

.. py:function:: {{ function.short_name }}({{ function.args }})
   :no-index-entry:
{% endfor %}

Synopsis
--------

.. autoapi-nested-parse::

   {{ obj.docstring|replace(".. rubric:: Examples", "Examples\n--------")|replace(".. rubric:: サンプル", "Examples\n--------")|indent(3) }}

{% else %}
{% include "python/module_default.rst" %}
{% endif %}
