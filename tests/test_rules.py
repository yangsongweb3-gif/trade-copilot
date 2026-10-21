import pytest
from pydantic import ValidationError

from copilot.config import Plan, Plans, Settings
from copilot.market import DailyBars, Ticker
from copilot.rules import IMPORTANT, URGENT, evaluate, position_size
from copilot.state import AlertState

S = Settings(account_usdt=10000, risk_per_trade_pct=2, no_chase_pct_24h=20)
ETH_A = Plan(id='eth-a', symbol='ETHUSDT', note='回踩买', buy_zone=(136, 138), stop=131,
              targets=[155, 174], max_usdt=1875, cancel_if=[{'symbol': 'BTCUSDT', 'close_below': 80000}])
BTC_OK = {'BTCUSDT': DailyBars('BTCUSDT', [82000.0] * 30)}


def keys(signals):
    return {s.key for s in signals}


def tick(price, pct=0.0, sym='ETHUSDT'):
    return {sym: Ticker(sym, price, pct)}


def test_buy_zone_with_position_size():
    (s,) = evaluate(ETH_A, S, tick(137), BTC_OK)
    assert s.key == 'eth-a:buy_zone' and s.level == IMPORTANT
    # 风险 200U / 每枚风险 6U ≈ 33 枚 ≈ 4,567U，但计划上限 1,875U → 约 13.7 枚
    assert '1,875 U' in s.text


def test_position_size_respects_risk_budget():
    qty, usdt, loss = position_size(S, entry=100, stop=95, max_usdt=None)
    assert loss == pytest.approx(200)          # 账户 2%
    assert qty == pytest.approx(40)


def test_outside_zone_no_signal():
    assert evaluate(ETH_A, S, tick(145), BTC_OK) == []


def test_stop_is_urgent():
    (s,) = evaluate(ETH_A, S, tick(130), BTC_OK)
    assert s.key == 'eth-a:stop' and s.level == URGENT


def test_targets():
    assert keys(evaluate(ETH_A, S, tick(160), BTC_OK)) == {'eth-a:target1'}
    assert keys(evaluate(ETH_A, S, tick(175), BTC_OK)) == {'eth-a:target1', 'eth-a:target2'}


def test_cancel_condition_overrides_everything():
    btc_bad = {'BTCUSDT': DailyBars('BTCUSDT', [82000.0] * 29 + [79000.0])}
    (s,) = evaluate(ETH_A, S, tick(137), btc_bad)    # 就算在买入区，计划作废优先
    assert s.key == 'eth-a:cancel:BTCUSDT' and s.level == URGENT


def test_close_above_uses_daily_close_not_live_price():
    plan = Plan(id='eth-b', symbol='ETHUSDT', close_above=156, stop=145, targets=[181])
    below = {'ETHUSDT': DailyBars('ETHUSDT', [150.0] * 10)}
    above = {'ETHUSDT': DailyBars('ETHUSDT', [150.0] * 9 + [157.0])}
    assert evaluate(plan, S, tick(158), below) == []   # 盘中冲上去不算
    assert keys(evaluate(plan, S, tick(158), above)) == {'eth-b:close_above'}


def test_close_below_ma():
    plan = Plan(id='link-hold', symbol='LINKUSDT', close_below_ma=20)
    up = {'LINKUSDT': DailyBars('LINKUSDT', [100.0] * 19 + [110.0])}
    down = {'LINKUSDT': DailyBars('LINKUSDT', [110.0] * 19 + [100.0])}
    assert evaluate(plan, S, tick(105, sym='LINKUSDT'), up) == []
    assert keys(evaluate(plan, S, tick(105, sym='LINKUSDT'), down)) == {'link-hold:ma20'}


def test_no_chase():
    plan = Plan(id='x', symbol='ARBUSDT')
    assert keys(evaluate(plan, S, tick(1, 25, 'ARBUSDT'), {})) == {'ARBUSDT:no_chase'}
    assert evaluate(plan, S, tick(1, 15, 'ARBUSDT'), {}) == []


def test_disabled_plan_is_silent():
    plan = ETH_A.model_copy(update={'enabled': False})
    assert evaluate(plan, S, tick(130), BTC_OK) == []


@pytest.mark.parametrize('bad', [
    {'buy_zone': (138, 136)},                       # 区间写反
    {'buy_zone': (136, 138), 'stop': 137},          # 止损在买入区里
    {'buy_zone': (136, 138), 'targets': [137]},     # 目标价比买入区还低
])
def test_plan_validation(bad):
    with pytest.raises(ValidationError):
        Plan(id='bad', symbol='ETHUSDT', **bad)


def test_duplicate_plan_ids_rejected():
    with pytest.raises(ValidationError):
        Plans(settings=S, plans=[ETH_A, ETH_A])


def test_state_alerts_once_until_condition_clears(tmp_path):
    st = AlertState(tmp_path / 'state.json')
    assert st.update({'a'}) == {'a'}        # 第一次成立：提醒
    assert st.update({'a'}) == set()        # 一直成立：不重复
    assert st.update(set()) == set()        # 不成立：解除
    assert st.update({'a'}) == {'a'}        # 再次成立：再提醒
    assert AlertState(tmp_path / 'state.json').active == {'a'}   # 重启后状态还在
