from datetime import date, datetime, timedelta, timezone

from copilot.agenda import BEIJING, Event, fomc_events, merge_same_release, parse_ff, source_url, translate, upcoming
from copilot.levels import key_levels
from copilot.market import DailyBars


def bars(n=60):
    closes = [80000.0 + (i % 10) * 300 for i in range(n)]
    days = [date(2026, 8, 1) + timedelta(days=i) for i in range(n)]
    return DailyBars('BTCUSDT', closes, [c + 500 for c in closes], [c - 500 for c in closes], dates=days)


def test_key_levels_split_around_price_and_sorted_nearest_first():
    support, resist = key_levels(bars(), price=82100, today_high=82600, today_low=81700)
    assert all(lv.price < 82100 for lv in support) and all(lv.price >= 82100 for lv in resist)
    assert [lv.price for lv in support] == sorted((lv.price for lv in support), reverse=True)
    assert support[0].label == '今日低点' and resist[0].label == '今日高点'
    assert any(lv.label == '整数关口' and lv.price == 80000 for lv in support)
    assert any(lv.label == '整数关口' and lv.price == 85000 for lv in resist)


def test_key_levels_merge_levels_that_are_too_close():
    # 今日低点 81,990 和 MA 附近的价位离得很近时只留一个
    support, _ = key_levels(bars(), price=82100, today_high=82600, today_low=82050)
    prices = [lv.price for lv in support]
    assert all(abs(a - b) / 82100 * 100 >= 0.2 for i, a in enumerate(prices) for b in prices[i + 1:])


def test_parse_ff_keeps_usd_medium_and_high_and_translates():
    rows = [
        {'title': 'Unemployment Claims', 'country': 'USD', 'date': '2026-10-22T08:30:00-04:00', 'impact': 'Medium', 'forecast': '200K', 'previous': '199K'},
        {'title': 'German Ifo', 'country': 'EUR', 'date': '2026-10-22T04:00:00-04:00', 'impact': 'High'},
        {'title': 'Bank Holiday', 'country': 'USD', 'date': '2026-10-22T00:00:00-04:00', 'impact': 'Holiday'},
    ]
    (e,) = parse_ff(rows)
    assert e.title == '初请失业金人数' and e.impact == 'medium' and e.forecast == '200K'
    assert e.time.astimezone(BEIJING).hour == 20                 # 美东 8:30 = 北京 20:30
    assert e.url == 'https://www.dol.gov/ui/data.pdf'


def test_source_url_official_page_or_forexfactory_day():
    when = datetime(2026, 10, 23, 9, 45)
    assert 'bls.gov' in source_url('Core CPI m/m', when)
    assert 'bea.gov' in source_url('Core PCE Price Index m/m', when)    # PCE 不能被 CPI 的规则抢走
    assert source_url('Some New Report', when) == 'https://www.forexfactory.com/calendar?day=oct23.2026'
    assert all(e.url for e in fomc_events())


def test_translate_fed_speakers_and_unknown_titles():
    assert translate('FOMC Member Waller Speaks') == '美联储官员 Waller 讲话'
    assert translate('Some New Report') == 'Some New Report'


def test_fomc_october_is_thursday_2am_beijing():
    oct_ = [e for e in fomc_events() if e.time.month == 10][0]
    t = oct_.time.astimezone(BEIJING)
    assert (t.month, t.day, t.hour) == (10, 29, 2)


def test_upcoming_window_and_dedupe():
    now = datetime(2026, 10, 22, 10, 0, tzinfo=BEIJING)
    t = lambda d, h: datetime(2026, 10, d, h, tzinfo=BEIJING)
    events = [Event(t(21, 20), '昨天', 'medium'), Event(t(22, 8), '今天早上', 'medium'),
              Event(t(29, 2), '美联储利率决议', 'high'), Event(t(29, 2), '美联储利率决议', 'high'),
              Event(t(30, 0), '超出 7 天', 'high')]          # 今天是 22 日：22 日加之后 7 天，到 29 日为止
    assert [e.title for e in upcoming(events, now)] == ['今天早上', '美联储利率决议']


def test_same_release_is_merged_into_one_row():
    t = datetime(2026, 10, 23, 13, 45, tzinfo=timezone.utc)
    pmi = 'https://www.pmi.spglobal.com/Public/Release/PressReleases'
    ff = 'https://www.forexfactory.com/calendar?day=oct23.2026'
    events = [Event(t, '标普制造业 PMI 初值', 'medium', '55.4', '57.0', pmi),
              Event(t, '标普服务业 PMI 初值', 'medium', '57.9', '58.7', pmi),
              Event(t, '没收录的事件 A', 'medium', url=ff), Event(t, '没收录的事件 B', 'medium', url=ff)]
    merged = merge_same_release(events)
    assert len(merged) == 3                                  # 两个 PMI 合并；兜底链接相同的不合并
    pmi_row = next(e for e in merged if e.url == pmi)
    assert pmi_row.title == '标普 PMI 初值' and [i[0] for i in pmi_row.items] == ['标普制造业 PMI 初值', '标普服务业 PMI 初值']


def test_fomc_from_calendar_and_schedule_becomes_one_row_with_forecast():
    t = fomc_events()[6].time
    events = fomc_events()[6:7] + [Event(t, '美联储利率决议', 'high', '3.75%', '3.75%', fomc_events()[0].url),
                                   Event(t, '美联储议息声明', 'high', url=fomc_events()[0].url)]
    (e,) = merge_same_release(events)
    assert e.title == '美联储利率决议' and e.forecast == '3.75%' and e.items == ()
