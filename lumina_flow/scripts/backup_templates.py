import shutil
from pathlib import Path
from datetime import datetime

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
    'templates/detailed_modern.html',
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

stamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
backup_dir = ROOT / 'templates' / f'_checkpoint_{stamp}'
backup_dir.mkdir(parents=True, exist_ok=True)

for rel_path in TEMPLATES:
    src = ROOT / rel_path
    dst = backup_dir / Path(rel_path).name
    if src.exists():
        shutil.copy2(src, dst)
        print('Backed up', rel_path)
    else:
        print('Missing', rel_path)

print('Checkpoint created at', backup_dir)
