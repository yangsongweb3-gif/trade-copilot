"""BTC 期权到期：Deribit 每周五 08:00 UTC（北京时间 16:00）交割；当月最后一个周五是月度，3/6/9/12 月的是季度，量最大。

用 Deribit 公开行情算每个到期日的未平仓量、认沽认购比和最大痛点（期权买方整体亏得最多的价位）。
纯函数，拉取在 macro.Macro.deribit_options。
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .agenda import Event

MONTHS = {m: i for i, m in enumerate(['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'], 1)}
DERIBIT_URL = 'https://www.deribit.com/options/BTC'


@dataclass(frozen=True)
class Expiry:
    time: datetime                  # 交割时间 08:00 UTC
    kind: str                       # 周度 / 月度 / 季度
    oi_btc: float = 0.0             # 未平仓量（1 张 = 1 BTC）
    notional_usd: float = 0.0
    put_call: float | None = None   # 认沽未平仓 / 认购未平仓
    max_pain: float | None = None


def expiry_kind(d: date) -> str:
    last_friday = (d + timedelta(days=7)).month != d.month
    if last_friday and d.month in (3, 6, 9, 12):
        return '季度'
    return '月度' if last_friday else '周度'


def _at_8(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 8, tzinfo=timezone.utc)


def parse_deribit(rows: list[dict]) -> list[Expiry]:
    """Deribit 期权行情 → 每个周五到期日的统计（Deribit 还有每日到期的，量小，不看）。"""
    groups: dict[date, dict] = {}
    for r in rows:
        m = re.match(r'BTC-(\d{1,2})([A-Z]{3})(\d{2})-(\d+)-([CP])$', r.get('instrument_name', ''))
        if not m:
            continue
        d = date(2000 + int(m[3]), MONTHS[m[2]], int(m[1]))
        g = groups.setdefault(d, {'C': {}, 'P': {}, 'px': 0.0})
        side, strike = g[m[5]], float(m[4])
        side[strike] = side.get(strike, 0.0) + float(r.get('open_interest') or 0)
        g['px'] = float(r.get('underlying_price') or g['px'])
    out = []
    for d, g in sorted(groups.items()):
        if d.weekday() != 4:
            continue
        calls, puts = g['C'], g['P']
        oi_c, oi_p = sum(calls.values()), sum(puts.values())
        strikes = sorted(set(calls) | set(puts))
        # 到期价为 k 时期权买方能拿回的总价值；最大痛点就是让这个值最小的价位
        payout = lambda k: sum(oi * max(0.0, k - s) for s, oi in calls.items()) + sum(oi * max(0.0, s - k) for s, oi in puts.items())
        out.append(Expiry(_at_8(d), expiry_kind(d), oi_c + oi_p, (oi_c + oi_p) * g['px'],
                          oi_p / oi_c if oi_c else None, min(strikes, key=payout) if strikes else None))
    return out


def option_events(expiries: list[Expiry], now: datetime, days: int = 8) -> list[Event]:
    """从今天起 days 天里的每个周五都列一条；Deribit 拿不到时只有日期，没有统计。"""
    stats = {e.time: e for e in expiries}
    today = now.astimezone(timezone.utc).date()
    out = []
    for i in range(days + 1):
        d = today + timedelta(days=i)
        if d.weekday() != 4:
            continue
        e = stats.get(_at_8(d)) or Expiry(_at_8(d), expiry_kind(d))
        note = ' · '.join(x for x in [
            e.oi_btc and f'未平仓 {e.oi_btc / 1e4:.1f} 万 BTC（≈${e.notional_usd / 1e9:.1f}B）',
            e.max_pain and f'最大痛点 ${e.max_pain:,.0f}',
            e.put_call is not None and f'认沽/认购 {e.put_call:.2f}',
        ] if x)
        out.append(Event(e.time, f'BTC 期权到期（{e.kind}）', 'medium' if e.kind == '周度' else 'high', url=DERIBIT_URL, note=note))
    return out
