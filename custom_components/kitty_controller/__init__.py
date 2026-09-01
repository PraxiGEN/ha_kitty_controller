"""Kitty Controller 集成入口。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .api import KittyAPI
from .coordinator import KittyControllerCoordinator
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

@dataclass
class KittyRuntimeData:
    """持有集成运行期数据。"""
    coordinator: KittyControllerCoordinator
    api: KittyAPI

type KittyConfigEntry = ConfigEntry[KittyRuntimeData]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """集成加载时全局注册服务。"""
    await async_setup_services(hass)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: KittyConfigEntry) -> bool:
    """初始化配置条目。"""
    coordinator = KittyControllerCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = KittyRuntimeData(coordinator=coordinator, api=coordinator.api)
    coordinators = [
        config_entry.runtime_data.coordinator
        for config_entry in hass.config_entries.async_entries(DOMAIN)
        if getattr(config_entry, "runtime_data", None) is not None
    ]
    await async_setup_services(hass, coordinators)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: KittyConfigEntry) -> bool:
    """卸载配置条目。"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return unload_ok

    # 卸载单个条目后，若仍有其余实例在运行，用剩余协调器刷新服务下拉，
    others = [
        config_entry
        for config_entry in hass.config_entries.async_entries(DOMAIN)
        if config_entry.entry_id != entry.entry_id
    ]
    if others:
        remaining = [
            config_entry.runtime_data.coordinator
            for config_entry in others
            if getattr(config_entry, "runtime_data", None) is not None
        ]
        await async_setup_services(hass, remaining)
    else:
        # 最后一个条目卸载时清理全局注册的服务
        for service in list(hass.services.async_services_for_domain(DOMAIN)):
            hass.services.async_remove(DOMAIN, service)

    return unload_ok