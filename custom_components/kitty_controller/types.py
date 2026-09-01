"""Kitty Controller 运行期数据类型与配置条目类型别名。"""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .api import KittyAPI
from .coordinator import KittyControllerCoordinator

@dataclass
class KittyRuntimeData:
    """持有集成运行期数据。"""

    coordinator: KittyControllerCoordinator
    api: KittyAPI

# 跨模块共享的配置条目类型别名：平台模块直接运行时导入本模块，
type KittyConfigEntry = ConfigEntry[KittyRuntimeData]
