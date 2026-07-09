import os
import re

html_path = r"d:\Code\scoring\templates\index.html"
css_path = r"d:\Code\scoring\static\css\main.css"
js_path = r"d:\Code\scoring\static\js\main.js"

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract styles
style_match = re.search(r'<style>(.*?)</style>', content, flags=re.DOTALL)
if style_match:
    with open(css_path, 'w', encoding='utf-8') as f:
        f.write(style_match.group(1).strip())
    content = content.replace(style_match.group(0), '<link rel="stylesheet" href="/static/css/main.css">')

# Extract scripts (only the last one which is the main script)
script_matches = list(re.finditer(r'<script>(.*?)</script>', content, flags=re.DOTALL))
if script_matches:
    last_script = script_matches[-1]
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(last_script.group(1).strip())
    content = content[:last_script.start()] + '<script src="/static/js/main.js"></script>' + content[last_script.end():]

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Extraction complete")
