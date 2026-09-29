"""称号系统

修复的六个问题:
1. 属性加成只对装备中的称号生效, 未装备的称号仅收集不加成。
2. 限时称号过期后立即移除属性, 并产生一条过期提醒。
3. 获取条件动态检查, 掉出条件时自动冻结(默认)或回收称号, 条件恢复后可解冻/重新获取。
4. 展示优先级按 稀有度 > 等级 > 获取时间 排序。
5. 每个稀有度有独立的颜色/特效/边框配置。
6. 每个称号记录获取来源、获取时间以及获取时的条件快照。

仅使用 Python 标准库。
"""
from dataclasses import dataclass
import copy
import time

# 稀有度档位, 数值越大越稀有(展示时排在越前面)
RARITY_ORDER = ("common", "uncommon", "rare", "epic", "legendary", "mythic")
RARITY_RANK = {name: index for index, name in enumerate(RARITY_ORDER)}

# 各稀有度的展示配置: 颜色 / 特效 / 边框
RARITY_STYLE = {
    "common":    {"color": "gray",    "effect": "none",    "border": "plain",   "glow": False},
    "uncommon":  {"color": "green",   "effect": "none",    "border": "silver",  "glow": False},
    "rare":      {"color": "blue",    "effect": "glow",    "border": "blue",    "glow": True},
    "epic":      {"color": "purple",  "effect": "shimmer", "border": "purple",  "glow": True},
    "legendary": {"color": "gold",    "effect": "aura",    "border": "gold",    "glow": True},
    "mythic":    {"color": "red",     "effect": "rainbow", "border": "rainbow", "glow": True},
}

# 中文稀有度别名
RARITY_ALIAS = {
    "普通": "common", "常见": "common",
    "优秀": "uncommon", "精良": "uncommon", "稀有": "rare",
    "史诗": "epic",
    "传说": "legendary",
    "神话": "mythic",
}

# 掉出获取条件时的处理策略
POLICY_FREEZE = "freeze"   # 冻结: 保留称号但不生效
POLICY_REVOKE = "revoke"   # 回收: 收回称号, 条件恢复后可重新获取


@dataclass
class Title:
    """称号静态配置"""
    tid: str
    name: str
    rarity: str
    effects: dict
    expire_time: float = None
    source: str = ""
    level: int = 1
    revoke_on_fail: bool = False


