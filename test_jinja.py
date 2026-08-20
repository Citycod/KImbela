from jinja2 import Template, Environment

env = Environment()
template_str = """
{% set token = csrf_token() if csrf_token is callable else csrf_token %}
Token is: {{ token }}
"""
try:
    template = env.from_string(template_str)
    print("Function:", template.render(csrf_token=lambda: "im_a_func"))
    print("String:", template.render(csrf_token="im_a_string"))
except Exception as e:
    print("Error:", e)
