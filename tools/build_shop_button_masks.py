"""Compile exact button exclusion masks into reviewable RGBA PNGs and HTML."""
import base64
import json
from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.image_matcher import ImageMatcher


def main():
    buttons = ROOT / 'images/buttons'
    output = buttons / 'masked'
    output.mkdir(exist_ok=True)
    definitions = json.loads((buttons / 'template_masks.json').read_text(encoding='utf-8'))
    matcher = ImageMatcher()
    rows = []
    for name in definitions:
        template = matcher.load_template(buttons / name).copy()
        template[template[:, :, 3] == 0, :3] = 0
        encoded = cv2.imencode('.png', template)[1]
        encoded.tofile(str(output / name))
        if '_backup' in name:
            continue
        original = base64.b64encode((buttons / name).read_bytes()).decode('ascii')
        masked = base64.b64encode(encoded).decode('ascii')
        kept = (template[:, :, 3] > 0).mean()
        rows.append(f'<tr><th>{name}<small>{kept:.1%} retained</small></th>'
                    f'<td><img alt="Original {name}" src="data:image/png;base64,{original}"></td>'
                    f'<td class="checker"><img alt="Masked {name}" src="data:image/png;base64,{masked}"></td></tr>')
    preview = ROOT / 'docs/i18n/secret-shop-button-masks.html'
    preview.write_text('''<!doctype html><html lang="ko"><meta charset="utf-8">
<title>비밀상점 버튼 문자 제외 마스크</title>
<style>body{font:16px system-ui,sans-serif;background:#20252d;color:#eef2f7;margin:32px}
h1{font-size:24px}p{max-width:900px;line-height:1.6}table{border-collapse:collapse;width:100%;max-width:1100px}
th,td{padding:20px;border:1px solid #596373;text-align:left}td{width:34%;height:110px}
img{image-rendering:pixelated;max-width:100%;width:auto;height:auto;zoom:1.7}
small{display:block;color:#b7c3d5;margin-top:8px}.checker{background-color:#949494;
background-image:conic-gradient(#646464 25%,transparent 0 50%,#646464 0 75%,transparent 0);
background-size:16px 16px}</style>
<h1>비밀상점 버튼 문자 제외 마스크</h1>
<p>왼쪽은 원본, 오른쪽은 실제 매칭에 사용하는 마스크입니다. 체크무늬가 보이는 중앙 영역은 비교에서 제외합니다.
버튼 크기와 클릭 중심은 유지하며 구입 버튼의 수량과 활성·비활성 색상은 남깁니다.
원본 PNG는 보존하고 template_masks.json으로 제외 영역을 관리합니다.</p>
<p>영어 화면의 문구 폭·버튼 크기와 실제 실행은 추가 검증이 필요합니다. 같은 테두리의 다른 버튼은 구분할 수 없습니다.</p>
<table><thead><tr><th>파일 / 남는 영역</th><th>원본</th><th>마스크 적용</th></tr></thead><tbody>
''' + '\n'.join(rows) + '</tbody></table></html>', encoding='utf-8')
    print(f'Exported {len(definitions)} RGBA templates: {output}')
    print(f'Preview: {preview}')


if __name__ == '__main__':
    main()
