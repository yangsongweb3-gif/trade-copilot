"""大环境开关（今日环境灯）：把 BTC 趋势、波动、杠杆、美股、美元美债、稳定币、情绪、BTC 现货 ETF 资金流汇总成 🟢🟡🔴。

只描述市场环境，不给操作建议：怎么做由自己判断。
这里是纯函数：输入已经拉好的数据，输出灯色和每一项的理由，不联网，可以直接写单元测试。
阈值先用经验值，以后用回测再调。
"""
from dataclasses import dataclass, field
from datetime import date

from .market import DailyBars
from .rules import fp

GREEN, YELLOW, RED = 'green', 'yellow', 'red'
LIGHT = {GREEN: ('🟢', '绿灯'), YELLOW: ('🟡', '黄灯'), RED: ('🔴', '红灯')}

FUNDING_HOT = 0.0003            # 7 天平均资金费率超过 0.03%/8h 算多头拥挤（平时约 0.01%）
OI_SURGE_PCT = 15               # 7 天持仓量涨超 15%……
OI_PRICE_FLAT_PCT = 3           # ……而 BTC 涨不到 3%：杠杆在堆、价格没跟上
VOL_EXPAND, VOL_QUIET = 1.5, 0.7  # 近 7 天平均振幅是近 30 天的几倍
DXY_MOVE_PCT = 1.5              # 美元指数 20 个交易日涨跌超过 1.5%
US10Y_MOVE = 0.25               # 美债 10 年期收益率 20 个交易日上升超过 0.25 个百分点
STABLE_UP_PCT, STABLE_DOWN_PCT = 2, -1   # 稳定币总量 30 天增减
GREED, FEAR = 80, 20
ETF_FLOW_M = 500                # 近 5 个交易日 ETF 累计净流入超过 5 亿美元算明显


@dataclass(frozen=True)
class Indicator:
    name: str
    score: int | None   # +1 利好 / 0 中性 / -1 利空；None 表示数据缺失，不计分
    text: str
    weight: int = 1


@dataclass(frozen=True)
class MacroData:
    btc: DailyBars                      # BTC 已收盘日线，至少 55 根
    funding: list[float] | None = None  # BTC 永续资金费率（每 8 小时一次），至少 21 次
    oi: list[float] | None = None       # BTC 永续每日持仓量，至少 8 天
    nasdaq: list[float] | None = None
    dxy: list[float] | None = None
    us10y: list[float] | None = None
    stables: list[float] | None = None  # 每天稳定币总量，至少 31 天
    fear_greed: int | None = None
    etf: list[tuple[date, float]] | None = None   # 美国现货 BTC ETF 每日净流入（百万美元），从旧到新
    series: dict[str, list[tuple[date, float]]] = field(default_factory=dict)   # 带日期的原始序列，只给网页画图用
    etf_funds: dict[str, float] = field(default_factory=dict)   # 最新一天各基金净流入（百万美元），只给网页用


@dataclass(frozen=True)
class Regime:
    light: str
    score: int
    reason: str
    indicators: list[Indicator]


def _pct(old: float, new: float) -> float:
    return (new / old - 1) * 100


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _trend(closes: list[float]) -> tuple[int, str] | None:
    """收盘价相对 MA20、MA50 的位置：多头排列 +1，空头排列 -1，纠缠 0。"""
    if len(closes) < 50:
        return None
    c, m20, m50 = closes[-1], _mean(closes[-20:]), _mean(closes[-50:])
    desc = f'收盘 {fp(c)}，MA20 {fp(m20)}'
    if len(closes) >= 25:
        desc += '（向上）' if m20 > _mean(closes[-25:-5]) else '（向下）'
    desc += f'，MA50 {fp(m50)}'
    if c > m20 > m50:
        return 1, desc + '：多头排列'
    if c < m20 < m50:
        return -1, desc + '：空头排列'
    return 0, desc + '：均线纠缠，方向不明'


def btc_trend(bars: DailyBars) -> Indicator:
    t = _trend(bars.closes)
    if t is None:
        return Indicator('BTC 趋势', None, '日线不足 50 根', 2)
    return Indicator('BTC 趋势', t[0], t[1], 2)


def btc_volatility(bars: DailyBars) -> Indicator:
    if len(bars.highs) < 30:
        return Indicator('BTC 波动', None, '日线不足 30 根')
    ranges = [(h - l) / c for h, l, c in zip(bars.highs, bars.lows, bars.closes)]
    r7, r30 = _mean(ranges[-7:]), _mean(ranges[-30:])
    ratio = r7 / r30
    text = f'近 7 天平均日振幅 {r7:.1%}，近 30 天 {r30:.1%}（{ratio:.1f} 倍）'
    if ratio >= VOL_EXPAND:
        return Indicator('BTC 波动', -1, text + '：波动放大')
    if ratio <= VOL_QUIET:
        return Indicator('BTC 波动', 0, text + '：波动收缩，常是大行情前的安静期，等方向出来')
    return Indicator('BTC 波动', 0, text + '：正常')


def leverage(funding: list[float] | None, oi: list[float] | None, btc_closes: list[float]) -> Indicator:
    if not funding:
        return Indicator('杠杆情绪', None, '资金费率数据缺失')
    avg = _mean(funding[-21:])   # 近 7 天
    score, parts, notes = 0, [f'7 天平均资金费率 {avg:.4%}'], []
    if avg > FUNDING_HOT:
        score = -1
        notes.append('多头拥挤')
    elif avg < 0:
        notes.append('费率为负，空头拥挤')
    if oi and len(oi) >= 8 and len(btc_closes) >= 8:
        oi_chg, px_chg = _pct(oi[-8], oi[-1]), _pct(btc_closes[-8], btc_closes[-1])
        parts.append(f'持仓量 7 天 {oi_chg:+.1f}%，BTC {px_chg:+.1f}%')
        if oi_chg > OI_SURGE_PCT and px_chg < OI_PRICE_FLAT_PCT:
            score = -1
            notes.append('杠杆在堆、价格没跟上')
    return Indicator('杠杆情绪', score, '，'.join(parts) + '：' + ('，'.join(notes) or '正常'))


