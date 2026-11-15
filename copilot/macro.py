"""币安以外的宏观数据，都是免费公开接口，不需要 Key：

- 美股、美元指数、美债 10 年期收益率：Yahoo Finance
- 稳定币总量：DefiLlama
- 恐惧贪婪指数：alternative.me
- 市值排名：CoinGecko
- 美国现货 BTC ETF 每日净流入：tftc.io（Farside 有 Cloudflare 拦截）
- 本周财经日历：ForexFactory
- Coinbase BTC-USD 小时线（算 Coinbase 溢价）、Deribit BTC 期权行情（期权到期统计）
"""
import html
import re
from datetime import date, datetime, timezone

import requests

YAHOO = 'https://query1.finance.yahoo.com/v8/finance/chart/'
NASDAQ, DXY, US10Y = '^IXIC', 'DX-Y.NYB', '^TNX'
TFTC_ETF = 'https://www.tftc.io/bitcoin-etf-flows'
FF_CALENDAR = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'


def _money(cell: str) -> float | None:
    """'1,082.4' → 1082.4，'(82.4)' → -82.4（括号表示流出），'-' 或空 → None（当天没数据）。"""
    v = cell.replace(',', '').strip()
    if v in ('', '-'):
        return None
    return -float(v.strip('()')) if v.startswith('(') else float(v)


def parse_etf_flows(page: str) -> list[tuple[date, float, dict[str, float]]]:
    """tftc.io 页面里的每日净流入表 → [(日期, 合计, {基金: 净流入})]，单位百万美元，从旧到新。"""
    i = page.find('US spot Bitcoin ETF daily net flows')
    table = page[i:page.find('</table>', i)]
    header, out = [], []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.S):
        cells = [html.unescape(re.sub(r'<[^>]+>', '', c)).strip() for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.S)]
        try:
            day = datetime.strptime(cells[0], '%b %d, %Y').date()
        except (ValueError, IndexError):
            header = cells   # 表头：Date, IBIT, FBTC, ……, Total
            continue
        funds = {name: v for name, cell in zip(header[1:-1], cells[1:-1]) if (v := _money(cell)) is not None}
        out.append((day, _money(cells[-1]) or 0.0, funds))
    return sorted(out, key=lambda r: r[0])


class Macro:
    def __init__(self, proxy: str = '', timeout: float = 15):
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'Mozilla/5.0'   # Yahoo 拒绝没有 UA 的请求
        if proxy:
            self.session.proxies.update({'http': proxy, 'https': proxy})
        self.timeout = timeout

    def _get(self, url: str, **params):
        r = self.session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def yahoo_series(self, symbol: str) -> list[tuple[date, float]]:
        """最近半年的 (日期, 收盘价)，从旧到新。美股盘中时最后一个是实时价。"""
        r = self._get(YAHOO + symbol, range='6mo', interval='1d')['chart']['result'][0]
        closes = r['indicators']['quote'][0]['close']
        return [(datetime.fromtimestamp(t, timezone.utc).date(), c)
                for t, c in zip(r['timestamp'], closes) if c is not None]   # 停牌、节假日会有空值

    def stablecoin_supply(self, days: int = 91) -> list[tuple[date, float]]:
        """最近 days 天的 (日期, 稳定币总市值美元)，从旧到新。"""
        rows = self._get('https://stablecoins.llama.fi/stablecoincharts/all')
        return [(datetime.fromtimestamp(int(r['date']), timezone.utc).date(), float(r['totalCirculatingUSD']['peggedUSD']))
                for r in rows[-days:]]

    def fear_greed(self, days: int = 30) -> list[tuple[date, int]]:
        """最近 days 天的 (日期, 恐惧贪婪指数)，从旧到新。"""
        rows = self._get('https://api.alternative.me/fng/', limit=days)['data']
        return [(datetime.fromtimestamp(int(r['timestamp']), timezone.utc).date(), int(r['value'])) for r in reversed(rows)]

    def market_coins(self) -> dict[str, dict]:
        """市值前 250 名：币种代码（大写）→ {rank, id（CoinGecko ID）, mcap}。代码重名时保留排名靠前的。"""
        rows = self._get('https://api.coingecko.com/api/v3/coins/markets',
                         vs_currency='usd', order='market_cap_desc', per_page=250, page=1)
        coins: dict[str, dict] = {}
        for r in rows:
            if r.get('market_cap_rank'):
                coins.setdefault(r['symbol'].upper(), {'rank': r['market_cap_rank'], 'id': r['id'], 'mcap': r.get('market_cap') or 0})
        return coins

    def llama_revenue(self) -> dict:
        """DefiLlama 近 30 天手续费和协议收入的原始表，加上对应币用的协议、母协议、公链目录。
        几个目录都很大，调用方要缓存。换算在 revenue.gecko_index / by_gecko。"""
        get = lambda path, **q: self.session.get(f'https://api.llama.fi{path}', params=q, timeout=90).json()
        q = {'excludeTotalDataChart': 'true', 'excludeTotalDataChartBreakdown': 'true'}
        return {
            'fees': get('/overview/fees', dataType='dailyFees', **q)['protocols'],
            'revenue': get('/overview/fees', dataType='dailyRevenue', **q)['protocols'],
            'protocols': get('/protocols'),
            'parents': get('/lite/protocols2', b=2)['parentProtocols'],
            'chains': get('/v2/chains'),
        }

    def etf_flows(self) -> list[tuple[date, float, dict[str, float]]]:
        r = self.session.get(TFTC_ETF, timeout=self.timeout)
        r.raise_for_status()
        return parse_etf_flows(r.text)

    def ff_calendar(self) -> list[dict]:
        """ForexFactory 本周财经日历（原始数据，解析在 agenda.parse_ff）。"""
        return self._get(FF_CALENDAR)

    def coinbase_hourly(self) -> list[tuple[datetime, float]]:
        """Coinbase BTC-USD 最近约 2 周的已收盘小时线 (开盘时间, 收盘价)，从旧到新。"""
        rows = self._get('https://api.exchange.coinbase.com/products/BTC-USD/candles', granularity=3600)
        return sorted((datetime.fromtimestamp(r[0], timezone.utc), float(r[4])) for r in rows)[:-1]   # 最后一根还没收盘

    def deribit_options(self) -> list[dict]:
        """Deribit 全部 BTC 期权的行情摘要（原始数据，解析在 options.parse_deribit）。"""
        return self._get('https://www.deribit.com/api/v2/public/get_book_summary_by_currency', currency='BTC', kind='option')['result']
