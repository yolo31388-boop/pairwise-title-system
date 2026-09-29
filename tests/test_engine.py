"""称号测试"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.engine import TitleSystem, Title

class TestEffects:
    def test_only_equipped_active(self):
        ts = TitleSystem()
        ts.titles = {"t1": Title("t1","a","rare",{"atk":10}), "t2": Title("t2","b","epic",{"atk":20})}
        ts.owned["p1"] = ["t1","t2"]
        ts.equipped["p1"] = "t1"
        effects = ts.get_effects("p1")
        assert effects.get("atk",0) == 10, "未装备称号也生效"

class TestExpire:
    def test_expired_title_inactive(self):
        ts = TitleSystem()
        ts.titles = {"t1": Title("t1","a","rare",{"atk":10}, expire_time=0)}
        ts.owned["p1"] = ["t1"]
        ts.equipped["p1"] = "t1"
        effects = ts.get_effects("p1")
        assert effects.get("atk",0) == 0, "过期称号仍生效"
