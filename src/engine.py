"""称号系统

核心实现位于 title/system.py, 本模块保留原有导入路径:
    from src.engine import TitleSystem, Title
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from title.system import (  # noqa: E402
    TitleSystem,
    Title,
    RARITY_ORDER,
    RARITY_STYLE,
    POLICY_FREEZE,
    POLICY_REVOKE,
)

__all__ = ["TitleSystem", "Title", "RARITY_ORDER", "RARITY_STYLE"]
