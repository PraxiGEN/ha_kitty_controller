"""Kitty Controller 常量。"""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "kitty_controller"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SELECT,
    Platform.BUTTON,
]

# 配置项
CONF_API_URL = "api_url"
CONF_BEAR_TOKEN = "bearer_token"
CONF_USE_SSL = "use_ssl"
CONF_ALLOW_UNSAFE = "allow_unsafe"
CONF_DEVICE_NAME = "device_name"
DEFAULT_DEVICE_NAME = "哈基咪"

# 选项
MIN_SCAN_INTERVAL = 10
DEFAULT_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 300
CONF_STREAMING_DETECTION = "streaming_detection"
DEFAULT_STREAMING_DETECTION = False
CONF_DEFAULT_GROUPS = "default_groups"
DEFAULT_DEFAULT_GROUPS = ""

# 服务名
API_CALL_SERVICE_NAME = "api_call_service"
DNS_QUERY_SERVICE_NAME = "dns_query_service"
FILTER_CONNECTION_SERVICE_NAME = "filter_connection_service"
GET_LATENCY_SERVICE_NAME = "get_latency_service"
GET_RULE_SERVICE_NAME = "get_rule_service"
REBOOT_CORE_SERVICE_NAME = "reboot_core_service"
UPDATE_RULE_PROVIDER_SERVICE_NAME = "update_rule_provider_service"
HEALTHCHECK_PROVIDER_SERVICE_NAME = "healthcheck_provider_service"
UPDATE_PROXY_PROVIDER_SERVICE_NAME = "update_proxy_provider_service"