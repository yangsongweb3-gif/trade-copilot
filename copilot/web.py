"""本地网页：浏览器打开看今日环境灯。

用法：
  python -m copilot.web            打开 http://127.0.0.1:8000
  python -m copilot.web --port 8080
  python -m copilot.web --open     启动后自动打开浏览器（start-web.bat 就是这样）

默认只监听本机。以后放公网前要先加登录和 HTTPS：现在页面只有公开行情，
但以后会接持仓和计划，这些属于个人信息。
"""
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import webbrowser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import snapshot
from .agenda import BEIJING, fomc_events, parse_ff, upcoming
from .changes import daily_changes
from .config import load_env, load_plans
from .macro import Macro
from .levels import key_levels
from .main import _try, collect_macro
from .market import Market
from .news import News, NewsItem
from .options import option_events, parse_deribit
from .regime import LIGHT, evaluate_regime
from .scanner import AltScore, rank_alts, universe

CACHE_SECONDS = 600     # 日线级别的数据，10 分钟内重复打开页面不重新拉
NEWS_CACHE_SECONDS = 300
CHART_DAYS = 60
STATIC = Path(__file__).resolve().parent / 'static'
SNAP_DIR = Path(__file__).resolve().parent.parent / 'data' / 'snapshots'

log = logging.getLogger('copilot.web')
app = FastAPI(title='trade-copilot', docs_url=None, redoc_url=None, openapi_url=None)
_env = load_env()
_plans = load_plans()
_market = Market(proxy=_env.get('HTTPS_PROXY', ''))
_macro = Macro(proxy=_env.get('HTTPS_PROXY', ''))
_news = News(proxy=_env.get('HTTPS_PROXY', ''))
app.mount('/static', StaticFiles(directory=STATIC), name='static')   # 二维码等图片
_lock = threading.Lock()
_cache: dict = {'at': 0.0, 'data': None}
_news_cache: dict = {'at': 0.0, 'data': None}
_news_lock = threading.Lock()
_alts_cache: dict = {'at': 0.0, 'data': None}
_alts_lock = threading.Lock()
CANDIDATES = 10


def _ma_series(closes: list[float], n: int) -> list[float | None]:
    return [sum(closes[i - n + 1:i + 1]) / n if i >= n - 1 else None for i in range(len(closes))]


def _day(d: date) -> str:
    """日线给日期；资金费率、溢价这种按小时的给到分钟，换成北京时间。"""
    return d.astimezone(BEIJING).strftime('%Y-%m-%d %H:%M') if isinstance(d, datetime) else d.isoformat()


def build_levels(btc) -> dict | None:
    today = _try('今日 K 线', _market.today, 'BTCUSDT')
    if not today:
        return None
    high, low, price = today
    support, resist = key_levels(btc, price, high, low)
    as_dict = lambda lvs: [{'price': lv.price, 'label': lv.label} for lv in lvs]
    return {'price': price, 'support': as_dict(support), 'resistance': as_dict(resist)}


def build_agenda() -> list[dict]:
    """本周日历拿不到时，至少还有议息日程。"""
    rows = _try('财经日历', _macro.ff_calendar) or []
    now = datetime.now(timezone.utc)
    options = option_events(parse_deribit(_try('Deribit 期权', _macro.deribit_options) or []), now)
    events = upcoming(parse_ff(rows) + fomc_events() + options, now)
    return [{'time': e.time.astimezone(timezone.utc).isoformat(), 'title': e.title, 'impact': e.impact,
             'forecast': e.forecast, 'previous': e.previous, 'url': e.url, 'note': e.note,
             'items': [{'title': t, 'forecast': f, 'previous': p} for t, f, p in e.items]} for e in events]


def _asof(data, levels: dict | None) -> dict:
    """每块数据截至什么时候，页面上标在旁边，免得实时价和昨天收盘价混在一起看。"""
    s, bj = data.series, lambda t: t.astimezone(BEIJING)
    last = lambda k: s[k][-1][0] if s.get(k) else None
    out = {'btc': f'收盘 {data.btc.dates[-1]:%m-%d}'}
    if levels:
        out['levels'] = f'实时 {datetime.now(BEIJING):%H:%M}'
    if last('funding'):
        out['funding'] = f"{bj(last('funding')):%m-%d %H:%M}"
    if last('premium'):
        out['premium'] = f"{bj(last('premium')):%m-%d %H}:00"
    if last('etf'):
        out['etf'] = f"美股 {last('etf'):%m-%d}"
    for k in ('fng', 'nasdaq', 'dxy', 'us10y', 'stables'):
        if last(k):
            out[k] = f'{last(k):%m-%d}'
    return out