class TitleSystem:
    def __init__(self, time_func=None):
        # 称号静态配置 tid -> Title
        self.titles = {}
        # 玩家已收集的称号(保持获取顺序) player_id -> [tid, ...]
        self.owned = {}
        # 玩家当前装备的称号 player_id -> tid
        self.equipped = {}
        # 获取记录(来源/时间/条件快照/状态) player_id -> {tid: record}
        self.records = {}
        # 称号获取条件 tid -> callable(player_id) -> bool
        self.conditions = {}
        # 掉出条件后的处理策略 tid -> freeze/revoke
        self.policies = {}
        # 提醒消息 player_id -> [message, ...]
        self.notifications = {}
        # 可注入的时钟, 默认系统时间
        self.time_func = time_func or time.time

    # ------------------------------------------------------------------ 内部工具

    def _now(self, now=None):
        return self.time_func() if now is None else now

    def rarity_rank(self, rarity):
        rarity = RARITY_ALIAS.get(rarity, rarity)
        return RARITY_RANK.get(str(rarity).lower(), 0)

    def _get_title(self, tid):
        title = self.titles.get(tid)
        if title is None:
            raise KeyError("未配置的称号: %s" % tid)
        return title

    def _record(self, player_id, tid):
        """获取获取记录, 兼容直接操作 owned 列表但没有 record 的情况。"""
        bucket = self.records.setdefault(player_id, {})
        record = bucket.get(tid)
        if record is None:
            record = self._new_record(source=self.titles.get(tid).source if tid in self.titles else "")
            bucket[tid] = record
        return record

    @staticmethod
    def _new_record(source="", acquired_at=None, snapshot=None):
        return {
            "source": source,
            "acquired_at": acquired_at,
            "condition_snapshot": copy.deepcopy(snapshot) if snapshot else {},
            "state": "active",          # active / frozen / revoked / expired
            "revoke_on_fail": False,
            "condition": None,
            "expire_notified": False,
        }

    def _notify(self, player_id, message):
        self.notifications.setdefault(player_id, []).append(message)

    def is_expired(self, tid, now=None):
        title = self._get_title(tid)
        return title.expire_time is not None and self._now(now) >= title.expire_time

    def is_active(self, player_id, tid, now=None):
        """称号当前是否处于生效状态: 已收集、未过期、未冻结/回收且条件仍满足。"""
        if tid not in self.owned.get(player_id, []):
            return False
        if self.is_expired(tid, now):
            return False
        record = self._record(player_id, tid)
        if record["state"] != "active":
            return False
        condition = record["condition"] or self.conditions.get(tid)
        if condition is not None and not condition(player_id):
            return False
        return True

    # ------------------------------------------------------------------ 获取/装备

    def register_condition(self, tid, condition, policy=POLICY_FREEZE):
        """注册称号的动态获取条件。policy 为 freeze 或 revoke。"""
        self.conditions[tid] = condition
        self.policies[tid] = policy

    def acquire(self, player_id, tid, condition_check=True, source="",
                condition=None, snapshot=None, now=None):
        title = self._get_title(tid)
        condition = condition or self.conditions.get(tid)

        owned = self.owned.setdefault(player_id, [])

        # 已被回收的称号: 条件重新满足时允许再次获取
        existing = self.records.get(player_id, {}).get(tid)
        re_acquire = bool(existing and existing["state"] == "revoked")

        if tid in owned and not re_acquire:
            return True

        # 获取条件动态求值, 不满足则拿不到称号
        if condition_check and condition is not None and not condition(player_id):
            return False

        record = existing if re_acquire else self._new_record()
        record.update({
            "source": source or title.source or "unknown",
            "acquired_at": self._now(now),
            "condition_snapshot": copy.deepcopy(snapshot) if snapshot is not None else self._take_snapshot(player_id, condition),
            "state": "active",
            "revoke_on_fail": title.revoke_on_fail or self.policies.get(tid) == POLICY_REVOKE,
            "condition": condition,
            "expire_notified": False,
        })
        self.records.setdefault(player_id, {})[tid] = record
        if tid not in owned:
            owned.append(tid)
        # 入手即已过期: 立即标记过期
        self._sweep_title(player_id, tid, self._now(now))
        return True

    @staticmethod
    def _take_snapshot(player_id, condition):
        snapshot = {"player_id": player_id}
        # 若玩家对象暴露了可快照的属性, 顺手记录关键字段
        for attr in ("level", "vip_level", "rank", "power", "achievement_count"):
            value = getattr(player_id, attr, None)
            if value is not None:
                snapshot[attr] = value
        return snapshot

    def equip(self, player_id, tid, now=None):
        if tid not in self.owned.get(player_id, []):
            return False
        self._sweep_title(player_id, tid, self._now(now))
        if not self.is_active(player_id, tid, now):
            return False
        self.equipped[player_id] = tid
        return True

    def unequip(self, player_id, tid=None):
        current = self.equipped.get(player_id)
        if current is None:
            return False
        if tid is not None and current != tid:
            return False
        del self.equipped[player_id]
        return True

    def get_equipped(self, player_id):
        return self.equipped.get(player_id)

    # ------------------------------------------------------------------ 刷新/过期/条件

    def _expire_title(self, player_id, tid, record, now):
        record["state"] = "expired"
        if self.equipped.get(player_id) == tid:
            del self.equipped[player_id]
        if not record["expire_notified"]:
            title = self.titles[tid]
            self._notify(player_id, {
                "type": "expired",
                "tid": tid,
                "name": title.name,
                "time": now,
                "message": "称号【%s】已过期, 属性加成已移除" % title.name,
            })
            record["expire_notified"] = True

    def _sweep_title(self, player_id, tid, now):
        """检查单个称号的过期与获取条件, 返回它当前是否生效。"""
        record = self._record(player_id, tid)

        # 1. 过期检查
        if self.is_expired(tid, now):
            if record["state"] != "expired":
                self._expire_title(player_id, tid, record, now)
            return False

        # 2. 动态获取条件检查
        condition = record["condition"] or self.conditions.get(tid)
        if condition is not None:
            passing = condition(player_id)
            if not passing and record["state"] == "active":
                if record["revoke_on_fail"] or self.policies.get(tid) == POLICY_REVOKE:
                    self._revoke(player_id, tid, record, now)
                    return False
                record["state"] = "frozen"
                if self.equipped.get(player_id) == tid:
                    del self.equipped[player_id]
                self._notify(player_id, {
                    "type": "frozen",
                    "tid": tid,
                    "name": self.titles[tid].name,
                    "time": now,
                    "message": "称号【%s】已不满足获取条件, 暂时冻结" % self.titles[tid].name,
                })
            elif passing and record["state"] == "frozen":
                record["state"] = "active"
                self._notify(player_id, {
                    "type": "restored",
                    "tid": tid,
                    "name": self.titles[tid].name,
                    "time": now,
                    "message": "称号【%s】重新满足条件, 已恢复" % self.titles[tid].name,
                })

        return record["state"] == "active"

    def _revoke(self, player_id, tid, record, now):
        record["state"] = "revoked"
        if tid in self.owned.get(player_id, []):
            self.owned[player_id].remove(tid)
        if self.equipped.get(player_id) == tid:
            del self.equipped[player_id]
        self._notify(player_id, {
            "type": "revoked",
            "tid": tid,
            "name": self.titles[tid].name,
            "time": now,
            "message": "称号【%s】已不满足获取条件, 已被回收" % self.titles[tid].name,
        })

    def refresh(self, player_id, now=None):
        """刷新玩家全部称号: 过期处理 + 动态条件检查。"""
        now = self._now(now)
        for tid in list(self.owned.get(player_id, [])):
            self._sweep_title(player_id, tid, now)

    # 语义化别名
    def check_conditions(self, player_id, now=None):
        self.refresh(player_id, now)

    def tick(self, player_id=None, now=None):
        """游戏帧/定时调用, 处理过期与条件变化。"""
        now = self._now(now)
        targets = list(self.owned.keys()) if player_id is None else [player_id]
        for pid in targets:
            for tid in list(self.owned.get(pid, [])):
                self._sweep_title(pid, tid, now)

    # ------------------------------------------------------------------ 属性加成

    def get_effects(self, player_id, now=None):
        """只有装备中且生效(未过期/未冻结)的称号提供属性加成。"""
        self.refresh(player_id, now)
        total = {}
        tid = self.equipped.get(player_id)
        if tid is None:
            return total
        if not self.is_active(player_id, tid, now):
            return total
        for key, value in self.titles[tid].effects.items():
            total[key] = total.get(key, 0) + value
        return total

    # ------------------------------------------------------------------ 展示

    def get_display_order(self, player_id, now=None):
        """展示顺序: 稀有度(高到低) > 等级(高到低) > 获取时间(早到晚)。"""
        self.refresh(player_id, now)
        records = self.records.get(player_id, {})

        def sort_key(tid):
            title = self.titles[tid]
            record = records.get(tid)
            acquired_at = record["acquired_at"] if record and record["acquired_at"] is not None else 0
            acquisition_index = self.owned[player_id].index(tid)
            return (-self.rarity_rank(title.rarity), -int(title.level), acquired_at, acquisition_index)

        return sorted(self.owned.get(player_id, []), key=sort_key)

    def get_display_list(self, player_id, now=None):
        """返回带展示信息的称号列表。"""
        result = []
        for tid in self.get_display_order(player_id, now):
            title = self.titles[tid]
            record = self._record(player_id, tid)
            result.append({
                "tid": tid,
                "name": title.name,
                "rarity": title.rarity,
                "level": title.level,
                "style": self.get_rarity_style(tid),
                "state": record["state"],
                "equipped": self.equipped.get(player_id) == tid,
                "acquired_at": record["acquired_at"],
                "source": record["source"],
            })
        return result

    def get_rarity_style(self, tid):
        title = self._get_title(tid)
        rarity = RARITY_ALIAS.get(title.rarity, title.rarity)
        style = RARITY_STYLE.get(str(rarity).lower())
        if style is None:
            return {"color": "white", "effect": "none", "border": "plain", "glow": False}
        result = dict(style)
        result["rarity"] = str(rarity).lower()
        result["rank"] = self.rarity_rank(title.rarity)
        return result

    # ------------------------------------------------------------------ 来源记录

    def get_provenance(self, player_id, tid):
        """返回称号获取来源、时间、条件快照。"""
        record = self.records.get(player_id, {}).get(tid)
        if record is None:
            return None
        return {
            "tid": tid,
            "source": record["source"],
            "acquired_at": record["acquired_at"],
            "condition_snapshot": copy.deepcopy(record["condition_snapshot"]),
            "state": record["state"],
        }

    def get_source(self, player_id, tid):
        info = self.get_provenance(player_id, tid)
        return info["source"] if info else None

    # ------------------------------------------------------------------ 提醒

    def get_notifications(self, player_id):
        return list(self.notifications.get(player_id, []))

    def drain_notifications(self, player_id):
        messages = self.notifications.get(player_id, [])
        self.notifications[player_id] = []
        return messages
