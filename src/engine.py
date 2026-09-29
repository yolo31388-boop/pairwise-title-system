"""称号系统"""
from dataclasses import dataclass, field
from time import time as _now
from typing import Callable, Optional

RARITY_ORDER = ("common", "rare", "epic", "legendary", "mythic")

RARITY_STYLES = {
    "common": {"label": "普通", "color": "#CFCFCF", "effect": "none",
               "border": "plain", "glow": False, "order": 0},
    "rare": {"label": "稀有", "color": "#3B82F6", "effect": "shine",
             "border": "blue", "glow": False, "order": 1},
    "epic": {"label": "史诗", "color": "#A855F7", "effect": "sparkle",
             "border": "purple", "glow": True, "order": 2},
    "legendary": {"label": "传说", "color": "#F59E0B", "effect": "flame",
                  "border": "gold", "glow": True, "order": 3},
    "mythic": {"label": "神话", "color": "#EC4899", "effect": "rainbow",
               "border": "prismatic", "glow": True, "order": 4},
}

DEFAULT_STYLE = {"label": "未知", "color": "#FFFFFF", "effect": "none",
                 "border": "plain", "glow": False, "order": 0}

STATUS_ACTIVE = "active"
STATUS_FROZEN = "frozen"
STATUS_EXPIRED = "expired"
STATUS_REVOKED = "revoked"


@dataclass
class Title:
    tid: str
    name: str
    rarity: str
    effects: dict
    expire_time: float = None
    source: str = ""
    level: int = 1
    condition: Optional[Callable[[str, dict], bool]] = None
    on_condition_lost: str = "freeze"


@dataclass
class TitleRecord:
    tid: str
    source: str
    acquire_time: float
    condition_snapshot: dict = field(default_factory=dict)
    status: str = STATUS_ACTIVE


