{% if obj.display %}
{% if is_own_page %}
{% set title = "class " ~ obj.id %}
{{ title }}
{{ "=" * title|length }}

{% endif %}
{% set children = obj.children|selectattr("display")|list %}
{% set methods = children|selectattr("type", "equalto", "method")|list %}
{% set attributes = children|rejectattr("type", "equalto", "method")|list %}
.. py:{{ obj.type }}:: {% if is_own_page %}{{ obj.id }}{% else %}{{ obj.short_name }}{% endif %}{% if obj.type_params %}[{{ obj.type_params }}]{% endif %}{% if obj.args %}({{ obj.args }}){% endif %}

{% if obj.bases and "show-inheritance" in autoapi_options %}
   ベースクラス: {% for base in obj.bases %}{{ base|link_objs }}{% if not loop.last %}, {% endif %}{% endfor %}

{% endif %}
{% if obj.docstring %}
   {{ obj.docstring|indent(3) }}

{% endif %}
{% if methods %}
   .. rubric:: Methods:

   .. autoapisummary::

{% for method in methods %}
      {{ method.id }}
{% endfor %}

{% endif %}
{% if attributes %}
   .. rubric:: Attributes:

{% for attribute in attributes %}
   {{ attribute.render()|indent(3) }}

{% endfor %}
{% endif %}
{% if methods %}
   .. rubric:: Methods Details:

{% for method in methods %}
   {{ method.render()|indent(3) }}

{% endfor %}
{% endif %}
{% endif %}
