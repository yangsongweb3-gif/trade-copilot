"""每天把日报卡片发到 X（推特）：一条主推文 + 1 张卡片。不带网址（带链接的推文接口要贵十几倍），网页链接放在个人简介里。

只用 X 官方接口（OAuth 1.0a 用户密钥，.env 的 X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_SECRET），
只发自己的账号。卡片和文案由 report.py 每天 10:10 生成在 site/x/日期/（card.png + tweet.txt）。

用法：
  python -m copilot.xpost --check        只验证密钥（查询当前账号），不发推
  python -m copilot.xpost --dry-run      看看今天会发什么，不发推
  python -m copilot.xpost                发今天的（同一天只发一次）
"""
import argparse
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests

from .agenda import BEIJING
from .config import ROOT, load_env

API = 'https://api.x.com'
LOG = ROOT / 'data' / 'report' / 'xpost.log'
log = logging.getLogger('copilot.xpost')


def _pct(s: str) -> str:
    return quote(s, safe='~-._')


def oauth_header(method: str, url: str, env: dict, query: dict | None = None) -> str:
    """OAuth 1.0a 签名（HMAC-SHA1）。JSON 和 multipart 的请求体不参与签名，只签 URL 上的参数。"""
    oauth = {
        'oauth_consumer_key': env['X_API_KEY'], 'oauth_token': env['X_ACCESS_TOKEN'],
        'oauth_nonce': secrets.token_hex(16), 'oauth_timestamp': str(int(time.time())),
        'oauth_signature_method': 'HMAC-SHA1', 'oauth_version': '1.0',
    }
    params = {**(query or {}), **oauth}
    base = '&'.join([method.upper(), _pct(url), _pct('&'.join(f'{_pct(k)}={_pct(v)}' for k, v in sorted(params.items())))])
    key = f"{_pct(env['X_API_SECRET'])}&{_pct(env['X_ACCESS_SECRET'])}"
    oauth['oauth_signature'] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return 'OAuth ' + ', '.join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


class X:
    def __init__(self, env: dict):
        missing = [k for k in ('X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_SECRET') if not env.get(k)]
        if missing:
            raise RuntimeError(f".env 缺少 {', '.join(missing)}")
        self.env = env
        self.session = requests.Session()
        if env.get('HTTPS_PROXY'):
            self.session.proxies.update({'http': env['HTTPS_PROXY'], 'https': env['HTTPS_PROXY']})

    def _call(self, method: str, path: str, query: dict | None = None, **kwargs) -> dict:
        url = API + path
        r = self.session.request(method, url, params=query, timeout=60,
                                 headers={'Authorization': oauth_header(method, url, self.env, query)}, **kwargs)
        if r.status_code >= 400:
            raise RuntimeError(f'{method} {path} 失败：HTTP {r.status_code} {r.text[:500]}')
        return r.json()

    def me(self) -> dict:
        return self._call('GET', '/2/users/me')['data']

    def upload_image(self, path: Path) -> str:
        with open(path, 'rb') as f:
            data = self._call('POST', '/2/media/upload', files={'media': (path.name, f, 'image/png')},
                              data={'media_category': 'tweet_image', 'media_type': 'image/png'})
        return data['data']['id']

    def post(self, text: str, media_ids: list[str] | None = None, reply_to: str | None = None) -> str:
        body: dict = {'text': text}
        if media_ids:
            body['media'] = {'media_ids': media_ids}
        if reply_to:
            body['reply'] = {'in_reply_to_tweet_id': reply_to}
        return self._call('POST', '/2/tweets', json=body)['data']['id']


def parse_tweet_txt(text: str) -> tuple[str, list[str]]:
    """读 report.py 写的 tweet.txt：【主推文】和【评论区第 N 条】各一段，去掉标题行。"""
    blocks = re.split(r'\n\n(?=【)', text.strip())
    body = lambda b: b.split('\n', 1)[1].strip()
    main = next(body(b) for b in blocks if b.startswith('【主推文】'))
    return main, [body(b) for b in blocks if b.startswith('【评论区')]


def main():
    ap = argparse.ArgumentParser(description='把今天的日报卡片发到 X')
    ap.add_argument('--check', action='store_true', help='只验证密钥')
    ap.add_argument('--dry-run', action='store_true', help='只看会发什么')
    ap.add_argument('--date', help='发哪天的（默认今天，北京时间）')
    args = ap.parse_args()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S',
                        handlers=[logging.FileHandler(LOG, encoding='utf-8')] + ([logging.StreamHandler()] if sys.stderr else []))
    env = load_env()
    x = X(env)
    if args.check:
        me = x.me()
        log.info('密钥有效：@%s（%s）', me['username'], me['name'])
        return
    day = args.date or datetime.now(BEIJING).date().isoformat()
    folder = Path(env.get('SITE_DIR') or ROOT / 'site') / 'x' / day
    card, txt, flag = folder / 'card.png', folder / 'tweet.txt', ROOT / 'data' / 'report' / f'.x-posted-{day}'
    if not card.exists() or not txt.exists():
        log.error('找不到 %s 的卡片或文案（%s），今天不发', day, folder)
        sys.exit(1)
    main_text, replies = parse_tweet_txt(txt.read_text(encoding='utf-8'))
    # 带网址的推文接口约 $0.20 一条，是普通推文的十几倍：文案里出现网址就不发
    if any(re.search(r'https?://|\b[\w-]+\.(?:com|io|net|org|xyz)\b', t) for t in [main_text, *replies]):
        log.error('文案里有网址，按约定不发（带链接的推文很贵）：%s', txt)
        sys.exit(1)
    if args.dry_run:
        log.info('[dry-run] 将发送（配 %s）：\n%s\n回复：%s', card, main_text, json.dumps(replies, ensure_ascii=False))
        return
    if flag.exists():
        log.info('%s 已经发过（%s），跳过', day, flag.read_text(encoding='utf-8').strip())
        return
    media = x.upload_image(card)
    tweet_id = x.post(main_text, [media])
    flag.write_text(tweet_id, encoding='utf-8')    # 主推文发出去就记下，回复失败也不会重发主推文
    log.info('✅ 已发推：https://x.com/i/status/%s', tweet_id)
    for r in replies:
        try:
            x.post(r, reply_to=tweet_id)
        except Exception as e:
            log.warning('回复发送失败：%s', e)


if __name__ == '__main__':
    main()