class TitleSystem:
    def __init__(self):
        self.titles: dict[str, Title] = {}
        self.owned: dict[str, list] = {}
        self.equipped: dict[str, str] = {}
        self.records: dict[str, dict[str, TitleRecord]] = {}
        self.notifications: dict[str, list] = {}

    def register_title(self, title: Title):
        self.titles[title.tid] = title
        return title

    def _bucket(self, player_id):
        self.owned.setdefault(player_id, [])
        self.records.setdefault(player_id, {})
        self.notifications.setdefault(player_id, [])

    def _notify(self, player_id, message):
        self.notifications.setdefault(player_id, []).append(message)

    def poll_notifications(self, player_id):
        notes = self.notifications.get(player_id, [])
        self.notifications[player_id] = []
        return notes

    def rarity_rank(self, tid):
        t = self.titles.get(tid)
        if not t:
            return 0
        return RARITY_STYLES.get(t.rarity, DEFAULT_STYLE)["order"]

    def is_expired(self, tid, now=None):
        t = self.titles.get(tid)
        if not t or t.expire_time is None:
            return False
        return (now if now is not None else _now()) >= t.expire_time

    def _status(self, player_id, tid, now=None):
        rec = self.records.get(player_id, {}).get(tid)
        return rec.status if rec else STATUS_ACTIVE

    def is_active(self, player_id, tid, now=None):
        if tid not in self.owned.get(player_id, []):
            return False
        if self.is_expired(tid, now):
            return False
        return self._status(player_id, tid, now) == STATUS_ACTIVE

    def acquire(self, player_id, tid, condition_check=True, *,
                source=None, snapshot=None, now=None):
        t = self.titles.get(tid)
        if t is None:
            return False
        self._bucket(player_id)
        if tid in self.owned[player_id]:
            return False
        context = dict(snapshot or {})
        if condition_check and t.condition is not None:
            if not t.condition(player_id, context):
                return False
        now = now if now is not None else _now()
        self.owned[player_id].append(tid)
        self.records[player_id][tid] = TitleRecord(
            tid=tid,
            source=source if source is not None else t.source,
            acquire_time=now,
            condition_snapshot=context,
        )
        self._notify(player_id, f"获得称号《{t.name}》")
        return True

    def equip(self, player_id, tid, now=None):
        if tid not in self.owned.get(player_id, []):
            return False
        self._expire_due(player_id, now)
        if not self.is_active(player_id, tid, now):
            return False
        self.equipped[player_id] = tid
        return True

    def unequip(self, player_id):
        old = self.equipped.pop(player_id, None)
        return old

    def get_effects(self, player_id, now=None):
        tid = self.equipped.get(player_id)
        if not tid:
            return {}
        self._expire_due(player_id, now, only={tid})
        if not self.is_active(player_id, tid, now):
            return {}
        return dict(self.titles[tid].effects)

    def _expire_due(self, player_id, now=None, only=None):
        now = now if now is not None else _now()
        for tid in list(self.owned.get(player_id, [])):
            if only is not None and tid not in only:
                continue
            if not self.is_expired(tid, now):
                continue
            self._mark_expired(player_id, tid, now)

    def _mark_expired(self, player_id, tid, now=None):
        rec = self.records.get(player_id, {}).get(tid)
        if rec and rec.status == STATUS_EXPIRED:
            return
        if rec:
            rec.status = STATUS_EXPIRED
        if self.equipped.get(player_id) == tid:
            self.equipped.pop(player_id, None)
        name = self.titles[tid].name if tid in self.titles else tid
        self._notify(player_id, f"称号《{name}》已过期，属性加成已移除")

    def sweep_expirations(self, player_id=None, now=None):
        targets = [player_id] if player_id is not None else list(self.owned.keys())
        for pid in targets:
            self._expire_due(pid, now)

    def check_conditions(self, player_id, context=None, now=None):
        context = dict(context or {})
        now = now if now is not None else _now()
        self._expire_due(player_id, now)
        for tid in list(self.owned.get(player_id, [])):
            t = self.titles.get(tid)
            if t is None or t.condition is None:
                continue
            rec = self.records.get(player_id, {}).get(tid)
            if rec and rec.status in (STATUS_EXPIRED, STATUS_REVOKED):
                continue
            satisfied = bool(t.condition(player_id, context))
            if satisfied:
                if rec and rec.status == STATUS_FROZEN:
                    rec.status = STATUS_ACTIVE
                    self._notify(player_id, f"称号《{t.name}》条件恢复，已解冻")
                continue
            if t.on_condition_lost == "revoke":
                if tid in self.owned.get(player_id, []):
                    self.owned[player_id].remove(tid)
                if self.equipped.get(player_id) == tid:
                    self.equipped.pop(player_id, None)
                if rec:
                    rec.status = STATUS_REVOKED
                self._notify(player_id, f"称号《{t.name}》条件不再满足，已回收")
            else:
                if rec:
                    rec.status = STATUS_FROZEN
                if self.equipped.get(player_id) == tid:
                    self.equipped.pop(player_id, None)
                self._notify(player_id, f"称号《{t.name}》条件不再满足，已冻结")

    def get_display_order(self, player_id, now=None, include_frozen=True):
        self._expire_due(player_id, now)
        records = self.records.get(player_id, {})
        visible = []
        for index, tid in enumerate(self.owned.get(player_id, [])):
            rec = records.get(tid)
            status = rec.status if rec else STATUS_ACTIVE
            if status == STATUS_EXPIRED or status == STATUS_REVOKED:
                continue
            if status == STATUS_FROZEN and not include_frozen:
                continue
            visible.append((index, tid))

        def sort_key(item):
            index, tid = item
            t = self.titles.get(tid)
            rarity = RARITY_STYLES.get(t.rarity, DEFAULT_STYLE)["order"] if t else 0
            level = t.level if t else 1
            acquire_time = rec.acquire_time if (rec := records.get(tid)) else index
            return (-rarity, -level, acquire_time, index)

        return [tid for _, tid in sorted(visible, key=sort_key)]

    def get_rarity_style(self, tid):
        t = self.titles.get(tid)
        style = RARITY_STYLES.get(t.rarity, DEFAULT_STYLE) if t else DEFAULT_STYLE
        return dict(style)

    def get_record(self, player_id, tid):
        return self.records.get(player_id, {}).get(tid)

    def get_source_info(self, player_id, tid):
        rec = self.get_record(player_id, tid)
        if rec is None:
            return None
        return {
            "tid": rec.tid,
            "source": rec.source,
            "acquire_time": rec.acquire_time,
            "condition_snapshot": dict(rec.condition_snapshot),
            "status": rec.status,
        }
