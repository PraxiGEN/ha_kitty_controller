"""Kitty Controller 选择平台。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import quote

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base import BaseEntity
from .coordinator import (
    KittyControllerCoordinator,
    KittyData,
    DEFAULT_ENABLED_GROUP_KEYWORDS,
    slugify,
)

if TYPE_CHECKING:
    from . import KittyConfigEntry

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class KittySelectEntityDescription(SelectEntityDescription):
    """选择器描述符。"""

    current_fn: Callable[[KittyData], str | None] | None = None
    options_fn: Callable[[KittyData], list[str]] | None = None

# 静态选择器：核心模式
SELECT_DESCRIPTIONS: dict[str, KittySelectEntityDescription] = {
    "core_mode": KittySelectEntityDescription(
        key="core_mode",
        translation_key="core_mode",
        icon="mdi:tune",
        current_fn=lambda d: d.configs.get("mode"),
        options_fn=lambda d: d.configs.get("mode-list") or ["rule", "global", "direct"],
    ),
}

# 代理组选择器描述符模板（唯一 ID 由组名派生）
GROUP_DESCRIPTION = KittySelectEntityDescription(
    key="proxy_group",
    translation_key="proxy_group",
    icon="mdi:network-outline",
)

def _is_default_enabled_group(name: str, coordinator: KittyControllerCoordinator) -> bool:
    """按关键词判断组首次注册时是否默认启用（内置关键词 + 选项流额外关键词）。"""
    keywords = set(DEFAULT_ENABLED_GROUP_KEYWORDS)
    extra = getattr(coordinator, "default_group_keywords", None)
    if extra:
        keywords.update(extra)
    lowered = name.lower()
    return any(k in lowered for k in keywords)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: KittyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """建立选择实体：核心模式 + 全部代理组。"""
    coordinator = entry.runtime_data.coordinator
    entry_id = entry.entry_id
    entities: list[SelectEntity] = []

    entities.append(KittyCoreModeSelect(coordinator, entry_id, SELECT_DESCRIPTIONS["core_mode"]))

    # 代理组为动态实体：全部策略组均可作为选择器（含当前选中节点暂缺的组）
    for group in coordinator.data.groups:
        entities.append(KittyGroupSelect(coordinator, entry_id, group))

    async_add_entities(entities)

class KittySelectBase(BaseEntity, SelectEntity):
    """选择平台抽象基类。"""

    entity_description: KittySelectEntityDescription

    def __init__(
        self,
        coordinator: KittyControllerCoordinator,
        entry_id: str,
        description: KittySelectEntityDescription,
    ) -> None:
        """初始化选择器。"""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._override: str | None = None

    @property
    def current_option(self) -> str | None:
        """当前选项。"""
        if self._override is not None:
            return self._override
        if self.entity_description.current_fn is not None:
            return self.entity_description.current_fn(self.coordinator.data)
        return None

    @property
    def options(self) -> list[str]:
        """可选项列表。"""
        if self.entity_description.options_fn is not None:
            return self.entity_description.options_fn(self.coordinator.data) or []
        return []

    @callback
    def _handle_coordinator_update(self) -> None:
        """刷新后清除临时覆盖值。"""
        self._override = None
        self.async_write_ha_state()

class KittyCoreModeSelect(KittySelectBase):
    """核心运行模式选择器。"""

    async def async_select_option(self, option: str) -> None:
        """切换核心模式（PATCH /configs）。"""
        mode = option.strip()
        try:
            await self.coordinator.api.async_request("PATCH", "configs", json_data={"mode": mode})
            self._override = mode
            self.async_write_ha_state()
        except Exception as err:
            raise HomeAssistantError(f"切换核心模式至 {mode} 失败: {err}") from err

class KittyGroupSelect(KittySelectBase):
    """代理组选择器（动态实体）。"""

    def __init__(self, coordinator, entry_id, group) -> None:
        """初始化代理组选择器。"""
        super().__init__(coordinator, entry_id, GROUP_DESCRIPTION)
        self._group_name = group.name
        self._attr_unique_id = f"{entry_id}_group_{slugify(group.name)}"
        self._attr_name = group.name
        # 关键词启发式：常用组默认启用，其余默认禁用（可在实体列表中手动启用）
        self._attr_entity_registry_enabled_default = _is_default_enabled_group(
            group.name, coordinator
        )

    @property
    def _group(self):
        """按名称从最新协调器数据中解析本实体对应的代理组。"""
        for g in self.coordinator.data.groups:
            if g.name == self._group_name:
                return g
        return None

    @property
    def current_option(self) -> str | None:
        """当前选中的节点。"""
        if self._override is not None:
            return self._override
        group = self._group
        return group.now if group else None

    @property
    def options(self) -> list[str]:
        """组内候选节点。"""
        group = self._group
        return group.all if group else []

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """代理组元数据。"""
        group = self._group
        return group.attributes if group else None

    async def async_select_option(self, option: str) -> None:
        """切换代理组节点。"""
        group = self._attr_name.strip()
        try:
            await self.coordinator.api.async_request(
                "PUT",
                f"proxies/{quote(group, safe='')}",
                json_data={"name": option.strip()},
            )
            self._override = option
            self.async_write_ha_state()
        except Exception as err:
            raise HomeAssistantError(f"设置代理组 {group} 失败: {err}") from err