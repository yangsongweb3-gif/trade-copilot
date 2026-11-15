"""真实收入：把 DefiLlama 的手续费、协议收入按 CoinGecko 的币对应起来。

DefiLlama 的收入表按协议和公链列（Uniswap V3、Hyperliquid Perps、Solana 链……），不带币的 ID；
用它的协议目录（子协议 → 母协议）和公链目录找到 CoinGecko ID，再把同一个币下的各条加起来。
口径以 DefiLlama 为准："手续费"是用户付出去的，"收入"是协议自己留下的。纯函数。
"""
from collections import defaultdict

MIN_REVENUE = 10_000   # 30 天收入不到 1 万美元，当作没有收入


def gecko_index(protocols: list[dict], parents: list[dict], chains: list[dict]) -> dict[str, str]:
    """DefiLlama 的 defillamaId（协议是数字，公链是 chain#名字）→ CoinGecko ID。"""
    parent_gecko = {p['id']: p.get('gecko_id') for p in parents}
    out = {}
    for p in protocols:
        g = p.get('gecko_id') or parent_gecko.get(p.get('parentProtocol'))
        if g:
            out[str(p['id'])] = g
    for c in chains:
        if c.get('gecko_id'):
            out['chain#' + c['name'].lower()] = c['gecko_id']
    return out


def by_gecko(rows: list[dict], index: dict[str, str]) -> dict[str, float]:
    """收入表里的每一条按币加总近 30 天的数（美元）。"""
    total: dict[str, float] = defaultdict(float)
    for r in rows:
        g = index.get(str(r.get('defillamaId')))
        if g:
            total[g] += r.get('total30d') or 0
    return dict(total)


def price_to_sales(mcap: float | None, revenue30d: float | None) -> float | None:
    """市销率：市值是年化收入的多少倍。没有收入（或太少）返回 None。"""
    if not mcap or not revenue30d or revenue30d < MIN_REVENUE:
        return None
    return mcap / (revenue30d * 365 / 30)
