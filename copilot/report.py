"""每日日报图片：把首页截成一张长图，给 my_invest_agent 10:30 的发群任务用；配置了 SITE_REPO 时顺带发布网页版。

用法：
  python -m copilot.report          生成今天的图（含个别好友的专属二维码版本）

流程：本进程里临时起一个网页服务 → 拉一遍最新数据（拉不到就不出图，免得把报错页发到群里）
→ 用 Edge 无头模式先量页面高度、再整页截图。顺带也存了今天的快照。
输出到 .env 的 REPORT_DIR，文件名 {REPORT_NAME}-YYYY-MM-DD.png，沿用旧 BTC 日报的路径和名字，发群脚本不用改。
个别好友换二维码：.env 里 REPORT_QR_<QQ号>=二维码图片路径|二维码下的名字，
生成到 REPORT_DIR/variants/{REPORT_NAME}-日期-QQ号.png（发群脚本看到这个文件就直接用）。
"""
import logging
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
import uvicorn

from . import publish
from .agenda import BEIJING
from .config import ROOT, load_env

WIDTH, SCALE = 600, 2           # 接近手机的宽度：手机上缩小得少，小字才看得清；2 倍清晰度
EDGE = [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']
WORK = ROOT / 'data' / 'report'
log = logging.getLogger('copilot.report')


def _edge(args: list[str], timeout: int) -> str:
    exe = next((p for p in EDGE if Path(p).exists()), None)
    if not exe:
        raise FileNotFoundError('找不到 Edge 浏览器')
    r = subprocess.run([exe, '--headless=new', '--disable-gpu', '--hide-scrollbars',
                        f'--user-data-dir={WORK / "edge-profile"}', *args],   # 单独的配置目录，不和平时开的 Edge 冲突
                       capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=timeout,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return r.stdout


def screenshot(url: str, out: Path) -> None:
    """先让页面渲染完、读出整页高度，再按这个高度截图；先写临时文件再改名，发群脚本不会读到半张图。"""
    dom = _edge(['--virtual-time-budget=30000', f'--window-size={WIDTH},2000', '--dump-dom', url], timeout=180)
    m = re.search(r'data-report-h="(\d+)"', dom)
    if not m:
        raise RuntimeError(f'页面没有渲染完：{url}')
    tmp = WORK / 'shot.png'      # Edge 的 --screenshot 不认中文路径，先写到英文路径
    tmp.unlink(missing_ok=True)
    _edge(['--virtual-time-budget=30000', f'--window-size={WIDTH},{m.group(1)}', f'--force-device-scale-factor={SCALE}',
           f'--screenshot={tmp}', url], timeout=180)
    if not tmp.exists() or tmp.stat().st_size < 50_000:
        raise RuntimeError(f'截图失败：{url}')
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + '.part')   # 复制到目标旁边再改名：跨盘也行，改名这一步是原子的
    shutil.copyfile(tmp, part)
    part.replace(out)
    log.info('已生成 %s（%d KB）', out, out.stat().st_size // 1024)


def _serve() -> tuple[uvicorn.Server, str]:
    from .web import app
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    # log_config=None：计划任务用 pythonw 跑，没有控制台，uvicorn 自带的彩色日志会因为拿不到终端而崩
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning', log_config=None))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return server, f'http://127.0.0.1:{port}'
        time.sleep(0.1)
    raise RuntimeError('网页服务没有起来')


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S',
                        handlers=[logging.FileHandler(WORK / 'report.log', encoding='utf-8')]
                        + ([logging.StreamHandler()] if sys.stderr else []))   # pythonw 没有控制台
    env = load_env()
    out_dir = Path(env.get('REPORT_DIR') or WORK)
    name = env.get('REPORT_NAME') or 'BTC消息日报'
    day = datetime.now(BEIJING).date()
    server = None
    try:
        server, base = _serve()
        s = requests.Session()
        s.trust_env = False      # 本机服务不走代理
        s.get(f'{base}/api/regime?refresh=true', timeout=300).raise_for_status()
        s.get(f'{base}/api/news?refresh=true', timeout=120)
        s.get(f'{base}/api/alts', timeout=300)
        screenshot(f'{base}/?report=1', out_dir / f'{name}-{day}.png')
        for key, spec in env.items():
            if key.startswith('REPORT_QR_') and spec:
                target, qr_name = key.removeprefix('REPORT_QR_'), spec.partition('|')[2]
                try:
                    screenshot(f'{base}/?report=1&qr={target}&qn={quote(qr_name)}',
                               out_dir / 'variants' / f'{name}-{day}-{target}.png')
                except Exception as e:   # 专属版失败不影响群里那张；发群脚本会跳过这个人
                    log.warning('%s 的专属二维码版本生成失败：%s', target, e)
        if env.get('SITE_REPO'):
            try:     # 网页版发布失败不影响出图和发群
                site = Path(env.get('SITE_DIR') or WORK / 'site')
                publish.export(base, site, day)
                log.info('网页版%s：%s', '已推送' if publish.push(site, env['SITE_REPO'], day) else '没有变化', env.get('SITE_URL', ''))
            except Exception as e:
                log.warning('网页版发布失败：%s', e)
    except Exception as e:
        log.error('日报图片生成失败：%s', e)
        raise
    finally:
        if server:
            server.should_exit = True


if __name__ == '__main__':
    main()
