from datetime import date

from copilot.macro import parse_etf_flows
from copilot.market import DailyBars
from copilot.regime import (GREEN, RED, YELLOW, MacroData, btc_trend, btc_volatility, dollar_and_rates, etf_flows,
                            evaluate_regime, fear_greed, format_regime, leverage, stablecoins)


def bars(closes, range_pct=0.02):
    """按收盘价造日线，每天振幅固定为 range_pct。"""
    half = [c * range_pct / 2 for c in closes]
    return DailyBars('BTCUSDT', closes, [c + h for c, h in zip(closes, half)], [c - h for c, h in zip(closes, half)])


UP = [80000 + i * 100 for i in range(60)]       # 稳步上涨：收盘 > MA20 > MA50
DOWN = [90000 - i * 100 for i in range(60)]     # 稳步下跌：收盘 < MA20 < MA50
FLAT = [80000.0] * 60


def test_btc_trend():
    assert btc_trend(bars(UP)).score == 1
    assert btc_trend(bars(DOWN)).score == -1
    assert btc_trend(bars(FLAT)).score == 0
    assert btc_trend(bars(UP[:40])).score is None      # 不够 50 根不下结论


def test_volatility_expansion():
    b = DailyBars('BTCUSDT', FLAT, [80800.0] * 53 + [84000.0] * 7, [79200.0] * 53 + [76000.0] * 7)
    assert btc_volatility(b).score == -1
    assert btc_volatility(bars(FLAT)).score == 0


def test_leverage():
    assert leverage([0.0001] * 21, None, FLAT).score == 0
    assert leverage([0.0005] * 21, None, FLAT).score == -1            # 费率过热
    oi_surge = [100.0] * 7 + [120.0]
    assert leverage([0.0001] * 21, oi_surge, FLAT).score == -1         # 持仓猛增、价格不动
    assert leverage(None, None, FLAT).score is None


def test_dollar_and_rates():
    flat = [100.0] * 21
    assert dollar_and_rates(flat, [4.0] * 21).score == 0
    assert dollar_and_rates([100.0] * 20 + [102.0], [4.0] * 21).score == -1   # 美元走强
    assert dollar_and_rates(flat, [4.0] * 20 + [4.4]).score == -1             # 利率上升
    assert dollar_and_rates([100.0] * 20 + [98.0], [4.0] * 21).score == 1     # 美元走弱
    assert dollar_and_rates(None, None).score is None


def test_stablecoins():
    assert stablecoins([300e9] * 30 + [310e9]).score == 1
    assert stablecoins([300e9] * 30 + [295e9]).score == -1
    assert stablecoins([300e9] * 10).score is None


def test_fear_greed():
    assert fear_greed(85).score == -1
    assert fear_greed(15).score == 0
    assert fear_greed(None).score is None


def test_btc_downtrend_vetoes_everything():
    good = MacroData(bars(DOWN), nasdaq=UP, dxy=[100.0] * 20 + [97.0], stables=[300e9] * 30 + [320e9])
    r = evaluate_regime(good)
    assert r.light == RED and r.score > -2       # 分数不差，但 BTC 空头排列一票否决


def test_green_needs_btc_uptrend_plus_support():
    assert evaluate_regime(MacroData(bars(UP), nasdaq=UP)).light == GREEN
    assert evaluate_regime(MacroData(bars(UP))).light == YELLOW         # 只有 BTC 好，不够绿灯


def test_flat_btc_is_yellow_and_missing_data_is_shown():
    r = evaluate_regime(MacroData(bars(FLAT)))
    assert r.light == YELLOW
    text = format_regime(r)
    assert '黄灯' in text and '❔ 纳斯达克' in text and '仓位' not in text


def test_etf_flows():
    days = lambda vals: [(date(2026, 10, i + 1), v) for i, v in enumerate(vals)]
    assert etf_flows(days([200, 150, 100, 80, 50])).score == 1         # 5 天累计 +580M
    assert etf_flows(days([-300, -200, 10, -100, 20])).score == -1     # 5 天累计 -570M
    assert etf_flows(days([23, 526, -82, 5, -261])).score == 0
    assert etf_flows(days([100, 100])).score is None


def test_parse_etf_flows_reads_table_and_brackets_as_outflow():
    page = """<h2>US spot Bitcoin ETF daily net flows</h2><table>
      <tr><th>Date</th><th>IBIT</th><th>FBTC</th><th>Total (US$m)</th></tr>
      <tr><td>Oct 20, 2026</td><td>20.0</td><td>-</td><td>23.2</td></tr>
      <tr><td>Oct 16, 2026</td><td>(80.0)</td><td>(1,002.4)</td><td>(1,082.4)</td></tr></table>"""
    assert parse_etf_flows(page) == [
        (date(2026, 10, 16), -1082.4, {'IBIT': -80.0, 'FBTC': -1002.4}),
        (date(2026, 10, 20), 23.2, {'IBIT': 20.0}),          # '-' 表示当天没数据，不算 0
    ]
