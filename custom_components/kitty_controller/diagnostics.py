"""Kitty Controller 诊断平台。"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_BEAR_TOKEN

# 配置项中需直接脱敏的键（命中即整体替换为占位符）
REDACT_CONFIG_KEYS: frozenset[str] = {CONF_BEAR_TOKEN}

# 递归脱敏时匹配的键名片段（不区分大小写）：覆盖 mihomo /configs 等载荷中的凭证字段
_SENSITIVE_FRAGMENTS: tuple[str, ...] = (
    "secret",
    "token",
    "password",
    "passwd",
    "pwd",
    "apikey",
    "api_key",
    "access_token",
    "authorization",
    "authorisation",
    "cookie",
    "bearer",
    "key",
)

def _is_sensitive_key(key: str) -> bool:
    """键名是否命中敏感片段。"""
    lowered = key.lower()
    return any(frag in lowered for frag in _SENSITIVE_FRAGMENTS)

def _redact_dict(data: Any) -> Any:
    """递归遍历结构，敏感键的值替换为脱敏占位符，保持原结构。"""
    if isinstance(data, dict):
        return {
            k: ("**REDACTED**" if _is_sensitive_key(k) else _redact_dict(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_redact_dict(item) for item in data]
    return data

def _redact_config(data: dict[str, Any]) -> dict[str, Any]:
    """配置项数据脱敏（bearer_token 等）。"""
    redacted = dict(data)
    for key in REDACT_CONFIG_KEYS:
        if redacted.get(key):
            redacted[key] = "**REDACTED**"
    return redacted

def _runtime_snapshot(coordinator: Any) -> dict[str, Any] | None:
    """将协调器当前数据转为脱敏的诊断快照。"""
    data = coordinator.data
    if data is None:
        return None
    connections = data.connections or {}
    return _redact_dict(
        {
            "version": data.version,
            "meta": data.meta,
            "traffic": data.traffic,
            "memory": data.memory,
            "connections": {
                "download_total": connections.get("downloadTotal"),
                "upload_total": connections.get("uploadTotal"),
                "memory": connections.get("memory"),
                "active_connections": len(connections.get("connections", []) or []),
            },
            "configs": data.configs,
            "groups": [
                {
                    "name": g.name,
                    "type": g.type,
                    "now": g.now,
                    "supports_fixed": g.supports_fixed,
                    "fixed": g.fixed,
                    "test_url": g.test_url,
                    "hidden": g.hidden,
                    "all": g.all,
                }
                for g in data.groups
            ],
            "streaming": data.streaming,
            "provider_proxies": {
                "names": list(
                    (data.provider_proxies.get("providers", {}) or {}).keys()
                ),
                "count": len(data.provider_proxies.get("providers", {}) or {}),
            },
            "provider_rules": {
                "names": list(
                    (data.provider_rules.get("providers", {}) or {}).keys()
                ),
                "count": len(data.provider_rules.get("providers", {}) or {}),
            },
            "release": data.release,
        }
    )

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """导出配置项诊断：脱敏配置 + 运行时快照。"""
    coordinator = entry.runtime_data.coordinator
    return {
        "config_entry": {
            "data": _redact_config(dict(entry.data)),
            "options": dict(entry.options),
        },
        "runtime": _runtime_snapshot(coordinator),
    }

async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """导出设备级诊断：设备信息 + 该实例运行时快照。"""
    coordinator = entry.runtime_data.coordinator
    return {
        "device": {
            "name": device.name,
            "id": device.id,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.sw_version,
        },
        "runtime": _runtime_snapshot(coordinator),
    }