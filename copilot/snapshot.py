"""每日快照：每次生成页面数据都把今天的结果存成 data/snapshots/YYYY-MM-DD.json（北京时间的日期，同一天覆盖）。

用途：和昨天对比出"今日变化"、画近 30 天灯色，以后也是回测、调整阈值的素材。
"""
import json
from datetime import date
from pathlib import Path


def save(folder: Path, day: date, snap: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{day.isoformat()}.json').write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding='utf-8')


def _files(folder: Path) -> list[Path]:
    return sorted(folder.glob('????-??-??.json')) if folder.exists() else []


def previous(folder: Path, day: date) -> dict | None:
    """今天之前最近的一份快照（不一定是昨天，中间可能有几天没打开页面）。"""
    older = [p for p in _files(folder) if p.stem < day.isoformat()]
    return json.loads(older[-1].read_text(encoding='utf-8')) if older else None


def history(folder: Path, days: int = 30) -> list[dict]:
    return [json.loads(p.read_text(encoding='utf-8')) for p in _files(folder)[-days:]]
