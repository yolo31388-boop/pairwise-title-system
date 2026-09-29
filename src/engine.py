"""称号系统 - 带6个bug"""
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Title:
    tid: str
    name: str
    rarity: str
    effects: dict
    expire_time: float = None
    source: str = ""

class TitleSystem:
    def __init__(self):
        self.titles: dict[str, Title] = {}
        self.owned = {}  # player_id -> list of tid
        self.equipped = {}  # player_id -> tid

    def get_effects(self, player_id):
        # bug1: 所有拥有的称号都生效
        total = {}
        for tid in self.owned.get(player_id, []):
            t = self.titles[tid]
            # bug2: 不检查过期
            for k, v in t.effects.items():
                total[k] = total.get(k, 0) + v
        return total

    def acquire(self, player_id, tid, condition_check=True):
        # bug3: 只检查一次
        if player_id not in self.owned:
            self.owned[player_id] = []
        if tid not in self.owned[player_id]:
            self.owned[player_id].append(tid)
        return True

    def get_display_order(self, player_id):
        # bug4: 按获取时间
        return self.owned.get(player_id, [])

    def get_rarity_style(self, tid):
        # bug5: 无稀有度区分
        return {"color": "white"}
