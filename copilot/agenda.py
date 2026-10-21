"""未来 7 天的宏观日程。

- ForexFactory 本周日历：美国、中高影响的数据发布，带预期和前值（只有本周，下周的接口不对外）
- 美联储议息：官方全年日程，写在下面，每年初按 federalreserve.gov 更新一次
- 每个事件配上官方发布页（数据公布时原文就在那里），对照表里没有的链接到 ForexFactory 当天的日历页

解析和筛选是纯函数，拉取在 macro.Macro.ff_calendar 里。
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))

# 议息声明时间：美东 14:00。3 月第二个周日到 11 月第一个周日是夏令时（UTC-4），其余 UTC-5
FOMC_UTC = [datetime(2026, m, d, h, tzinfo=timezone.utc) for m, d, h in [
    (1, 28, 19), (3, 18, 18), (4, 29, 18), (6, 17, 18), (7, 29, 18), (9, 16, 18), (10, 28, 18), (12, 9, 19),
]]

TITLE_ZH = {
    'Unemployment Claims': '初请失业金人数',
    'Non-Farm Employment Change': '非农就业人数',
    'ADP Non-Farm Employment Change': 'ADP 就业人数',
    'Unemployment Rate': '失业率',
    'Average Hourly Earnings m/m': '平均时薪月率',
    'JOLTS Job Openings': 'JOLTS 职位空缺',
    'CPI m/m': 'CPI 月率', 'CPI y/y': 'CPI 年率', 'Core CPI m/m': '核心 CPI 月率', 'Core CPI y/y': '核心 CPI 年率',
    'PPI m/m': 'PPI 月率', 'Core PPI m/m': '核心 PPI 月率',
    'PCE Price Index m/m': 'PCE 物价指数月率', 'Core PCE Price Index m/m': '核心 PCE 物价指数月率',
    'Advance GDP q/q': 'GDP 初值（季率）', 'Prelim GDP q/q': 'GDP 修正值（季率）', 'Final GDP q/q': 'GDP 终值（季率）',
    'Retail Sales m/m': '零售销售月率', 'Core Retail Sales m/m': '核心零售销售月率',
    'ISM Manufacturing PMI': 'ISM 制造业 PMI', 'ISM Services PMI': 'ISM 服务业 PMI',
    'Flash Manufacturing PMI': '标普制造业 PMI 初值', 'Flash Services PMI': '标普服务业 PMI 初值',
    'Federal Funds Rate': '美联储利率决议', 'FOMC Statement': '美联储议息声明',
    'FOMC Press Conference': '美联储主席新闻发布会', 'FOMC Meeting Minutes': '美联储会议纪要',
    'Fed Chair Speaks': '美联储主席讲话', 'Beige Book': '美联储褐皮书',
    'Prelim UoM Consumer Sentiment': '密歇根大学消费者信心初值', 'Revised UoM Consumer Sentiment': '密歇根大学消费者信心终值',
    'Prelim UoM Inflation Expectations': '密歇根大学通胀预期初值', 'Revised UoM Inflation Expectations': '密歇根大学通胀预期终值',
    'CB Consumer Confidence': '谘商会消费者信心',
    'Durable Goods Orders m/m': '耐用品订单月率', 'Core Durable Goods Orders m/m': '核心耐用品订单月率',
    'Building Permits': '营建许可', 'Housing Starts': '新屋开工', 'New Home Sales': '新屋销售',
    'Existing Home Sales': '成屋销售', 'Pending Home Sales m/m': '成屋签约销售月率',
    'Empire State Manufacturing Index': '纽约联储制造业指数', 'Philly Fed Manufacturing Index': '费城联储制造业指数',
    'Industrial Production m/m': '工业产出月率', 'Trade Balance': '贸易差额', 'Employment Cost Index q/q': '就业成本指数（季率）',
}


# 官方发布页：按英文标题匹配，先匹配到的为准
SOURCE_URL = [
    (r'Unemployment Claims', 'https://www.dol.gov/ui/data.pdf'),
    (r'^ADP', 'https://adpemploymentreport.com/'),
    (r'Non-Farm Employment|Unemployment Rate|Average Hourly Earnings', 'https://www.bls.gov/news.release/empsit.nr0.htm'),
    (r'JOLTS', 'https://www.bls.gov/news.release/jolts.nr0.htm'),
    (r'Employment Cost Index', 'https://www.bls.gov/news.release/eci.nr0.htm'),
    (r'PCE', 'https://www.bea.gov/data/personal-consumption-expenditures-price-index'),
    (r'CPI', 'https://www.bls.gov/news.release/cpi.nr0.htm'),
    (r'PPI', 'https://www.bls.gov/news.release/ppi.nr0.htm'),
    (r'GDP', 'https://www.bea.gov/data/gdp/gross-domestic-product'),
    (r'Trade Balance', 'https://www.bea.gov/data/intl-trade-investment/international-trade-goods-and-services'),
    (r'Retail Sales', 'https://www.census.gov/retail/index.html'),
    (r'Durable Goods', 'https://www.census.gov/manufacturing/m3/index.html'),
    (r'Building Permits|Housing Starts', 'https://www.census.gov/construction/nrc/index.html'),
    (r'New Home Sales', 'https://www.census.gov/construction/nrs/index.html'),
    (r'Existing Home Sales|Pending Home Sales', 'https://www.nar.realtor/research-and-statistics/housing-statistics'),
    (r'^ISM', 'https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/'),
    (r'Flash .*PMI', 'https://www.pmi.spglobal.com/Public/Release/PressReleases'),
    (r'UoM', 'https://www.sca.isr.umich.edu/'),
    (r'CB Consumer Confidence', 'https://www.conference-board.org/topics/consumer-confidence'),
    (r'Empire State', 'https://www.newyorkfed.org/survey/empire/empiresurvey_overview'),
    (r'Philly Fed', 'https://www.philadelphiafed.org/surveys-and-data/regional-economic-analysis/manufacturing-business-outlook-survey'),
    (r'Industrial Production', 'https://www.federalreserve.gov/releases/g17/current/default.htm'),
    (r'Beige Book', 'https://www.federalreserve.gov/monetarypolicy/beige-book-default.htm'),
    (r'Speaks', 'https://www.federalreserve.gov/newsevents/speeches.htm'),
    (r'FOMC|Federal Funds Rate', 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'),
]
FOMC_URL = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'

# 同一时间、同一发布页的几项数据合成一条时用的名字（例如标普制造业和服务业 PMI 同时公布）
RELEASE_NAME = {
    'https://www.pmi.spglobal.com/Public/Release/PressReleases': '标普 PMI 初值',
    'https://www.sca.isr.umich.edu/': '密歇根大学 消费者调查',
    'https://www.bls.gov/news.release/empsit.nr0.htm': '非农就业报告',
    'https://www.bls.gov/news.release/cpi.nr0.htm': 'CPI 报告',
    'https://www.bls.gov/news.release/ppi.nr0.htm': 'PPI 报告',
    'https://www.bea.gov/data/personal-consumption-expenditures-price-index': 'PCE 物价指数',
    'https://www.bea.gov/data/gdp/gross-domestic-product': 'GDP 报告',
    'https://www.census.gov/retail/index.html': '零售销售',
    'https://www.census.gov/manufacturing/m3/index.html': '耐用品订单',
    'https://www.census.gov/construction/nrc/index.html': '新屋开工与营建许可',
    FOMC_URL: '美联储利率决议',
}


def source_url(title: str, when: datetime) -> str:
    for pattern, url in SOURCE_URL:
        if re.search(pattern, title):
            return url
    return f"https://www.forexfactory.com/calendar?day={when:%b}{when.day}.{when.year}".lower()


@dataclass(frozen=True)
class Event:
    time: datetime          # 带时区
    title: str              # 中文（没翻译的保留英文）
    impact: str             # high / medium
    forecast: str = ''
    previous: str = ''
    url: str = ''           # 官方发布页
    items: tuple[tuple[str, str, str], ...] = ()   # 合并后的各项数据：(名称, 预期, 前值)
    note: str = ''          # 补充说明，比如期权到期的未平仓量


def translate(title: str) -> str:
    if title in TITLE_ZH:
        return TITLE_ZH[title]
    m = re.match(r'^(?:FOMC Member|Fed Chair) (.+) Speaks$', title)
    if m:
        return f'美联储官员 {m.group(1)} 讲话'
    return title


def parse_ff(rows: list[dict]) -> list[Event]:
    """ForexFactory 日历 → 美国、中高影响的事件。"""
    out = []
    for r in rows:
        if r.get('country') == 'USD' and r.get('impact') in ('High', 'Medium'):
            when = datetime.fromisoformat(r['date'])
            out.append(Event(when, translate(r['title']), r['impact'].lower(), r.get('forecast') or '',
                             r.get('previous') or '', source_url(r['title'], when)))
    return out


def fomc_events() -> list[Event]:
    return [Event(t, '美联储利率决议', 'high', url=FOMC_URL) for t in FOMC_UTC]


def merge_same_release(events: list[Event]) -> list[Event]:
    """同一时间、同一发布页的几项数据合成一条；只合并 RELEASE_NAME 里有名字的发布。"""
    groups: dict[tuple, list[Event]] = {}
    out = []
    for e in events:
        if e.url in RELEASE_NAME:
            groups.setdefault((e.time, e.url), []).append(e)
        else:
            out.append(e)
    for es in groups.values():
        if len(es) == 1:
            out.append(es[0])
            continue
        first, name = es[0], RELEASE_NAME[es[0].url]
        impact = 'high' if any(e.impact == 'high' for e in es) else 'medium'
        # 只列有预期或前值的项；同名的（比如议息表和日历里都有"美联储利率决议"）只留一次
        items = list({e.title: (e.title, e.forecast, e.previous) for e in es if e.forecast or e.previous}.values())
        if len(items) == 1 and items[0][0] == name:
            out.append(Event(first.time, name, impact, items[0][1], items[0][2], first.url))
        else:
            out.append(Event(first.time, name, impact, url=first.url, items=tuple(items)))
    return out


def upcoming(events: list[Event], now: datetime, days: int = 7) -> list[Event]:
    """北京时间今天加上之后 days 天里的事件，按时间排；同一天同名的只留一条（日历和议息表会重复）。"""
    start = now.astimezone(BEIJING).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days + 1)
    seen, out = set(), []
    for e in sorted(merge_same_release(events), key=lambda e: (e.time, e.impact != 'high')):
        key = (e.time.astimezone(BEIJING).date(), e.title)
        if start <= e.time < end and key not in seen:
            seen.add(key)
            out.append(e)
    return out
