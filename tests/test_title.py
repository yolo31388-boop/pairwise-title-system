"""称号系统测试: 覆盖六个展示/属性 bug 的修复"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from title.system import (
    TitleSystem,
    Title,
    RARITY_STYLE,
    POLICY_REVOKE,
)


class TestEffects:
    def test_only_equipped_active(self):
        """bug1: 只有装备中的称号生效, 未装备只收集不加成"""
        ts = TitleSystem()
        ts.titles = {
            "t1": Title("t1", "a", "rare", {"atk": 10}),
            "t2": Title("t2", "b", "epic", {"atk": 20}),
        }
        assert ts.acquire("p1", "t1", condition_check=False)
        assert ts.acquire("p1", "t2", condition_check=False)
        assert ts.get_effects("p1") == {}
        assert ts.equip("p1", "t1")
        assert ts.get_effects("p1").get("atk", 0) == 10
        ts.unequip("p1")
        assert ts.get_effects("p1") == {}


class TestExpire:
    def test_expired_title_inactive(self):
        """bug2: 限时称号过期后属性立即移除"""
        ts = TitleSystem()
        ts.titles = {"t1": Title("t1", "a", "rare", {"atk": 10}, expire_time=0)}
        ts.owned["p1"] = ["t1"]
        ts.equipped["p1"] = "t1"
        assert ts.get_effects("p1").get("atk", 0) == 0
        assert "t1" not in ts.equipped.values()

    def test_expire_notification(self):
        """bug2: 过期时给玩家一条过期提醒"""
        clock = {"now": 100.0}
        ts = TitleSystem(time_func=lambda: clock["now"])
        ts.titles = {"t1": Title("t1", "巅峰", "legendary", {"atk": 10}, expire_time=200.0)}
        assert ts.acquire("p1", "t1", condition_check=False)
        assert ts.equip("p1", "t1")
        clock["now"] = 250.0
        assert ts.get_effects("p1") == {}
        notes = ts.drain_notifications("p1")
        assert len(notes) == 1
        assert notes[0]["type"] == "expired"
        assert notes[0]["tid"] == "t1"


class TestDynamicCondition:
    def test_freeze_when_condition_lost(self):
        """bug3: 掉出条件时自动冻结, 属性停止生效"""
        state = {"qualified": True}
        ts = TitleSystem()
        ts.titles = {"t1": Title("t1", "a", "rare", {"atk": 10})}
        ts.register_condition("t1", lambda p: state["qualified"])
        assert ts.acquire("p1", "t1")
        assert ts.equip("p1", "t1")
        state["qualified"] = False
        ts.check_conditions("p1")
        assert "t1" in ts.owned["p1"]
        assert ts.get_effects("p1") == {}
        assert any(n["type"] == "frozen" for n in ts.drain_notifications("p1"))

    def test_revoke_when_condition_lost(self):
        """bug3: 回收策略下掉出条件直接收回, 条件恢复可重新获取"""
        state = {"qualified": True}
        ts = TitleSystem()
        ts.titles = {"t1": Title("t1", "a", "rare", {"atk": 10}, revoke_on_fail=True)}
        ts.register_condition("t1", lambda p: state["qualified"], policy=POLICY_REVOKE)
        assert ts.acquire("p1", "t1")
        state["qualified"] = False
        ts.check_conditions("p1")
        assert "t1" not in ts.owned["p1"]
        assert any(n["type"] == "revoked" for n in ts.drain_notifications("p1"))
        state["qualified"] = True
        assert ts.acquire("p1", "t1")
        assert "t1" in ts.owned["p1"]


class TestDisplayOrder:
    def test_rarity_level_time_order(self):
        """bug4: 稀有度 > 等级 > 获取时间"""
        ts = TitleSystem()
        ts.titles = {
            "init": Title("init", "新手", "common", {}, level=1),
            "rare_low": Title("rare_low", "稀有低", "rare", {}, level=1),
            "rare_high": Title("rare_high", "稀有高", "rare", {}, level=5),
            "epic": Title("epic", "史诗", "epic", {}, level=1),
            "legend": Title("legend", "传说", "legendary", {}, level=1),
        }
        for tid in ["init", "rare_low", "rare_high", "epic", "legend"]:
            assert ts.acquire("p1", tid, condition_check=False)
        assert ts.get_display_order("p1") == ["legend", "epic", "rare_high", "rare_low", "init"]


class TestRarityStyle:
    def test_rarity_styles_distinct(self):
        """bug5: 稀有度有不同的颜色/特效/边框"""
        ts = TitleSystem()
        ts.titles = {
            "normal": Title("normal", "普通", "common", {}),
            "legend": Title("legend", "传说", "legendary", {}),
        }
        normal = ts.get_rarity_style("normal")
        legend = ts.get_rarity_style("legend")
        assert normal["color"] != legend["color"]
        assert normal["effect"] != legend["effect"]
        assert normal["border"] != legend["border"]
        assert legend["color"] == "gold"
        assert legend["effect"] == "aura"
        assert legend["border"] == "gold"
        for style in RARITY_STYLE.values():
            assert {"color", "effect", "border"} <= set(style)


class TestProvenance:
    def test_records_source_time_snapshot(self):
        """bug6: 记录获取来源/时间/条件快照"""
        ts = TitleSystem()
        ts.titles = {"t1": Title("t1", "a", "rare", {})}
        assert ts.acquire(
            "p1", "t1", condition_check=False,
            source="成就: 达到80级", snapshot={"level": 80},
        )
        info = ts.get_provenance("p1", "t1")
        assert info is not None
        assert info["source"] == "成就: 达到80级"
        assert isinstance(info["acquired_at"], float)
        assert info["condition_snapshot"] == {"level": 80}
