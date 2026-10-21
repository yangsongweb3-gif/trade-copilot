"""规则判断：输入计划和行情，输出当前成立的提醒（Signal）。

这里是纯函数：不联网、不读文件、不记状态，所以可以直接写单元测试。
"同一件事只提醒一次"由 state.py 负责：这里每轮都把成立的条件全部报出来。
"""
from dataclasses import dataclass

from .config import Plan, Settings
from .market import DailyBars, Ticker

URGENT, IMPORTANT, INFO = 'urgent', 'important', 'info'


@dataclass(frozen=True)
class Signal:
    key: str        # 去重用的唯一标识，如 aave-a:stop
    level: str      # urgent / important / info
    title: str
    text: str


def fp(v: float) -> str:
    """价格显示：大于 1000 加千分位，小价格保留足够的有效数字。"""
    if v >= 1000:
        return f'{v:,.2f}'
    if v >= 1:
        return f'{v:.4f}'.rstrip('0').rstrip('.')
    return f'{v:.8f}'.rstrip('0').rstrip('.')


def position_size(settings: Settings, entry: float, stop: float, max_usdt: float | None) -> tuple[float, float, float]:
    """按单笔最多亏 risk_per_trade_pct 计算建议仓位，返回 (数量, 金额 USDT, 打到止损时亏多少 USDT)。"""
    budget = settings.account_usdt * settings.risk_per_trade_pct / 100
    qty = budget / (entry - stop)
    if max_usdt is not None:
        qty = min(qty, max_usdt / entry)
    return qty, qty * entry, qty * (entry - stop)


def evaluate(plan: Plan, settings: Settings, tickers: dict[str, Ticker], daily: dict[str, DailyBars]) -> list[Signal]:
    if not plan.enabled:
        return []
    t = tickers[plan.symbol]
    name = plan.symbol.removesuffix('USDT')
    head = f'{name} 现价 {fp(t.price)}（24h {t.pct_24h:+.1f}%）'
    out: list[Signal] = []

    # 取消条件优先：触发后计划作废，其他提醒没有意义
    for c in plan.cancel_if:
        bars = daily[c.symbol]
        if bars.last_close < c.close_below:
            cname = c.symbol.removesuffix('USDT')
            out.append(Signal(f'{plan.id}:cancel:{c.symbol}', URGENT, f'计划作废 · {plan.id}',
                              f'{cname} 日线收盘 {fp(bars.last_close)} 跌破 {fp(c.close_below)}，'
                              f'按规则取消计划「{plan.note}」'))
    if out:
        return out

    if plan.stop is not None and t.price <= plan.stop:
        out.append(Signal(f'{plan.id}:stop', URGENT, f'跌破止损 · {name}',
                          f'{head} 跌破止损 {fp(plan.stop)}。如果已按计划「{plan.note}」买入，按规则止损'))

    if plan.buy_zone:
        low, high = plan.buy_zone
        if low <= t.price <= high:
            text = f'{head} 进入买入区 {fp(low)}–{fp(high)}\n计划：{plan.note}'
            if plan.stop is not None:
                qty, usdt, loss = position_size(settings, t.price, plan.stop, plan.max_usdt)
                text += (f'\n建议仓位：约 {qty:.4g} 枚（{usdt:,.0f} U），止损 {fp(plan.stop)}，'
                         f'打到止损亏约 {loss:,.0f} U（账户 {loss / settings.account_usdt:.1%}）')
            out.append(Signal(f'{plan.id}:buy_zone', IMPORTANT, f'到达买入区 · {name}', text))

    if plan.close_above is not None:
        bars = daily[plan.symbol]
        if bars.last_close > plan.close_above:
            out.append(Signal(f'{plan.id}:close_above', IMPORTANT, f'突破确认 · {name}',
                              f'{name} 日线收盘 {fp(bars.last_close)} 站上 {fp(plan.close_above)}\n'
                              f'计划：{plan.note}\n{head}'))

    for i, target in enumerate(plan.targets, 1):
        if t.price >= target:
            out.append(Signal(f'{plan.id}:target{i}', IMPORTANT, f'到达目标 {i} · {name}',
                              f'{head} 到达目标 {i}：{fp(target)}\n计划：{plan.note}'))

    if plan.close_below_ma:
        bars = daily[plan.symbol]
        ma = bars.ma(plan.close_below_ma)
        if ma is not None and bars.last_close < ma:
            out.append(Signal(f'{plan.id}:ma{plan.close_below_ma}', IMPORTANT, f'跌破 MA{plan.close_below_ma} · {name}',
                              f'{name} 日线收盘 {fp(bars.last_close)} 低于 {plan.close_below_ma} 日均线 {fp(ma)}\n'
                              f'计划：{plan.note}'))

    if t.pct_24h >= settings.no_chase_pct_24h:
        out.append(Signal(f'{plan.symbol}:no_chase', IMPORTANT, f'按规则不追 · {name}',
                          f'{head}，24 小时涨幅超过 {settings.no_chase_pct_24h:g}%，按规则不追'))
    return out


def symbols_needed(plans: list[Plan]) -> tuple[set[str], set[str]]:
    """返回 (要拉 24h 行情的币, 要拉日线的币)。"""
    tick, day = set(), set()
    for p in plans:
        if not p.enabled:
            continue
        tick.add(p.symbol)
        if p.close_above is not None or p.close_below_ma:
            day.add(p.symbol)
        day.update(c.symbol for c in p.cancel_if)
    return tick, day