def nasdaq(closes: list[float] | None) -> Indicator:
    t = _trend(closes) if closes else None
    if t is None:
        return Indicator('纳斯达克', None, '数据缺失')
    return Indicator('纳斯达克', t[0], t[1])


def dollar_and_rates(dxy: list[float] | None, us10y: list[float] | None) -> Indicator:
    parts, bad, good = [], False, False
    if dxy and len(dxy) >= 21:
        d = _pct(dxy[-21], dxy[-1])
        parts.append(f'美元指数 {dxy[-1]:.2f}（20 日 {d:+.1f}%）')
        bad, good = d > DXY_MOVE_PCT, d < -DXY_MOVE_PCT
    if us10y and len(us10y) >= 21:
        y = us10y[-1] - us10y[-21]
        parts.append(f'美债 10 年 {us10y[-1]:.2f}%（20 日 {y:+.2f}）')
        bad = bad or y > US10Y_MOVE
    if not parts:
        return Indicator('美元/美债', None, '数据缺失')
    if bad:
        return Indicator('美元/美债', -1, '，'.join(parts) + '：美元或利率走强，压制风险资产')
    if good:
        return Indicator('美元/美债', 1, '，'.join(parts) + '：美元走弱，利好风险资产')
    return Indicator('美元/美债', 0, '，'.join(parts) + '：平稳')


def stablecoins(supply: list[float] | None) -> Indicator:
    if not supply or len(supply) < 31:
        return Indicator('稳定币总量', None, '数据缺失')
    c30, c7 = _pct(supply[-31], supply[-1]), _pct(supply[-8], supply[-1])
    text = f'总量 {supply[-1] / 1e9:,.1f}B 美元，30 天 {c30:+.1f}%，7 天 {c7:+.1f}%'
    if c30 >= STABLE_UP_PCT:
        return Indicator('稳定币总量', 1, text + '：场外资金在进来')
    if c30 <= STABLE_DOWN_PCT:
        return Indicator('稳定币总量', -1, text + '：资金在流出')
    return Indicator('稳定币总量', 0, text + '：平稳')


def fear_greed(value: int | None) -> Indicator:
    if value is None:
        return Indicator('恐惧贪婪', None, '数据缺失')
    if value >= GREED:
        return Indicator('恐惧贪婪', -1, f'{value}：极度贪婪')
    if value <= FEAR:
        return Indicator('恐惧贪婪', 0, f'{value}：极度恐惧')
    mood = '恐惧' if value < 45 else '中性' if value <= 55 else '贪婪'
    return Indicator('恐惧贪婪', 0, f'{value}：{mood}')


def etf_flows(days: list[tuple[date, float]] | None) -> Indicator:
    if not days or len(days) < 5:
        return Indicator('BTC 现货 ETF 资金流', None, '数据缺失')
    last5 = days[-5:]
    total = sum(v for _, v in last5)
    inflow_days = sum(v > 0 for _, v in last5)
    d, v = days[-1]
    text = f'近 5 个交易日净流入 {total:+,.0f}M 美元（{inflow_days} 天流入），最新 {d:%m-%d} {v:+,.1f}M'
    if total > ETF_FLOW_M:
        return Indicator('BTC 现货 ETF 资金流', 1, text + '：资金持续流入')
    if total < -ETF_FLOW_M:
        return Indicator('BTC 现货 ETF 资金流', -1, text + '：资金持续流出')
    return Indicator('BTC 现货 ETF 资金流', 0, text + '：进出不大')


def evaluate_regime(d: MacroData) -> Regime:
    trend = btc_trend(d.btc)
    inds = [trend, btc_volatility(d.btc), leverage(d.funding, d.oi, d.btc.closes),
            nasdaq(d.nasdaq), dollar_and_rates(d.dxy, d.us10y), stablecoins(d.stables), fear_greed(d.fear_greed),
            etf_flows(d.etf)]
    score = sum(i.score * i.weight for i in inds if i.score is not None)
    # BTC 空头排列一票否决：这时候山寨通常跌得比 BTC 更狠
    if trend.score == -1:
        light, reason = RED, 'BTC 空头排列（一票否决）'
    elif score <= -2:
        light, reason = RED, '利空占多数'
    elif trend.score == 1 and score >= 3:
        light, reason = GREEN, 'BTC 多头排列，其他指标也偏正面'
    elif trend.score == 1:
        light, reason = YELLOW, 'BTC 趋势向上，但其他指标拖后腿'
    else:
        light, reason = YELLOW, 'BTC 方向不明'
    return Regime(light, score, reason, inds)


def format_regime(r: Regime) -> str:
    icon, name = LIGHT[r.light]
    mark = {1: '✅', 0: '➖', -1: '⚠️', None: '❔'}
    lines = [f'{icon} 今日环境灯：{name}（综合 {r.score:+d} 分）',
             f'结论：{r.reason}',
             '']
    for i in r.indicators:
        weight = f' ×{i.weight}' if i.weight > 1 else ''
        lines.append(f'{mark[i.score]} {i.name}{weight}：{i.text}')
    return '\n'.join(lines)
