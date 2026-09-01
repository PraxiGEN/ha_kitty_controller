"""Kitty Controller 数据协调器。"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KittyAPI
from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STREAMING_DETECTION,
    DEFAULT_DEVICE_NAME,
    CONF_STREAMING_DETECTION,
    CONF_DEVICE_NAME,
    CONF_DEFAULT_GROUPS,
)

_LOGGER = logging.getLogger(__name__)

def slugify(value: str) -> str:
    """转安全 ID 片段：保留中文与 ASCII 字母数字，其余替换为下划线。"""
    slug = re.sub(r"[^\w]+", "_", value.lower().replace(" ", "_")).strip("_")
    if not slug:
        slug = hashlib.md5(value.encode("utf-8")).hexdigest()[:10]
    return slug

# 组选择器"默认启用"关键词：组名包含任一关键词（不区分大小写）时首次注册默认启用
DEFAULT_ENABLED_GROUP_KEYWORDS: frozenset[str] = frozenset(
    {"global", "自动", "选择", "漏网", "direct"}
)
# 核心版本检查间隔（GitHub API 无 token 配额 60 次/小时，6 小时查一次足够）
UPDATE_CHECK_INTERVAL: timedelta = timedelta(hours=6)

@dataclass(slots=True)
class KittyGroup:
    """单个代理组的纯数据模型。"""

    name: str
    type: str
    now: str | None = None
    all: list[str] = field(default_factory=list)
    supports_fixed: bool = False
    fixed: str | None = None
    test_url: str | None = None
    hidden: bool = False
    icon: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class KittyData:
    """协调器产出的完整数据模型。"""

    version: str | None = None
    meta: bool = False
    traffic: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    connections: dict[str, Any] = field(default_factory=dict)
    configs: dict[str, Any] = field(default_factory=dict)
    groups: list[KittyGroup] = field(default_factory=list)
    streaming: dict[str, Any] = field(default_factory=dict)
    provider_proxies: dict[str, Any] = field(default_factory=dict)
    provider_rules: dict[str, Any] = field(default_factory=dict)
    release: dict[str, str] | None = None

class KittyControllerCoordinator(DataUpdateCoordinator[KittyData]):
    """从内核 API 拉取数据并组装为 KittyData。"""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """初始化协调器。"""
        self.host = config_entry.data["api_url"]
        self.token = config_entry.data["bearer_token"]
        self.allow_unsafe = config_entry.data.get("allow_unsafe", False)
        self.config_entry = config_entry
        self.entry_id = config_entry.entry_id
        self.poll_interval = config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        self.streaming_detection = config_entry.options.get(
            CONF_STREAMING_DETECTION, DEFAULT_STREAMING_DETECTION
        )
        # 设备名称：仅显示用（默认"哈基咪"，可在配置流修改），不参与 unique_id 派生
        self.device_name = (
            config_entry.data.get(CONF_DEVICE_NAME, "").strip() or DEFAULT_DEVICE_NAME
        )
        # 选项流配置的额外默认启用组关键词（逗号分隔，小写化）
        raw_keywords = config_entry.options.get(CONF_DEFAULT_GROUPS, "")
        self.default_group_keywords = {
            k.strip().lower() for k in raw_keywords.split(",") if k.strip()
        }

        # 版本检查节流（monotonic 时间戳）与最近一次成功结果缓存
        self._last_release_check: float = 0.0
        self._release_info: dict[str, str] | None = None

        self.api = KittyAPI(
            hass,
            host=self.host,
            token=self.token,
            allow_unsafe=self.allow_unsafe,
        )

        super().__init__(
            hass,
            _LOGGER,
            name=self.device_name,
            update_method=self._async_update_data,
            update_interval=timedelta(seconds=self.poll_interval),
        )

    @property
    def device_info(self) -> DeviceInfo:
        """设备信息：标识符用 entry_id（稳定、与 IP 等易变字段无关）。"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry_id)},
            name=f"{self.device_name}",
            manufacturer="MetaCubeX",
            model="Mihomo",
            sw_version=self.data.version if self.data else None,
            configuration_url=f"{self.host}ui"
        )

    async def _async_update_data(self) -> KittyData:
        """拉取内核数据并组装为 KittyData。"""
        try:
            response = await self.api.fetch_data(streaming_detection=self.streaming_detection)
        except Exception as err:
            raise UpdateFailed(err) from err

        if not response:
            raise UpdateFailed("小猫咪核心未返回任何数据。")

        # 低频查询 GitHub 最新版本；成功更新缓存、失败保留旧值，无论成败都重置计时
        now = time.monotonic()
        if now - self._last_release_check >= UPDATE_CHECK_INTERVAL.total_seconds():
            self._last_release_check = now
            result = await self.api.get_latest_release()
            if result is not None:
                self._release_info = result
                _LOGGER.debug("获取小猫咪最新版本: %s", result.get("tag_name"))
            else:
                _LOGGER.warning(
                    "无法获取小猫咪最新版本信息，核心更新检查传感器将显示'检测中'。"
                    "下次重试将在 %d 小时后。",
                    int(UPDATE_CHECK_INTERVAL.total_seconds() // 3600),
                )
        response["release"] = self._release_info

        return self._assemble_data(response)

    @staticmethod
    def _assemble_data(response: dict[str, Any]) -> KittyData:
        """将原始响应组装为纯数据模型。"""
        version = response.get("version", {})
        if not isinstance(version, dict):
            version = {}
        return KittyData(
            version=version.get("version"),
            meta=bool(version.get("meta", False)),
            traffic=response.get("traffic", {}) or {},
            memory=response.get("memory", {}) or {},
            connections=response.get("connections", {}) or {},
            configs=response.get("configs", {}) or {},
            groups=KittyControllerCoordinator._build_groups(response.get("proxies", {})),
            streaming=response.get("streaming", {}) or {},
            provider_proxies=response.get("providers_proxies", {}) or {},
            provider_rules=response.get("providers_rules", {}) or {},
            release=response.get("release"),
        )

    @staticmethod
    def _build_groups(proxies: dict[str, Any]) -> list[KittyGroup]:
        """从代理数据中提取所有策略组（以"含 all 成员列表"为判据，普通节点无 all 字段）。"""
        groups: list[KittyGroup] = []
        proxy_map = proxies.get("proxies", {}) if isinstance(proxies, dict) else {}
        for item in proxy_map.values():
            if not isinstance(item, dict):
                continue
            if not isinstance(item.get("all"), list):
                continue
            gtype = item.get("type")
            fixed = item.get("fixed")
            supports_fixed = "fixed" in item
            attr_keys = [
                "tfo",
                "type",
                "udp",
                "xudp",
                "alive",
                "history",
                "all",
                "expectedStatus",
                "testUrl",
                "lastTestTime",
            ]
            attributes = {k: item[k] for k in attr_keys if k in item}
            groups.append(
                KittyGroup(
                    name=item.get("name", ""),
                    type=gtype,
                    now=item.get("now"),
                    all=item.get("all", []) or [],
                    supports_fixed=supports_fixed,
                    fixed=fixed,
                    test_url=item.get("testUrl"),
                    hidden=item.get("hidden", False),
                    icon=item.get("icon"),
                    attributes=attributes,
                )
            )
        return groups