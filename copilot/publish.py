"""网页版：把首页导出成静态网页推到 GitHub Pages，手机上能点开下拉框和链接。

只导出首页（BTC 日报）。强势山寨页不导出：那一页写着长期持仓，GitHub Pages 是公开的。
目录：index.html + data/（最新一期）、history/YYYY-MM-DD/（每天一份存档）、static/（样式、脚本、群二维码）。
由 report.py 每天出图后调用；配置在 .env：SITE_REPO（GitHub 仓库地址）、SITE_DIR（发布目录）。
SITE_DIR 可以是代码仓库里的 site/（由 .github/workflows/pages.yml 发布），也可以是单独的目录。
"""
import html
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import requests

STATIC = Path(__file__).resolve().parent / 'static'
ASSETS = ['style.css', 'common.js', 'qq-group-qrcode.png']   # 不带个别好友的专属二维码


def page_html(prefix: str) -> str:
    """首页改成静态网页：资源用相对路径，数据从 data/*.json 读，页脚加历史链接。"""
    page = (STATIC / 'index.html').read_text(encoding='utf-8').replace('/static/', f'{prefix}static/')
    page = page.replace('<script src=', '<script>window.STATIC_SITE = true;</script>\n<script src=', 1)
    return page.replace('</span></footer>', f' · <a href="{prefix}history/">历史日报</a></span></footer>', 1)


def history_index(days: list[str]) -> str:
    items = ''.join(f'<li><a href="{d}/">{d}</a></li>' for d in days)
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BTC 日报 · 历史</title><style>body{{margin:0;background:#f4f1e8;color:#1a1a1a;font:16px/1.9 "PingFang SC","Microsoft YaHei",system-ui,sans-serif}}
main{{max-width:640px;margin:auto;padding:28px 16px}}a{{color:#1c5cab}}</style></head>
<body><main><h1>BTC 日报 · 历史</h1><p><a href="../">← 最新一期</a></p><ul>{items}</ul>
<p style="font-size:13px;color:#5c554d">{html.escape("只整理信息，不构成投资建议。")}</p></main></body></html>'''


def export(base_url: str, site: Path, day: date) -> None:
    s = requests.Session()
    s.trust_env = False      # 本机服务不走代理
    data = {}
    for name in ('regime', 'news'):
        r = s.get(f'{base_url}/api/{name}', timeout=300)
        r.raise_for_status()
        data[name] = r.json()
    (site / 'static').mkdir(parents=True, exist_ok=True)
    for f in ASSETS:
        shutil.copy2(STATIC / f, site / 'static' / f)
    for folder, prefix in ((site, ''), (site / 'history' / day.isoformat(), '../../')):
        (folder / 'data').mkdir(parents=True, exist_ok=True)
        (folder / 'index.html').write_text(page_html(prefix), encoding='utf-8')
        for name, payload in data.items():
            (folder / 'data' / f'{name}.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    days = sorted((p.name for p in (site / 'history').iterdir() if re.fullmatch(r'\d{4}-\d{2}-\d{2}', p.name)), reverse=True)
    (site / 'history' / 'index.html').write_text(history_index(days), encoding='utf-8')
    (site / '.nojekyll').touch()     # 不让 GitHub Pages 用 Jekyll 处理


def _git(site: Path, *args: str) -> str:
    r = subprocess.run(['git', '-C', str(site), *args], capture_output=True, text=True, encoding='utf-8', errors='ignore',
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败：{r.stdout}{r.stderr}")
    return r.stdout.strip()


def push(site: Path, repo: str, day: date) -> bool:
    """提交并推送日报目录，没有变化返回 False。推送用本机 Git Credential Manager 里已有的 GitHub 授权。

    日报目录在代码仓库里（比如 site/）时，只提交这个目录，不碰别的改动，而且只在 main 分支上推；
    不在任何仓库里时，就把它单独建成一个仓库，remote 用 repo。
    """
    site.mkdir(parents=True, exist_ok=True)
    try:
        top = Path(_git(site, 'rev-parse', '--show-toplevel'))
    except RuntimeError:
        top = None
    if top is None:
        _git(site, 'init', '-b', 'main')
        _git(site, 'remote', 'add', 'origin', repo)
        owner = re.search(r'github\.com[/:]([^/]+)/', repo)
        name = owner.group(1) if owner else 'trade-copilot'
        _git(site, 'config', 'user.name', name)
        _git(site, 'config', 'user.email', f'{name}@users.noreply.github.com')
        top = site
    branch = _git(top, 'rev-parse', '--abbrev-ref', 'HEAD')
    if branch != 'main':
        raise RuntimeError(f'当前在 {branch} 分支，日报只在 main 分支上发布')
    path = str(site.resolve().relative_to(top.resolve())) or '.'
    _git(top, 'add', '--', path)
    if not _git(top, 'status', '--porcelain', '--', path):
        return False
    _git(top, 'commit', '-m', f'日报 {day}', '--', path)
    _git(top, 'push', 'origin', 'main')
    return True
