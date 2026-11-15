"""按当天的面板数据写 X 推文：一条主推文，配 1 张 4:5 卡片。

价位、ETF、资金费率这些数字都在卡片上，文字只写今天的看点：灯色、今日变化、接下来的大事件。
只描述数据，不给建议。X 的字数按"加权"算：中文、全角符号和 emoji 每个算 2，上限 280。
不放网址：X 接口发带链接的推文要贵十几倍，还会降低曝光；网页链接放在 X 个人简介里。纯函数。
"""
import re
from datetime import datetime, timedelta, timezone

LIMIT = 280
BEIJING = timezone(timedelta(hours=8))
WEEK = '一二三四五六日'
TAGS = '#BTC #比特币'


def x_len(text: str) -> int:
    """X 的加权字数。"""
    text = re.sub(r'https?://\S+', 'x' * 23, text)
    return sum(2 if ord(ch) >= 0x1100 else 1 for ch in text)


def _when(iso: str, now: datetime) -> str:
    t = datetime.fromisoformat(iso).astimezone(BEIJING)
    days = (t.date() - now.astimezone(BEIJING).date()).days
    day = {0: '今天', 1: '明天'}.get(days, f'周{WEEK[t.weekday()]}')
    return f'{day} {t:%H:%M}'


def compose(d: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(BEIJING)
    day = datetime.strptime(d['updated_at'][:10], '%Y-%m-%d')
    icon = {'red': '🔴', 'yellow': '🟡', 'green': '🟢'}[d['light']]
    changes = [c['text'] for c in d.get('changes', [])]
    upcoming = [e for e in d.get('agenda', []) if datetime.fromisoformat(e['time']) > now][:2]

    def build(n_changes: int, n_events: int) -> str:
        lines = [f'BTC 每日面板 · {day.month}/{day.day}',
                 f"{icon} 环境灯：{d['light_name']}（综合 {d['score']:+d} 分）",
                 '📌 ' + ('；'.join(changes[:n_changes]) if changes else d['reason'])]
        if n_events and upcoming:
            lines.append('📅 ' + '｜'.join(f"{_when(e['time'], now)} {e['title']}" for e in upcoming[:n_events]))
        lines.append('价位、ETF、资金费率见图，完整面板见主页简介链接')
        lines.append(f'只整理数据，不构成投资建议 {TAGS}')
        return '\n'.join(lines)

    # 从最完整的版本往下试，第一个不超长的就用：先少列变化，再少列日程
    variants = [(3, 2), (2, 2), (1, 2), (1, 1), (1, 0)]
    main = next((m for m in (build(*v) for v in variants) if x_len(m) <= LIMIT), build(*variants[-1]))
    return {'main': main, 'replies': []}


def to_text(t: dict) -> str:
    parts = [f"【主推文】（{x_len(t['main'])}/{LIMIT}，配 card.png）\n{t['main']}"]
    parts += [f'【评论区第 {i} 条】（{x_len(r)}/{LIMIT}）\n{r}' for i, r in enumerate(t['replies'], 1)]
    return '\n\n'.join(parts) + '\n'
