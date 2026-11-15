import re
from datetime import datetime

from copilot.tweet import BEIJING, LIMIT, compose, x_len

NOW = datetime(2026, 10, 22, 10, 10, tzinfo=BEIJING)
PAYLOAD = {
    'updated_at': '2026-10-22 10:10', 'light': 'yellow', 'light_name': '黄灯', 'score': 2,
    'reason': 'BTC 趋势向上，但其他指标拖后腿',
    'agenda': [{'time': '2026-10-22T02:00:00+00:00', 'title': '已经过去的'},
               {'time': '2026-10-22T12:30:00+00:00', 'title': '初请失业金人数'},
               {'time': '2026-10-23T08:00:00+00:00', 'title': 'BTC 期权到期（周度）'}],
    'changes': [{'text': 'BTC 收盘站上 MA20（83,241）'}],
}


def test_x_len_weights_cjk_and_urls():
    assert x_len('abc') == 3
    assert x_len('比特币') == 6
    assert x_len('看 https://example.com/very/long/path') == 2 + 1 + 23


def test_compose_one_post_with_light_change_events_and_no_url():
    t = compose(PAYLOAD, NOW)
    main = t['main']
    assert main.startswith('BTC 每日面板 · 10/22\n🟡 环境灯：黄灯（综合 +2 分）\n📌 BTC 收盘站上 MA20（83,241）')
    assert '今天 20:30 初请失业金人数｜明天 16:00 BTC 期权到期（周度）' in main     # 过去的事件不列
    assert '完整面板见主页简介链接' in main and '不构成投资建议' in main
    assert not re.search(r'https?://|\.io\b', main) and x_len(main) <= LIMIT     # 带链接的推文接口很贵
    assert t['replies'] == []


def test_compose_uses_reason_when_nothing_changed_and_trims_when_long():
    quiet = compose(dict(PAYLOAD, changes=[]), NOW)['main']
    assert '📌 BTC 趋势向上，但其他指标拖后腿' in quiet
    many = dict(PAYLOAD, changes=[{'text': '很长的一条变化说明' * 4}] * 3)
    t = compose(many, NOW)
    assert x_len(t['main']) <= LIMIT and '环境灯' in t['main']
