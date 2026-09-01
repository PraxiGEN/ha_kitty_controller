"""Kitty Controller 实体基类。"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

if TYPE_CHECKING:
    from .coordinator import KittyControllerCoordinator

_LOGGER = logging.getLogger(__name__)

class BaseEntity(CoordinatorEntity):
    """所有实体的公共基类：处理设备归属与唯一 ID 前缀。"""

    coordinator: KittyControllerCoordinator
    _attr_has_entity_name = True

    def __init__(self, coordinator: KittyControllerCoordinator, entry_id: str) -> None:
        """初始化实体。"""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_device_info = coordinator.device_info

    @callback
    def _handle_coordinator_update(self) -> None:
        """协调器刷新后重写状态。"""
        self.async_write_ha_state()