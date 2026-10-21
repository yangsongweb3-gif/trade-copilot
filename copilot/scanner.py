"""强势山寨扫描：在市值排名区间里，找最近 7 天、14 天都跑赢 BTC 的币。

长期持仓（plans.yaml 的 scanner.hold）不参与；扫描结果只用来挑山寨短线的候选，买不买还要看环境灯和自己的计划。
这里是纯函数：输入已经拉好的行情，输出排好序的结果，不联网，可以直接写单元测试。
"""
from dataclasses import dataclass

from .config import Scanner
from .market import DailyBars, Ticker

# 稳定币、包装币、黄金代币：价格跟着别的东西走，比强弱没有意义
EXCLUDE = {
    'USDT', 'USDC', 'FDUSD', 'TUSD', 'DAI', 'USDE', 'USDS', 'USD1', 'PYUSD', 'RLUSD', 'USDD', 'USDP', 'BFUSD', 'USDG', 'EURI',
    'WBTC', 'WETH', 'STETH', 'WSTETH', 'WBETH', 'CBBTC', 'BTCB', 'WEETH',
    'PAXG', 'XAUT',
}
STABLE_RANGE = 1.03     # 30 天最高收盘 / 最低收盘不到 3%，当作锚定类资产排除
VOL_UP = 1.5            # 近 7 天平均成交额是近 30 天的 1.5 倍以上算放量


@dataclass(frozen=True)
class AltScore:
    symbol: str             # SUIUSDT
    name: str               # SUI
    rank: int               # 市值排名
    price: float
    pct_24h: float
    quote_volume: float     # 24h 成交额（USDT）
    rs7: float              # 7 天比 BTC 多涨的百分点
    rs14: float
    vol_ratio: float        # 近 7 天平均成交额 / 近 30 天
    above_ma20: bool
    no_chase: bool          # 24h 涨幅超过不追线
    vs_btc: list[float]     # 相对 BTC 的走势，第一天 = 100，往上就是跑赢

    @property
    def score(self) -> float:
        return 0.6 * self.rs7 + 0.4 * self.rs14

    @property
    def strong(self) -> bool:
        return self.rs7 > 0 and self.rs14 > 0

    @property
    def volume_up(self) -> bool:
        return self.vol_ratio >= VOL_UP


def universe(ranks: dict[str, int], tickers: dict[str, Ticker], cfg: Scanner) -> dict[str, int]:
    """要扫描的交易对 → 市值排名：排名在区间内、不是长期持仓、币安有 USDT 交易对、成交额够。"""
    out = {}
    for name, rank in ranks.items():
        sym = name + 'USDT'
        if (cfg.rank_min <= rank <= cfg.rank_max and name not in cfg.hold and name not in EXCLUDE
                and sym in tickers and tickers[sym].quote_volume >= cfg.min_quote_volume):
            out[sym] = rank
    return out


def _ret(closes: list[float], days: int) -> float:
    return (closes[-1] / closes[-1 - days] - 1) * 100


def score_alt(symbol: str, rank: int, bars: DailyBars, ticker: Ticker, btc: DailyBars, no_chase_pct: float) -> AltScore | None:
    """不够 21 根日线（新币）或者价格几乎不动（锚定类资产）返回 None。"""
    c = bars.closes
    if len(c) < 21 or len(btc.closes) < 15:
        return None
    if max(c[-30:]) / min(c[-30:]) < STABLE_RANGE:
        return None
    n = min(len(c), len(btc.closes))
    ratio = [a / b for a, b in zip(c[-n:], btc.closes[-n:])]
    qv = bars.quote_volumes or [0.0]
    vol_ratio = (sum(qv[-7:]) / len(qv[-7:])) / (sum(qv[-30:]) / len(qv[-30:])) if sum(qv[-30:]) else 0.0
    return AltScore(
        symbol, symbol.removesuffix('USDT'), rank, ticker.price, ticker.pct_24h, ticker.quote_volume,
        rs7=_ret(c, 7) - _ret(btc.closes, 7), rs14=_ret(c, 14) - _ret(btc.closes, 14),
        vol_ratio=vol_ratio, above_ma20=c[-1] > bars.ma(20), no_chase=ticker.pct_24h >= no_chase_pct,
        vs_btc=[r / ratio[0] * 100 for r in ratio],
    )


def rank_alts(btc: DailyBars, bars: dict[str, DailyBars], tickers: dict[str, Ticker], ranks: dict[str, int],
              no_chase_pct: float) -> list[AltScore]:
    """全部扫描结果，按强弱分从高到低。"""
    scored = [score_alt(sym, ranks[sym], b, tickers[sym], btc, no_chase_pct) for sym, b in bars.items()]
    return sorted((s for s in scored if s), key=lambda s: s.score, reverse=True)
