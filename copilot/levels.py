"""BTC 关键价位：从均线、今日高低点、近期波段高低点、整数关口里挑离现价最近的几个。

只是参考位置，不是买卖建议。纯函数，不联网。
"""
from dataclasses import dataclass

from .market import DailyBars

ROUND_STEP = 5000       # BTC 的整数关口间隔
MERGE_PCT = 0.2         # 两个价位相差不到 0.2% 只留离现价近的那个


@dataclass(frozen=True)
class Level:
    price: float
    label: str


def _extreme(bars: DailyBars, days: int, high: bool) -> Level | None:
    """最近 days 根已收盘日线里的最高点 / 最低点，标上日期。"""
    if not bars.highs or not bars.dates:
        return None
    values = (bars.highs if high else bars.lows)[-days:]
    dates = bars.dates[-days:]
    pick = max if high else min
    i = values.index(pick(values))
    return Level(values[i], f"{dates[i]:%m/%d} {'高点' if high else '低点'}")


def key_levels(bars: DailyBars, price: float, today_high: float, today_low: float,
               n_support: int = 4, n_resist: int = 3) -> tuple[list[Level], list[Level]]:
    """返回 (支撑位从近到远, 压力位从近到远)。"""
    cand = [Level(today_low, '今日低点'), Level(today_high, '今日高点')]
    for n in (20, 50, 200):
        ma = bars.ma(n)
        if ma is not None:
            cand.append(Level(ma, f'MA{n}'))
    for days, high in ((7, False), (30, False), (30, True)):
        lv = _extreme(bars, days, high)
        if lv:
            cand.append(lv)
    base = price // ROUND_STEP * ROUND_STEP
    cand += [Level(base, '整数关口'), Level(base + ROUND_STEP, '整数关口')]

    kept: list[Level] = []
    for lv in sorted(cand, key=lambda lv: abs(lv.price - price)):
        if all(abs(lv.price - k.price) / price * 100 >= MERGE_PCT for k in kept):
            kept.append(lv)
    support = sorted((lv for lv in kept if lv.price < price), key=lambda lv: -lv.price)[:n_support]
    resist = sorted((lv for lv in kept if lv.price >= price), key=lambda lv: lv.price)[:n_resist]
    return support, resist
