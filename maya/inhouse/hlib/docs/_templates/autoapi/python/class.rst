{#-
  hlib のクラスページ。例外クラスもこのテンプレートで描画される。

  hlib の API は「Maya へ問い合わせる処理・シーンを変える処理はメソッド、
  保持している値はプロパティ」で表す(docs/hlib-api-design.md)。
  ページの後半もこの区分でメンバーを分け、数の多いメソッドを先に置く。
  各まとまりは、そのまとまりだけの早見表と個々の説明で完結させる。

    独立ページ:
      見出し → 宣言 → ベースクラス → クラス継承図 → クラスの説明
      → メソッド(早見表・説明) → プロパティ・属性(早見表・説明)
      → その他のメンバー(上の2区分に入らない種類があれば説明のみ)
    独立ページを持たない入れ子クラス:
      見出しと継承図を省き、短い名前で宣言する。
-#}
{#- (見出し, 対象とするメンバーの種類, 早見表を付けるか) -#}
{% set member_groups = [
    ("メソッド", ["method"], true),
    ("プロパティ・属性", ["property", "attribute"], true),
] %}
{% if obj.display %}
{% set visible = obj.children|selectattr("display")|list %}
{% set grouped_kinds = member_groups|map(attribute=1)|sum(start=[]) %}
{% set others = visible|rejectattr("type", "in", grouped_kinds)|list %}
{% set target = obj.id if is_own_page else obj.short_name %}
{% set generics = "[" ~ obj.type_params ~ "]" if obj.type_params else "" %}
{% set call_args = "(" ~ obj.args ~ ")" if obj.args else "" %}
{% if is_own_page %}
{% set heading = "class " ~ obj.id %}
{{ heading }}
{{ "=" * heading|length }}

{% endif %}
.. py:{{ obj.type }}:: {{ target }}{{ generics }}{{ call_args }}

{% if obj.bases and "show-inheritance" in autoapi_options %}
   ベースクラス: {{ obj.bases|map("link_objs")|join(", ") }}

{% endif %}
{% set lineage = ancestor_class_diagram(obj.short_name) if is_own_page else None %}
{% if lineage %}
   .. rubric:: クラス継承図

   このクラスの祖先と直接の派生クラスを表示します。矢印の先が基底クラスです。
   hlibのクラス名をクリックすると、そのクラスのリファレンスへ移動します。

   .. raw:: html

      <pre class="mermaid">
{{ lineage }}
      </pre>

{% endif %}
{% if obj.docstring %}
   {{ obj.docstring|indent(3) }}

{% endif %}
{% for title, kinds, with_table in member_groups %}
{% set group = visible|selectattr("type", "in", kinds)|list %}
{% if group %}
   .. rubric:: {{ title }}

{% if with_table %}
   .. autoapisummary::

{% for entry in group %}
      {{ entry.id }}
{% endfor %}

{% endif %}
{% for entry in group %}
   {{ entry.render()|indent(3) }}

{% endfor %}
{% endif %}
{% endfor %}
{% if others %}
   .. rubric:: その他のメンバー

{% for entry in others %}
   {{ entry.render()|indent(3) }}

{% endfor %}
{% endif %}
{% endif %}
