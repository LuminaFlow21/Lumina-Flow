import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = [
    'templates/detailed_bold.html',
    'templates/detailed_classic.html',
    'templates/detailed_clean.html',
    'templates/detailed_creative.html',
    'templates/detailed_elegant.html',
    'templates/detailed_luxury.html',
    'templates/detailed_premium.html',
    'templates/detailed_tech.html',
    'templates/detailed_vibrant.html',
    'templates/quick_bold.html',
    'templates/quick_classic.html',
    'templates/quick_clean.html',
    'templates/quick_creative.html',
    'templates/quick_elegant.html',
    'templates/quick_luxury.html',
    'templates/quick_modern_v2.html',
    'templates/quick_premium.html',
    'templates/quick_tech.html',
    'templates/quick_vibrant.html',
]

CSS_SNIPPET = "\n  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='css/quotation_actions.css') }}\">"
JS_SNIPPET = "\n  <script src=\"{{ url_for('static', filename='js/quotation_actions.js') }}\"></script>\n"
INCLUDE_SNIPPET = "\n{% include 'partials/quotation_actions.html' %}\n"

LAYOUT_PATTERN = re.compile(r"\s*<div class=\"layout-shell layout-shell--actions\">[\s\S]*?</div>\s*</div>", re.MULTILINE)
ACTIONS_PATTERN = re.compile(r"\s*<div class=\"action-buttons\"[^>]*>[\s\S]*?</div>", re.MULTILINE)

changed_files = []

for rel_path in TEMPLATES:
    path = ROOT / rel_path
    text = path.read_text(encoding='utf-8')

    if "partials/quotation_actions.html" in text:
        continue

    original = text

    # Add CSS link
    if 'quotation_actions.css' not in text:
        marker = "quotation_viewer.css"
        idx = text.find(marker)
        if idx != -1:
            line_end = text.find('\n', idx)
            if line_end == -1:
                line_end = idx + len(marker)
            text = text[:line_end] + CSS_SNIPPET + text[line_end:]

    # Add JS include
    if 'quotation_actions.js' not in text:
        if '</body>' in text:
            text = text.replace('</body>', f"{JS_SNIPPET}</body>", 1)

    # Remove legacy action shells
    text, _ = LAYOUT_PATTERN.subn('\n', text, count=1)
    text, _ = ACTIONS_PATTERN.subn('\n', text, count=1)

    # Insert partial include after <body>
    if "partials/quotation_actions.html" not in text:
        body_idx = text.lower().find('<body')
        if body_idx != -1:
            body_close = text.find('>', body_idx)
            if body_close != -1:
                insert_pos = body_close + 1
                text = text[:insert_pos] + INCLUDE_SNIPPET + text[insert_pos:]

    if text != original:
        path.write_text(text, encoding='utf-8')
        changed_files.append(rel_path)

print('Updated', len(changed_files), 'templates:')
for rel in changed_files:
    print(' -', rel)
