"""行业消息：币安官方公告 + PANews 中文快讯。都是公开接口，不需要 Key。

- 币安公告：上新、下架、最新动态。现货下架和"监控标签"打击最大，标红；合约下架不标红。
- PANews：行业快讯，按关键词打上宏观、ETF、监管、安全等标签，方便在网页上筛选。

解析函数（parse_*、tags_for）是纯函数，拉取只在 News 类里。
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

PANEWS_RSS = 'https://www.panewslab.com/rss.xml?lang=zh&type=NEWS'
BINANCE_LIST = 'https://www.binance.com/bapi/composite/v1/public/cms/article/list/query'
BINANCE_DETAIL = 'https://www.binance.com/zh-CN/support/announcement/detail/'
BINANCE_CATALOGS = {48: '上新', 161: '下架', 49: '动态'}   # 其他分类（活动、空投、API 更新）不看

TAG_RULES = [
    ('宏观', r'美联储|降息|加息|CPI|PCE|非农|鲍威尔|FOMC|美债|关税|GDP|失业|通胀'),
    ('ETF', r'ETF'),
    ('监管', r'SEC|CFTC|监管|法案|立法|诉讼|起诉|合规|牌照'),
    ('安全', r'黑客|被盗|漏洞|攻击|盗取|钓鱼|安全事件|被攻击'),
    ('解锁', r'解锁'),
    ('巨鲸', r'巨鲸|鲸鱼|大额转'),
    ('币安', r'币安|Binance'),
]
DANGER = r'下架|移除|监控标签|暂停.*(充值|提现|交易)'


@dataclass(frozen=True)
class NewsItem:
    source: str             # 币安 / PANews
    title: str
    url: str
    time: datetime          # UTC
    summary: str = ''
    tags: list[str] = field(default_factory=list)
    danger: bool = False    # 对持仓可能有直接打击（下架、监控标签等）


def tags_for(text: str) -> list[str]:
    return [name for name, pattern in TAG_RULES if re.search(pattern, text, re.IGNORECASE)]


def parse_panews(xml_bytes: bytes, limit: int = 40) -> list[NewsItem]:
    out = []
    for it in ET.fromstring(xml_bytes).findall('./channel/item')[:limit]:
        title = (it.findtext('title') or '').strip()
        summary = re.sub(r'^PANews \d+月\d+日消息，', '', (it.findtext('description') or '').strip())
        out.append(NewsItem('PANews', title, it.findtext('link') or '', parsedate_to_datetime(it.findtext('pubDate')),
                            summary, tags_for(title + summary), bool(re.search(DANGER, title))))
    return out


def parse_binance(data: dict, per_catalog: int = 6) -> list[NewsItem]:
    out = []
    for c in data['data']['catalogs']:
        kind = BINANCE_CATALOGS.get(c['catalogId'])
        if not kind:
            continue
        for a in c['articles'][:per_catalog]:
            title = a['title']
            # 只做现货：合约下架不算紧急
            danger = (kind == '下架' or bool(re.search(DANGER, title))) and '合约' not in title
            out.append(NewsItem('币安', title, BINANCE_DETAIL + a['code'],
                                datetime.fromtimestamp(a['releaseDate'] / 1000, timezone.utc), tags=[kind], danger=danger))
    return sorted(out, key=lambda n: n.time, reverse=True)


class News:
    def __init__(self, proxy: str = '', timeout: float = 15):
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'Mozilla/5.0'
        if proxy:
            self.session.proxies.update({'http': proxy, 'https': proxy})
        self.timeout = timeout

    def panews(self) -> list[NewsItem]:
        r = self.session.get(PANEWS_RSS, timeout=self.timeout)
        r.raise_for_status()
        return parse_panews(r.content)

    def binance(self) -> list[NewsItem]:
        r = self.session.get(BINANCE_LIST, params={'type': 1, 'pageNo': 1, 'pageSize': 10},
                             headers={'lang': 'zh-CN'}, timeout=self.timeout)
        r.raise_for_status()
        return parse_binance(r.json())
