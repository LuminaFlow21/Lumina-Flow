from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / 'templates'

THEMES = {
    'quick_modern_v2.html': {
        'bg_body': '#eef3ff',
        'fg_primary': '#182433',
        'fg_muted': '#60708c',
        'accent': '#1565ff',
        'accent_secondary': '#29d6ff',
        'accent_soft': '#e0e7ff',
        'border': '#e2e8f0',
        'card_bg': '#ffffff',
        'hint_bg': '#f7f9fc',
    },
    'quick_bold.html': {
        'bg_body': '#fff1f2',
        'fg_primary': '#4a044e',
        'fg_muted': '#9d174d',
        'accent': '#be185d',
        'accent_secondary': '#f97316',
        'accent_soft': '#ffe4e6',
        'border': '#fecdd3',
        'card_bg': '#ffffff',
        'hint_bg': '#fff7ed',
    },
    'quick_classic.html': {
        'bg_body': '#f4f1ea',
        'fg_primary': '#1f2937',
        'fg_muted': '#6b7280',
        'accent': '#b45309',
        'accent_secondary': '#d97706',
        'accent_soft': '#fef3c7',
        'border': '#e5e7eb',
        'card_bg': '#fffaf2',
        'hint_bg': '#fffbeb',
    },
    'quick_clean.html': {
        'bg_body': '#f0fdfa',
        'fg_primary': '#0f172a',
        'fg_muted': '#047857',
        'accent': '#0f766e',
        'accent_secondary': '#14b8a6',
        'accent_soft': '#ccfbf1',
        'border': '#99f6e4',
        'card_bg': '#ffffff',
        'hint_bg': '#ecfeff',
    },
    'quick_creative.html': {
        'bg_body': '#faf5ff',
        'fg_primary': '#3b0764',
        'fg_muted': '#6b21a8',
        'accent': '#a855f7',
        'accent_secondary': '#6366f1',
        'accent_soft': '#ede9fe',
        'border': '#ddd6fe',
        'card_bg': '#ffffff',
        'hint_bg': '#f8f5ff',
    },
    'quick_elegant.html': {
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
    'quick_luxury.html': {
        'bg_body': '#0b1120',
        'fg_primary': '#f8fafc',
        'fg_muted': '#cbd5f5',
        'accent': '#facc15',
        'accent_secondary': '#f59e0b',
        'accent_soft': '#4c1d95',
        'border': '#1e293b',
        'card_bg': '#111827',
        'hint_bg': '#1e1b4b',
    },
    'quick_premium.html': {
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
    'quick_tech.html': {
        'bg_body': '#020617',
        'fg_primary': '#e2e8f0',
        'fg_muted': '#94a3b8',
        'accent': '#38bdf8',
        'accent_secondary': '#22d3ee',
        'accent_soft': '#0ea5e9',
        'border': '#1e293b',
        'card_bg': '#0f172a',
        'hint_bg': '#111c30',
    },
    'quick_vibrant.html': {
        'bg_body': '#fff7ed',
        'fg_primary': '#431407',
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
TEMPLATE_SUFFIX = "\n} %}\n{% include 'partials/quick_template_base.html' %}\n"


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
