"""Kitty Controller 按钮平台。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import translation
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import RESTART_BODY
from .base import BaseEntity
from .const import DOMAIN
from .coordinator import KittyControllerCoordinator

if TYPE_CHECKING:
    from . import KittyConfigEntry

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, kw_only=True)
class KittyButtonEntityDescription(ButtonEntityDescription):
    """按钮描述符。"""

    endpoint: tuple[str, str] | None = None

# 静态按钮：动作（endpoint）写在描述符中
BUTTON_DESCRIPTIONS: Final[dict[str, KittyButtonEntityDescription]] = {
    "flush_fakeip_cache": KittyButtonEntityDescription(
        key="flush_fakeip_cache",
        translation_key="flush_cache",
        icon="mdi:cached",
        entity_category=EntityCategory.DIAGNOSTIC,
        endpoint=("POST", "cache/fakeip/flush"),
    ),
    "flush_dns_cache": KittyButtonEntityDescription(
        key="flush_dns_cache",
        translation_key="flush_dns_cache",
        icon="mdi:cached",
        entity_category=EntityCategory.DIAGNOSTIC,
        endpoint=("POST", "cache/dns/flush"),
    ),
    "upgrade_core": KittyButtonEntityDescription(
        key="upgrade_core",
        translation_key="upgrade_core",
        icon="mdi:update",
        entity_category=EntityCategory.DIAGNOSTIC,
        # 升级内核会重启内核进程，集成将短暂失联，故归为诊断类默认禁用
        endpoint=("POST", "upgrade"),
    ),
    "upgrade_geo": KittyButtonEntityDescription(
        key="upgrade_geo",
        translation_key="upgrade_geo",
        icon="mdi:earth",
        entity_category=EntityCategory.DIAGNOSTIC,
        # 升级 GEO 数据库会触发内核在线下载（约几十 MB），归为诊断类
        endpoint=("POST", "upgrade/geo"),
    ),
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: KittyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """建立按钮实体：仅静态按钮（更新订阅类动作已全部服务化）。"""
    coordinator = entry.runtime_data.coordinator
    entry_id = entry.entry_id
    entities: list[ButtonEntity] = []

    for description in BUTTON_DESCRIPTIONS.values():
        entities.append(KittyButtonEntity(coordinator, entry_id, description))

    async_add_entities(entities)

class KittyButtonEntity(BaseEntity, ButtonEntity):
    """静态按钮实体。"""

    entity_description: KittyButtonEntityDescription

    def __init__(
        self,
        coordinator: KittyControllerCoordinator,
        entry_id: str,
        description: KittyButtonEntityDescription,
    ) -> None:
        """初始化按钮。"""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"

    async def async_press(self) -> None:
        """执行按钮动作。"""
        endpoint = self.entity_description.endpoint
        if endpoint is None:
            raise HomeAssistantError("该按钮未定义动作。")
        try:
            # 升级内核与升级 GEO 同升级类动作，与重启核心一致携带空请求体
            json_body = RESTART_BODY if endpoint[1].startswith("upgrade") else None
            await self.coordinator.api.async_request(*endpoint, json_data=json_body)
        except Exception as err:
            _LOGGER.error("按钮动作执行失败: %s", err)
            await self._send_notification(success=False, error=str(err))
            raise HomeAssistantError(f"动作执行失败: {err}") from err
        else:
            await self._send_notification(success=True)

    async def _send_notification(self, success: bool, error: str | None = None) -> None:
        """从翻译文件动态抓取消息并发送持久通知。

        成功与失败分别读取 translation_key 下的 notification / notification_failed
        翻译键；键缺失时回退到「{实体名} 已完成 / 失败」的通用文案。
        """
        lang = self.hass.config.language
        translations = await translation.async_get_translations(
            self.hass, lang, "entity", [DOMAIN]
        )
        key = self.entity_description.key
        name = translations.get(
            f"component.{DOMAIN}.entity.button.{key}.name", key
        )
        if success:
            msg_key = f"component.{DOMAIN}.entity.button.{key}.notification"
            message = translations.get(msg_key, f"{name} 已完成")
        else:
            msg_key = f"component.{DOMAIN}.entity.button.{key}.notification_failed"
            message = translations.get(msg_key, f"{name} 失败：{error or '未知错误'}")
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "小猫咪控制器",
                "message": message,
                "notification_id": f"{DOMAIN}_{key}",
            },
            blocking=False,
        )
