from copilot.news import parse_binance, parse_panews, tags_for

RSS = '''<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>美联储官员暗示12月降息，比特币ETF单日净流入3亿美元</title>
<description>PANews 10月22日消息，据彭博社报道……</description>
<link>https://www.panewslab.com/zh/articles/a</link><pubDate>Wed, 21 Oct 2026 20:26:38 GMT</pubDate></item>
<item><title>某DeFi协议遭黑客攻击，损失约500万美元</title><description></description>
<link>https://www.panewslab.com/zh/articles/b</link><pubDate>Wed, 21 Oct 2026 19:00:00 GMT</pubDate></item>
</channel></rss>'''.encode()


def test_tags_for():
    assert tags_for('美联储降息预期升温') == ['宏观']
    assert tags_for('SEC 批准现货 ETF') == ['ETF', '监管']
    assert tags_for('一个平平无奇的新闻') == []


def test_parse_panews_strips_prefix_and_tags():
    a, b = parse_panews(RSS)
    assert a.summary == '据彭博社报道……'                  # 去掉"PANews x月x日消息，"
    assert a.tags == ['宏观', 'ETF'] and a.time.hour == 20
    assert b.tags == ['安全']


def test_parse_binance_keeps_relevant_catalogs_and_flags_delisting():
    data = {'data': {'catalogs': [
        {'catalogId': 48, 'articles': [{'title': '币安将上线 ABC', 'code': 'c1', 'releaseDate': 1792550000000}]},
        {'catalogId': 161, 'articles': [{'title': '币安移除部分现货交易对的公告', 'code': 'c2', 'releaseDate': 1792560000000}]},
        {'catalogId': 49, 'articles': [{'title': '币安将为 XYZ 添加监控标签', 'code': 'c3', 'releaseDate': 1792540000000}]},
        {'catalogId': 161, 'articles': [{'title': '币安合约将下架 PTBUSDT U本位永续合约', 'code': 'c5', 'releaseDate': 1792530000000}]},
        {'catalogId': 93, 'articles': [{'title': '交易锦标赛', 'code': 'c4', 'releaseDate': 1792570000000}]},
    ]}}
    items = parse_binance(data)
    assert [n.tags[0] for n in items] == ['下架', '上新', '动态', '下架']   # 活动类不要，按时间从新到旧
    assert [n.danger for n in items] == [True, False, True, False]          # 现货下架、监控标签标红；合约下架不标
    assert items[0].url.endswith('/c2')
