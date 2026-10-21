from datetime import date, datetime, timedelta, timezone

from copilot import snapshot
from copilot.changes import (daily_changes, etf_streak, fng_change, funding_flip, ma_cross, premium_flip,
                             snapshot_changes)
from copilot.options import expiry_kind, option_events, parse_deribit
from copilot.premium import premium_series


def test_snapshot_changes_light_score_and_indicators():
    prev = {'light': 'yellow', 'score': 0, 'scores': {'杠杆情绪': 0, 'BTC 波动': 0}}
    cur = {'light': 'red', 'score': -2, 'scores': {'杠杆情绪': -1, 'BTC 波动': 0}}
    texts = [c.text for c in snapshot_changes(cur, prev)]
    assert texts == ['环境灯：黄灯 → 红灯', '杠杆情绪：中性 → 利空']      # 灯色变了就不再单独报分数
    assert snapshot_changes(cur, None) == []


def test_ma_cross_up_and_down():
    flat = [100.0] * 25
    assert ma_cross(flat[:-1] + [110.0], 20).text.startswith('BTC 收盘站上 MA20')
    assert ma_cross(flat[:-1] + [90.0], 20).tone == 'down'
    assert ma_cross([100.0] * 23 + [110.0, 111.0], 20) is None          # 已经在上面，不算穿越


def test_funding_etf_fng_premium():
    assert funding_flip([0.0001, -0.00002]).text == '资金费率转负（-0.0020%）'
    assert funding_flip([0.0001, 0.0002]) is None
    days = [(date(2026, 10, i), v) for i, v in [(13, -50), (14, 100), (15, 200), (16, 300)]]
    assert etf_streak(days).text == 'BTC 现货 ETF 连续 3 个交易日净流入，累计 +0.60B 美元'
    assert etf_streak([(date(2026, 10, 1), 10), (date(2026, 10, 2), -620)]).text == 'BTC 现货 ETF 10-02 单日净流出 620M 美元'
    assert fng_change([(date(2026, 10, 20), 55), (date(2026, 10, 21), 63)]).text == '恐惧贪婪：中性 → 贪婪（55 → 63）'
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    prem = [(t0 + timedelta(hours=i), -0.05 if i < 24 else 0.04) for i in range(48)]
    assert premium_flip(prem).text.startswith('Coinbase 溢价转正')


def test_daily_changes_collects_everything():
    cur = {'light': 'yellow', 'score': 0, 'scores': {}}
    found = daily_changes(cur, None, [100.0] * 24 + [110.0], [date(2026, 10, 1)] * 25, [0.0001, -0.0001], None, None, None)
    assert [c.tone for c in found] == ['up', 'up', 'down']    # 站上 MA20、单日涨 10%、费率转负


def test_snapshot_save_previous_history(tmp_path):
    snapshot.save(tmp_path, date(2026, 10, 20), {'date': '2026-10-20', 'light': 'green', 'score': 3})
    snapshot.save(tmp_path, date(2026, 10, 22), {'date': '2026-10-22', 'light': 'yellow', 'score': 0})
    assert snapshot.previous(tmp_path, date(2026, 10, 22))['light'] == 'green'    # 中间缺一天也能找到
    assert snapshot.previous(tmp_path, date(2026, 10, 20)) is None
    assert [h['date'] for h in snapshot.history(tmp_path)] == ['2026-10-20', '2026-10-22']


def test_premium_series_aligns_by_hour():
    t = datetime(2026, 10, 22, 1, tzinfo=timezone.utc)
    cb = [(t, 100.1), (t + timedelta(hours=1), 100.0)]
    bn = [(t, 100.0)]
    ((when, pct),) = premium_series(cb, bn)
    assert when == t and round(pct, 3) == 0.1


def test_expiry_kind():
    assert expiry_kind(date(2026, 10, 23)) == '周度'
    assert expiry_kind(date(2026, 10, 30)) == '月度'
    assert expiry_kind(date(2026, 12, 25)) == '季度'


def test_parse_deribit_max_pain_and_put_call():
    rows = [
        {'instrument_name': 'BTC-30OCT26-80000-C', 'open_interest': 100, 'underlying_price': 84000},
        {'instrument_name': 'BTC-30OCT26-90000-C', 'open_interest': 300, 'underlying_price': 84000},
        {'instrument_name': 'BTC-30OCT26-80000-P', 'open_interest': 200, 'underlying_price': 84000},
        {'instrument_name': 'BTC-22OCT26-80000-P', 'open_interest': 999, 'underlying_price': 84000},   # 周四到期的每日期权，不看
    ]
    (e,) = parse_deribit(rows)
    assert e.kind == '月度' and e.oi_btc == 600 and e.put_call == 0.5
    assert e.max_pain == 80000      # 到期在 80,000：认购 80k 不赚钱、90k 也不赚、认沽 80k 不赚，买方拿回最少


def test_option_events_every_friday_even_without_data():
    now = datetime(2026, 10, 22, 2, tzinfo=timezone.utc)      # 周四
    events = option_events([], now)
    assert [e.time.date() for e in events] == [date(2026, 10, 23), date(2026, 10, 30)]
    assert events[1].title == 'BTC 期权到期（月度）' and events[1].impact == 'high' and events[1].note == ''
