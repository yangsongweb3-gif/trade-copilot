"""提醒去重：同一个条件只在"从不成立变成成立"时提醒一次。

比如 AAVE 进入买入区后会一直在区间里待一阵，不能每分钟提醒一次；
等价格离开区间、条件不成立了，才解除，下次再进入时重新提醒。状态存在 data/state.json，重启不丢。
"""
import json
from pathlib import Path


class AlertState:
    def __init__(self, path: Path):
        self.path = path
        self.active: set[str] = set(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else set()

    def update(self, current_keys: set[str]) -> set[str]:
        """传入本轮成立的条件，返回其中新出现、需要提醒的；不再成立的自动解除。"""
        new = current_keys - self.active
        self.active = set(current_keys)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(self.active), ensure_ascii=False, indent=1), encoding='utf-8')
        return new
