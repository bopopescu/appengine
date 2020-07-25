from jinja2 import Environment
from jinja2.loaders import DictLoader

env = Environment(loader=DictLoader({
'child.html': u'''\
{% extends main_layout or 'main.html' %}
{% include helpers = 'helpers.html' %}
{% macro get_the_answer() %}42{% endmacro %}
{% title = 'Hello World' %}
{% block body %}
    {{ get_the_answer() }}
    {{ helpers.conspirate() }}
{% endblock %}
''',
'main.html': u'''\
<!doctype html>
<title>{{ title }}</title>
{% block body %}{% endblock %}
''',
'helpers.html': u'''\
{% macro conspirate() %}23{% endmacro %}
'''
}))


tmpl = env.get_template("child.html")
print tmpl.render()
