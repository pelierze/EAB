"""Export effective exploration crops for language-dependency review.

This is an offline developer tool. It does not alter runtime assets or infer
language support from filenames. Text presence and safe replacements need
visual review and paired captures from the game.
"""
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_support.release_assets import used_images
from src.image_matcher import read_image


def collect(root=ROOT):
    root = Path(root)
    sources, entries = {}, []
    packaged = set(used_images(root))

    def add(group, marker, definition, base):
        path = base / definition['file']
        key = path.relative_to(root).as_posix()
        if key not in sources:
            sources[key] = read_image(path)
        source = sources[key]
        if source is None:
            raise ValueError(f'Missing image: {key}')
        height, width = source.shape[:2]
        crop = definition.get('crop', [0, 0, width, height])
        x, y, w, h = crop
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > width or y+h > height:
            raise ValueError(f'Invalid crop: {group}/{marker}')
        effective = source[y:y+h, x:x+w]
        entries.append(({
            'group': group, 'marker': marker, 'source': key, 'crop': crop,
            'source_size': [width, height],
            'region': definition.get('region'), 'threshold': definition.get('threshold'),
            'max_color_error': definition.get('max_color_error'),
            'packaged': key in packaged,
            'language_review': 'pending_visual_and_paired_screen_review',
        }, effective))

    rec = json.loads((root / 'src/chaos/recruitment_layout.json').read_text(encoding='utf-8'))
    node = json.loads((root / 'src/chaos/node_layout.json').read_text(encoding='utf-8'))
    recruitment = root / 'images/chaos/hero_selection'
    for marker, definition in rec['markers'].items():
        add('recruitment', marker, definition, recruitment)
        for index, filename in enumerate(definition.get('alternate_files', []), 1):
            add('portrait_variant', f'{marker}/{index}', {'file': filename}, recruitment)
    for marker, definition in node['markers'].items():
        add('node', marker, definition, root)
    for index in (1, 2):
        add('theme', f'select_supply_{index}',
            {'file': f'templates/themes/select_supply_{index}.png'}, recruitment)
    templates = root / 'images/chaos/node_progression/templates'
    for path in sorted((templates / 'blocked_choices').glob('*.png')):
        definition = {'file': path.name}
        if path.name in node.get('blocked_choice_crops', {}):
            definition['crop'] = node['blocked_choice_crops'][path.name]
        add('blocked_choice', path.stem, definition, path.parent)
    for path in sorted((templates / 'classes').glob('class_*.png')):
        add('class_icon', path.stem, {'file': path.name}, path.parent)
    return entries


def main():
    entries = collect()
    output = ROOT / 'docs/i18n'
    (output / 'exploration-image-audit.json').write_text(json.dumps({
        'note': 'Crop inventory only. No entry proves English game support. See exploration-english-progress.md.',
        'entries': [entry for entry, _ in entries],
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    cards = []
    for entry, pixels in entries:
        name = entry['group'] + '/' + entry['marker']
        x, y, w, h = entry['crop']
        width, height = entry['source_size']
        source = html.escape('../../' + entry['source'], quote=True)
        cards.append(f'<article id="{html.escape(name)}"><h2>{html.escape(name)}</h2>'
                     f'<p>{html.escape(entry["source"])}</p>'
                     f'<p>crop={entry["crop"]} · region={entry["region"]} · packaged={entry["packaged"]}</p>'
                     f'<svg viewBox="{x} {y} {w} {h}" width="{w}" height="{h}" role="img">'
                     f'<title>{html.escape(name)}</title><image href="{source}" width="{width}" '
                     f'height="{height}"></image></svg></article>')
    (output / 'exploration-image-audit.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Exploration effective image crops</title>
<style>body{background:#20252d;color:#eef2f7;font:14px system-ui;margin:24px}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
article{padding:12px;border:1px solid #64748b;overflow-wrap:anywhere}h2{font-size:16px}
svg{max-width:100%;max-height:220px;overflow:hidden;image-rendering:pixelated}p{font-size:12px}
</style><h1>Exploration effective image crops</h1>
<p>Developer review only. Crops do not establish language independence. Images reference this repository's source files.
Some configured markers are loaded but are not active decision inputs; inspect the calling code too.</p><main>
''' + '\n'.join(cards) + '</main></html>', encoding='utf-8')
    print(f'Exported {len(entries)} effective crops to {output}')


if __name__ == '__main__':
    main()
