"""Kitty Controller 传感器平台。"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfDataRate, UnitOfInformation
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import SERVICE_TABLE
from .base import BaseEntity
from .coordinator import KittyControllerCoordinator, KittyData, slugify
from .types import KittyConfigEntry

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class KittySensorEntityDescription(SensorEntityDescription):
    """传感器描述符：携带从协调器数据取值的函数。"""

    value_fn: Callable[[KittyData], Any] = lambda data: None
    attr_fn: Callable[[KittyData], dict[str, Any] | None] | None = None
    # ENUM 传感器的合法状态列表（配合翻译 state 段本地化显示）
    options: list[str] | None = None
    # 动态生成 ENUM options 的函数（状态值含动态版本号等场景），每次刷新时调用
    options_fn: Callable[[KittyData], list[str]] | None = None

def _parse_version(value: str) -> tuple[int, int, int]:
    """提取版本号三元组（"v1.19.0-alpha" → (1,19,0)），忽略 pre-release 后缀。"""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]

def _core_update_state(data: KittyData) -> str | None:
    """版本对比状态：有新版本显示版本号，无新版显示 up_to_date。 """
    current = data.version
    if not current:
        return None
    latest = (data.release or {}).get("tag_name")
    if not latest:
        return "checking"
    if _parse_version(latest) > _parse_version(current):
        return latest
    return "up_to_date"

def _core_update_options(data: KittyData) -> list[str]:
    """ENUM 合法状态列表：固定状态码 + 动态最新版本号（否则 ENUM 拒写状态）。"""
    options = ["up_to_date", "checking"]
    latest = (data.release or {}).get("tag_name")
    if latest:
        options.insert(0, latest)
    return options

def _core_update_attrs(data: KittyData) -> dict[str, Any] | None:
    """版本对比详情。"""
    release = data.release or {}
    return {
        "current_version": data.version,
        "latest_version": release.get("tag_name"),
        "published_at": release.get("published_at") or None,
        "is_meta": data.meta,
    }

# 静态传感器：展示元数据与取值逻辑都在平台侧声明
SENSOR_DESCRIPTIONS: dict[str, KittySensorEntityDescription] = {
    "up_speed": KittySensorEntityDescription(
        key="up_speed",
        translation_key="up_speed",
        icon="mdi:arrow-up",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.traffic.get("up"),
    ),
    "down_speed": KittySensorEntityDescription(
        key="down_speed",
        translation_key="down_speed",
        icon="mdi:arrow-down",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.traffic.get("down"),
    ),
    "up_traffic": KittySensorEntityDescription(
        key="up_traffic",
        translation_key="up_traffic",
        icon="mdi:tray-arrow-up",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.connections.get("uploadTotal"),
    ),
    "down_traffic": KittySensorEntityDescription(
        key="down_traffic",
        translation_key="down_traffic",
        icon="mdi:tray-arrow-down",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.connections.get("downloadTotal"),
    ),
    "memory_used": KittySensorEntityDescription(
        key="memory_used",
        translation_key="memory_used",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        # 优先 /connections 快照的 memory（单次响应稳定），/memory 采样 inuse 兜底，
        # 两者皆无返回 None（显示未知），避免误导性的 0
        value_fn=lambda d: d.connections.get("memory") or d.memory.get("inuse") or None,
    ),
    "connection_number": KittySensorEntityDescription(
        key="connection_number",
        translation_key="connection_number",
        icon="mdi:transit-connection",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.connections.get("connections", []) or []),
    ),
    "proxy_provider_count": KittySensorEntityDescription(
        key="proxy_provider_count",
        translation_key="proxy_provider_count",
        icon="mdi:server-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.provider_proxies.get("providers", {}) or {}),
    ),
    "rule_provider_count": KittySensorEntityDescription(
        key="rule_provider_count",
        translation_key="rule_provider_count",
        icon="mdi:file-document-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.provider_rules.get("providers", {}) or {}),
    ),
    # 核心更新检查：协调器每 6 小时查一次 GitHub 最新正式版，ENUM + 动态 options
    "core_update": KittySensorEntityDescription(
        key="core_update",
        translation_key="core_update",
        icon="mdi:update",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=["up_to_date", "checking"],
        options_fn=_core_update_options,
        value_fn=_core_update_state,
        attr_fn=_core_update_attrs,
    ),
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: KittyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """建立传感器实体：静态描述符 + 动态流媒体传感器。"""
    coordinator = entry.runtime_data.coordinator
    entry_id = entry.entry_id
    entities: list[SensorEntity] = []

    for description in SENSOR_DESCRIPTIONS.values():
        entities.append(KittySensorEntity(coordinator, entry_id, description))

    # 动态实体：流媒体解锁检测结果，成员随配置变化
    for service_key in coordinator.data.streaming:
        entities.append(StreamingSensor(coordinator, entry_id, service_key))

    async_add_entities(entities)

class KittySensorEntity(BaseEntity, SensorEntity):
    """通用传感器实现。"""

    entity_description: KittySensorEntityDescription

    def __init__(
        self,
        coordinator: KittyControllerCoordinator,
        entry_id: str,
        description: KittySensorEntityDescription,
    ) -> None:
        """初始化传感器。"""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        if description.options_fn is not None:
            # 动态 options（状态含版本号等运行时值）：用当前数据初始化，
            # 避免首次注册时 state 已是版本号却不在静态 options 中而抛 ValueError
            self._attr_options = description.options_fn(self.coordinator.data)
        elif description.options is not None:
            self._attr_options = description.options

    @callback
    def _handle_coordinator_update(self) -> None:
        """刷新后先同步动态 ENUM options，再重写状态。"""
        if self.entity_description.options_fn is not None:
            self._attr_options = self.entity_description.options_fn(
                self.coordinator.data
            )
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float | int | str | None:
        """从协调器数据计算数值。"""
        value = self.entity_description.value_fn(self.coordinator.data)
        if value is None:
            return None
        precision = self.entity_description.suggested_display_precision
        if precision and precision > 0:
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """附加属性。"""
        if self.entity_description.attr_fn is not None:
            return self.entity_description.attr_fn(self.coordinator.data)
        return None

class StreamingSensor(BaseEntity, SensorEntity):
    """流媒体解锁状态传感器（动态实体），描述符从 SERVICE_TABLE 构建。"""

    entity_description: KittySensorEntityDescription

    def __init__(
        self,
        coordinator: KittyControllerCoordinator,
        entry_id: str,
        service_key: str,
    ) -> None:
        """初始化流媒体传感器。"""
        super().__init__(coordinator, entry_id)
        self._service_key = service_key
        service_info = SERVICE_TABLE.get(service_key, {})
        self._code_table = service_info.get("code_table", {})
        self.entity_description = KittySensorEntityDescription(
            key=f"{service_key}_service",
            translation_key=f"{service_key}_service",
            icon=service_info.get("icon", "mdi:movie-outline"),
            device_class=SensorDeviceClass.ENUM,
            options=list(self._code_table.values()) + ["unknown"],
        )
        self._attr_unique_id = f"{entry_id}_{slugify(service_key)}"

    @property
    def native_value(self) -> str | None:
        """读取解锁状态。"""
        data = self.coordinator.data.streaming.get(self._service_key)
        if not data:
            return None
        return self._code_table.get(data.get("status_code", 0), "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """探测详情。"""
        return self.coordinator.data.streaming.get(self._service_key)