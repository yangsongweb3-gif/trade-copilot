"""币安现货公开行情：24 小时行情和日线。不需要 API Key。"""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import requests

BASE = 'https://api.binance.com'
FAPI = 'https://fapi.binance.com'   # 合约公开数据：只读资金费率、持仓量当情绪指标，不交易合约


@dataclass(frozen=True)
class Ticker:
    symbol: str
    price: float
    pct_24h: float
    quote_volume: float = 0.0   # 24h 成交额（USDT）


@dataclass(frozen=True)
class DailyBars:
    """已收盘的日线（币安按 UTC 0 点切日，即北京时间 8:00 收盘），从旧到新。"""
    symbol: str
    closes: list[float]
    highs: list[float] = field(default_factory=list)
    lows: list[float] = field(default_factory=list)
    quote_volumes: list[float] = field(default_factory=list)   # 每天成交额（USDT）
    dates: list[date] = field(default_factory=list)             # 每根日线的日期（UTC）

    @property
    def last_close(self) -> float:
        return self.closes[-1]

    def ma(self, n: int) -> float | None:
        return sum(self.closes[-n:]) / n if len(self.closes) >= n else None


class Market:
    def __init__(self, proxy: str = '', timeout: float = 10):
        self.session = requests.Session()
        if proxy:
            self.session.proxies.update({'http': proxy, 'https': proxy})
        self.timeout = timeout

    def _get(self, path: str, base: str = BASE, **params):
        r = self.session.get(base + path, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def ticker(self, symbol: str) -> Ticker:
        d = self._get('/api/v3/ticker/24hr', symbol=symbol)
        return Ticker(symbol, float(d['lastPrice']), float(d['priceChangePercent']), float(d['quoteVolume']))

    def all_tickers(self) -> dict[str, Ticker]:
        """所有 USDT 交易对的 24h 行情，一次请求拿全。"""
        return {d['symbol']: Ticker(d['symbol'], float(d['lastPrice']), float(d['priceChangePercent']), float(d['quoteVolume']))
                for d in self._get('/api/v3/ticker/24hr') if d['symbol'].endswith('USDT')}

    def daily(self, symbol: str, days: int = 60) -> DailyBars:
        klines = self._get('/api/v3/klines', symbol=symbol, interval='1d', limit=days + 1)
        closed = klines[:-1]  # 最后一根是今天还没收盘的，不算
        return DailyBars(symbol, [float(k[4]) for k in closed],
                         [float(k[2]) for k in closed], [float(k[3]) for k in closed], [float(k[7]) for k in closed],
                         [_utc(k[0]).date() for k in closed])

    def hourly(self, symbol: str, hours: int = 168) -> list[tuple[datetime, float]]:
        """最近已收盘的小时线 (开盘时间, 收盘价)，从旧到新。"""
        klines = self._get('/api/v3/klines', symbol=symbol, interval='1h', limit=hours + 1)[:-1]
        return [(_utc(k[0]), float(k[4])) for k in klines]

    def today(self, symbol: str) -> tuple[float, float, float]:
        """今天（UTC 0 点起，即北京时间 8 点起）还没收盘的日线：(最高, 最低, 最新价)。"""
        k = self._get('/api/v3/klines', symbol=symbol, interval='1d', limit=1)[0]
        return float(k[2]), float(k[3]), float(k[4])

    def funding_rates(self, symbol: str, n: int = 90) -> list[tuple[datetime, float]]:
        """最近 n 次 (结算时间, 资金费率)，每 8 小时一次，90 次约 30 天，从旧到新。"""
        rows = self._get('/fapi/v1/fundingRate', base=FAPI, symbol=symbol, limit=n)
        return [(_utc(r['fundingTime']), float(r['fundingRate'])) for r in rows]

    def open_interest(self, symbol: str, days: int = 30) -> list[tuple[date, float, float]]:
        """最近每天的 (日期, 持仓量（币）, 持仓价值（USDT）)，从旧到新。币安只保留最近 30 天。"""
        rows = self._get('/futures/data/openInterestHist', base=FAPI, symbol=symbol, period='1d', limit=days)
        return [(_utc(r['timestamp']).date(), float(r['sumOpenInterest']), float(r['sumOpenInterestValue'])) for r in rows]

    def long_short_ratio(self, symbol: str, days: int = 30) -> list[tuple[date, float, float]]:
        """最近每天的 (日期, 多空账户比, 做多账户占比)，从旧到新。"""
        rows = self._get('/futures/data/globalLongShortAccountRatio', base=FAPI, symbol=symbol, period='1d', limit=days)
        return [(_utc(r['timestamp']).date(), float(r['longShortRatio']), float(r['longAccount'])) for r in rows]


def _utc(ms: int) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc)
