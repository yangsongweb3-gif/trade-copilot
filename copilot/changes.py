"""今日变化：和前一天比，列出变了的事情。只描述变化，不给建议。

- 直接从数据序列算，第一天就有：BTC 收盘穿越均线、单日大涨大跌、资金费率翻转、ETF 连续流入流出、
  恐惧贪婪换区、Coinbase 溢价翻转
- 对比前一天的快照，第二天起才有：灯色、综合分、各项打分
纯函数。
"""
from dataclasses import dataclass
from datetime import date, datetime

from .regime import FEAR, GREED, LIGHT

BIG_MOVE_PCT = 3        # 日涨跌超过 3% 算大
ETF_STREAK = 3          # 连续 3 天同向算连续
ETF_BIG_M = 500         # 单日净流入流出超过 5 亿美元算大
SCORE_NAME = {1: '利好', 0: '中性', -1: '利空', None: '缺失'}
LIGHT_RANK = {'red': 0, 'yellow': 1, 'green': 2}


@dataclass(frozen=True)
class Change:
    text: str
    tone: str       # up / down / flat：只决定箭头方向和颜色


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def snapshot_changes(cur: dict, prev: dict | None) -> list[Change]:
    if not prev:
        return []
    out = []
    if cur['light'] != prev['light']:
        tone = 'up' if LIGHT_RANK[cur['light']] > LIGHT_RANK[prev['light']] else 'down'
        out.append(Change(f"环境灯：{LIGHT[prev['light']][1]} → {LIGHT[cur['light']][1]}", tone))
    elif cur['score'] != prev['score']:
        out.append(Change(f"综合分：{prev['score']:+d} → {cur['score']:+d}", 'up' if cur['score'] > prev['score'] else 'down'))
    for name, s in cur['scores'].items():
        p = prev.get('scores', {}).get(name, s)
        if s != p and s is not None and p is not None:
            out.append(Change(f'{name}：{SCORE_NAME[p]} → {SCORE_NAME[s]}', 'up' if s > p else 'down'))
    return out


def ma_cross(closes: list[float], n: int) -> Change | None:
    """昨天的收盘和前天相比，有没有穿过 n 日均线。"""
    if len(closes) < n + 2:
        return None
    ma_now, ma_before = _mean(closes[-n:]), _mean(closes[-n - 1:-1])
    if closes[-2] <= ma_before and closes[-1] > ma_now:
        return Change(f'BTC 收盘站上 MA{n}（{ma_now:,.0f}）', 'up')
    if closes[-2] >= ma_before and closes[-1] < ma_now:
        return Change(f'BTC 收盘跌破 MA{n}（{ma_now:,.0f}）', 'down')
    return None


def big_move(closes: list[float], dates: list[date]) -> Change | None:
    if len(closes) < 2:
        return None
    pct = (closes[-1] / closes[-2] - 1) * 100
    if abs(pct) < BIG_MOVE_PCT:
        return None
    return Change(f"BTC {dates[-1]:%m-%d} 收{'涨' if pct > 0 else '跌'} {abs(pct):.1f}%", 'up' if pct > 0 else 'down')


def funding_flip(rates: list[float]) -> Change | None:
    if len(rates) < 2 or (rates[-1] > 0) == (rates[-2] > 0):
        return None
    return Change(f"资金费率转{'正' if rates[-1] > 0 else '负'}（{rates[-1] * 100:.4f}%）", 'up' if rates[-1] > 0 else 'down')


def etf_streak(days: list[tuple[date, float]]) -> Change | None:
    if not days:
        return None
    sign = days[-1][1] > 0
    n = 0
    for _, v in reversed(days):
        if (v > 0) != sign or v == 0:
            break
        n += 1
    total = sum(v for _, v in days[-n:])
    word = '净流入' if sign else '净流出'
    tone = 'up' if sign else 'down'
    if n >= ETF_STREAK:
        return Change(f'BTC 现货 ETF 连续 {n} 个交易日{word}，累计 {total / 1000:+.2f}B 美元', tone)
    d, v = days[-1]
    if abs(v) >= ETF_BIG_M:
        return Change(f'BTC 现货 ETF {d:%m-%d} 单日{word} {abs(v):,.0f}M 美元', tone)
    return None


def fng_zone(v: int) -> str:
    if v >= GREED:
        return '极度贪婪'
    if v <= FEAR:
        return '极度恐惧'
    return '恐惧' if v < 45 else '中性' if v <= 55 else '贪婪'


def fng_change(history: list[tuple[date, int]]) -> Change | None:
    if len(history) < 2:
        return None
    (_, a), (_, b) = history[-2], history[-1]
    if fng_zone(a) == fng_zone(b):
        return None
    return Change(f'恐惧贪婪：{fng_zone(a)} → {fng_zone(b)}（{a} → {b}）', 'up' if b > a else 'down')


def premium_flip(series: list[tuple[datetime, float]]) -> Change | None:
    """最近 24 小时平均和再之前 24 小时平均的正负不同。"""
    if len(series) < 48:
        return None
    now, before = _mean([v for _, v in series[-24:]]), _mean([v for _, v in series[-48:-24]])
    if (now > 0) == (before > 0):
        return None
    return Change(f"Coinbase 溢价转{'正' if now > 0 else '负'}（24 小时平均 {now:+.3f}%）", 'up' if now > 0 else 'down')


def daily_changes(cur: dict, prev: dict | None, closes: list[float], dates: list[date], funding: list[float] | None,
                  etf: list[tuple[date, float]] | None, fng: list[tuple[date, int]] | None,
                  premium: list[tuple[datetime, float]] | None) -> list[Change]:
    found = snapshot_changes(cur, prev) + [
        ma_cross(closes, 20), ma_cross(closes, 50), big_move(closes, dates),
        funding_flip(funding or []), etf_streak(etf or []), fng_change(fng or []), premium_flip(premium or []),
    ]
    return [c for c in found if c]