def build_payload() -> dict:
    data = collect_macro(_market, _macro)
    r = evaluate_regime(data)
    levels = build_levels(data.btc)
    s = data.series
    # 今天的快照：先读之前最近的一份用来对比，再把今天的存下（同一天会覆盖）
    snap = {'date': datetime.now(BEIJING).date().isoformat(), 'saved_at': datetime.now(BEIJING).strftime('%H:%M'),
            'light': r.light, 'score': r.score, 'scores': {i.name: i.score for i in r.indicators},
            'btc_close': data.btc.closes[-1], 'price': levels and levels['price']}
    today = datetime.now(BEIJING).date()
    prev = snapshot.previous(SNAP_DIR, today)
    snapshot.save(SNAP_DIR, today, snap)
    vals = lambda k: [v for _, v in s[k]] if s.get(k) else None
    changes = daily_changes(snap, prev, data.btc.closes, data.btc.dates, vals('funding'), s.get('etf'), s.get('fng'), s.get('premium'))
    closes = data.btc.closes
    dates = [d.isoformat() for d in data.btc.dates]
    ma20, ma50 = _ma_series(closes, 20), _ma_series(closes, 50)
    return {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'light': r.light,
        'light_name': LIGHT[r.light][1],
        'score': r.score,
        'reason': r.reason,
        'indicators': [{'name': i.name, 'score': i.score, 'weight': i.weight, 'text': i.text} for i in r.indicators],
        'btc': {'dates': dates[-CHART_DAYS:], 'closes': closes[-CHART_DAYS:],
                'ma20': ma20[-CHART_DAYS:], 'ma50': ma50[-CHART_DAYS:]},
        # 宏观序列整段给出（约半年），网页自己算涨跌幅和均线
        'macro': {k: {'dates': [_day(d) for d, _ in s], 'values': [v for _, v in s]} for k, s in data.series.items()},
        'etf_funds': data.etf_funds,
        'levels': levels,
        'agenda': build_agenda(),
        'changes': [{'text': c.text, 'tone': c.tone} for c in changes],
        'first_day': prev is None,
        'history': [{'date': h['date'], 'light': h['light'], 'score': h['score']} for h in snapshot.history(SNAP_DIR)],
        'asof': _asof(data, levels),
    }


@app.get('/api/regime')
def api_regime(refresh: bool = False) -> dict:
    with _lock:
        if refresh or _cache['data'] is None or time.time() - _cache['at'] > CACHE_SECONDS:
            _cache['data'], _cache['at'] = build_payload(), time.time()
        return _cache['data']


def _alt(a: AltScore) -> dict:
    return {'name': a.name, 'rank': a.rank, 'price': a.price, 'pct_24h': a.pct_24h, 'quote_volume': a.quote_volume,
            'rs7': a.rs7, 'rs14': a.rs14, 'vol_ratio': a.vol_ratio, 'above_ma20': a.above_ma20,
            'no_chase': a.no_chase, 'volume_up': a.volume_up, 'strong': a.strong, 'vs_btc': a.vs_btc}


def build_alts() -> dict:
    cfg = _plans.scanner
    tickers = _market.all_tickers()
    syms = universe(_macro.market_cap_ranks(), tickers, cfg)
    btc = _market.daily('BTCUSDT', days=30)
    with ThreadPoolExecutor(8) as pool:   # 几十个币的日线并发拉，单个失败就跳过
        futures = {s: pool.submit(_market.daily, s, 30) for s in syms}
    bars = {}
    for s, f in futures.items():
        try:
            bars[s] = f.result()
        except Exception as e:
            log.warning('%s 日线获取失败：%s', s, e)
    scored = rank_alts(btc, bars, tickers, syms, _plans.settings.no_chase_pct_24h)
    return {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'hold': cfg.hold, 'rank_min': cfg.rank_min, 'rank_max': cfg.rank_max,
        'min_quote_volume': cfg.min_quote_volume, 'no_chase_pct': _plans.settings.no_chase_pct_24h,
        'candidates': [_alt(a) for a in scored if a.strong][:CANDIDATES],
        'all': [_alt(a) for a in scored],
    }


@app.get('/api/alts')
def api_alts(refresh: bool = False) -> dict:
    with _alts_lock:
        if refresh or _alts_cache['data'] is None or time.time() - _alts_cache['at'] > CACHE_SECONDS:
            _alts_cache['data'], _alts_cache['at'] = build_alts(), time.time()
        return _alts_cache['data']


def _item(n: NewsItem) -> dict:
    return {'source': n.source, 'title': n.title, 'url': n.url, 'time': n.time.isoformat(),
            'summary': n.summary, 'tags': n.tags, 'danger': n.danger}


def build_news() -> dict:
    """首页只看行业快讯；币安公告（上新、下架）跟 BTC 关系不大，不放首页。"""
    try:
        return {'flash': [_item(n) for n in _news.panews()], 'errors': []}
    except Exception as e:
        log.warning('PANews 获取失败：%s', e)
        return {'flash': [], 'errors': ['PANews']}


@app.get('/api/news')
def api_news(refresh: bool = False) -> dict:
    with _news_lock:
        if refresh or _news_cache['data'] is None or time.time() - _news_cache['at'] > NEWS_CACHE_SECONDS:
            _news_cache['data'], _news_cache['at'] = build_news(), time.time()
        return _news_cache['data']


@app.get('/')
def index() -> FileResponse:
    return FileResponse(STATIC / 'index.html')


@app.get('/qr/{target}')
def qr_image(target: str) -> FileResponse:
    """日报图片给个别好友换的二维码：只认 .env 里配置过的 REPORT_QR_<QQ号>。"""
    spec = _env.get(f'REPORT_QR_{target}', '') if target.isdigit() else ''
    path = Path(spec.partition('|')[0])
    if not spec or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@app.get('/alts')
def alts_page() -> FileResponse:
    return FileResponse(STATIC / 'alts.html')


def main():
    import uvicorn
    ap = argparse.ArgumentParser(description='trade-copilot 本地网页')
    ap.add_argument('--host', default='127.0.0.1', help='默认只允许本机访问')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--open', action='store_true', help='启动后自动打开浏览器')
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
    url = f'http://{args.host}:{args.port}'
    print(f'打开浏览器访问 {url}（关掉这个窗口就停止）')
    if args.open:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
