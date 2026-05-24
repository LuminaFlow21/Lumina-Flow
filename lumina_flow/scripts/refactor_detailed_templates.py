from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / 'templates'

THEMES = {
    'detailed_modern.html': {
        'bg_body': '#ecf1ff',
        'fg_primary': '#0f172a',
        'fg_muted': '#64748b',
        'accent': '#4f46e5',
        'accent_secondary': '#0ea5e9',
        'accent_soft': '#e0e7ff',
        'border': '#e2e8f0',
        'card_bg': '#ffffff',
        'hint_bg': '#f8fafc',
    },
    'detailed_bold.html': {
        'bg_body': '#fff1f2',
        'fg_primary': '#2b0f12',
        'fg_muted': '#a16207',
        'accent': '#be123c',
        'accent_secondary': '#f97316',
        'accent_soft': '#ffe4e6',
        'border': '#fecdd3',
        'card_bg': '#fff',
        'hint_bg': '#fff7ed',
    },
    'detailed_classic.html': {
        'bg_body': '#f5f1ea',
        'fg_primary': '#1f2937',
        'fg_muted': '#6b7280',
        'accent': '#b45309',
        'accent_secondary': '#d97706',
        'accent_soft': '#fef3c7',
        'border': '#e5e7eb',
        'card_bg': '#fff8ed',
        'hint_bg': '#fffbeb',
    },
    'detailed_clean.html': {
        'bg_body': '#f0fdfa',
        'fg_primary': '#0f172a',
        'fg_muted': '#0f766e',
        'accent': '#0f766e',
        'accent_secondary': '#14b8a6',
        'accent_soft': '#ccfbf1',
        'border': '#99f6e4',
        'card_bg': '#ffffff',
        'hint_bg': '#ecfeff',
    },
    'detailed_creative.html': {
        'bg_body': '#fdf2ff',
        'fg_primary': '#3b0764',
        'fg_muted': '#6b21a8',
        'accent': '#a855f7',
        'accent_secondary': '#6366f1',
        'accent_soft': '#f3e8ff',
        'border': '#e9d5ff',
        'card_bg': '#ffffff',
        'hint_bg': '#fdf4ff',
    },
    'detailed_elegant.html': {
        'bg_body': '#f4f4f5',
        'fg_primary': '#1c1917',
        'fg_muted': '#57534e',
        'accent': '#78350f',
        'accent_secondary': '#ea580c',
        'accent_soft': '#fef0c7',
        'border': '#e4e4e7',
        'card_bg': '#ffffff',
        'hint_bg': '#fafaf9',
    },
    'detailed_luxury.html': {
        'bg_body': '#0b1120',
        'fg_primary': '#f7f5ef',
        'fg_muted': '#94a3b8',
        'accent': '#facc15',
        'accent_secondary': '#f59e0b',
        'accent_soft': '#4c1d95',
        'border': '#1e293b',
        'card_bg': '#111827',
        'hint_bg': '#1e1b4b',
    },
    'detailed_premium.html': {
        'bg_body': '#ecfccb',
        'fg_primary': '#1f2937',
        'fg_muted': '#4d7c0f',
        'accent': '#15803d',
        'accent_secondary': '#34d399',
        'accent_soft': '#dcfce7',
        'border': '#bbf7d0',
        'card_bg': '#ffffff',
        'hint_bg': '#f0fdf4',
    },
    'detailed_tech.html': {
        'bg_body': '#0f172a',
        'fg_primary': '#e2e8f0',
        'fg_muted': '#94a3b8',
        'accent': '#38bdf8',
        'accent_secondary': '#22d3ee',
        'accent_soft': '#0ea5e9',
        'border': '#1e293b',
        'card_bg': '#020617',
        'hint_bg': '#111c30',
    },
    'detailed_vibrant.html': {
        'bg_body': '#fff7ed',
        'fg_primary': '#422006',
        'fg_muted': '#9a3412',
        'accent': '#ec4899',
        'accent_secondary': '#f97316',
        'accent_soft': '#ffe4e6',
        'border': '#fed7aa',
        'card_bg': '#ffffff',
        'hint_bg': '#fff0f6',
    },
}

TEMPLATE_PREFIX = "{% set theme = {\n"
TEMPLATE_SUFFIX = "\n} %}\n{% include 'partials/detailed_template_base.html' %}\n"

def render_theme(theme_dict):
    pairs = []
    for key, value in theme_dict.items():
        pairs.append(f"  '{key}': '{value}'")
    return ',\n'.join(pairs)


def main():
    for filename, theme in THEMES.items():
        target = TEMPLATES_DIR / filename
        if not target.exists():
            print(f'[skip] {filename} não encontrado')
            continue
        content = TEMPLATE_PREFIX + render_theme(theme) + TEMPLATE_SUFFIX
        target.write_text(content, encoding='utf-8')
        print(f'[ok] {filename} atualizado')


if __name__ == '__main__':
    main()
