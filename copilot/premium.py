"""Coinbase 溢价：Coinbase 的 BTC-USD 比币安 BTC-USDT 贵多少（%）。

Coinbase 是美国机构和散户的主要入口，溢价为正说明美国买盘比全球其他地方积极，为负说明美国在卖。
USDT 偶尔偏离 1 美元，会带来 ±0.05% 左右的误差。不计入综合分。纯函数。
"""
from datetime import datetime


def premium_series(coinbase: list[tuple[datetime, float]], binance: list[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    """按整点对齐两边的小时收盘价，算溢价百分比，从旧到新。"""
    bn = dict(binance)
    return [(t, (px / bn[t] - 1) * 100) for t, px in coinbase if t in bn and bn[t]]


def average(series: list[tuple[datetime, float]], hours: int) -> float | None:
    vals = [v for _, v in series[-hours:]]
    return sum(vals) / len(vals) if vals else None
