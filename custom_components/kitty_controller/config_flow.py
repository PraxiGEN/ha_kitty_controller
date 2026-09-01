"""Kitty Controller 配置流。"""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from yarl import URL

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .api import (
    APIAuthError,
    APIConnectionError,
    APIClientError,
    APITimeoutError,
    KittyAPI,
)
from .const import (
    CONF_ALLOW_UNSAFE,
    CONF_API_URL,
    CONF_BEAR_TOKEN,
    CONF_DEFAULT_GROUPS,
    CONF_DEVICE_NAME,
    CONF_STREAMING_DETECTION,
    CONF_USE_SSL,
    DEFAULT_DEFAULT_GROUPS,
    DEFAULT_DEVICE_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STREAMING_DETECTION,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

class KittyControllerConfigFlow(ConfigFlow, domain=DOMAIN):
    """处理小猫咪控制器的配置流。"""

    VERSION = 1

    def _normalize_url(self, api_url: str, use_ssl: bool):
        """规范化 API 地址：统一协议前缀与末尾斜杠。"""
        if api_url.startswith("http://") or api_url.startswith("https://"):
            if use_ssl and api_url.startswith("http://"):
                api_url = api_url.replace("http://", "https://", 1)
            elif not use_ssl and api_url.startswith("https://"):
                api_url = api_url.replace("https://", "http://", 1)
        else:
            api_url = f"https://{api_url}" if use_ssl else f"http://{api_url}"
        if not api_url.endswith('/'):
            api_url += '/'
        return api_url

    async def _test_connection(self, api: KittyAPI) -> dict[str, str]:
        """公用连接测试逻辑。"""
        errors = {}
        try:
            if not await api.connected():
                errors["base"] = "cannot_connect"
        except APIAuthError:
            errors["base"] = "invalid_token"
        except APITimeoutError:
            errors["base"] = "timed_out"
        except (APIClientError, APIConnectionError):
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("测试小猫咪连接时出现意外错误")
            errors["base"] = "unknown"
        return errors

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """处理初始配置步骤。"""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_url = self._normalize_url(user_input[CONF_API_URL], user_input.get(CONF_USE_SSL, False))
            user_input[CONF_API_URL] = api_url
            unique_id = re.sub(r"[^a-zA-Z0-9]", "_", api_url)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            api = KittyAPI(
                self.hass,
                api_url,
                user_input[CONF_BEAR_TOKEN],
                allow_unsafe=user_input.get(CONF_ALLOW_UNSAFE, False),
            )
            errors = await self._test_connection(api)
            if not errors:

                return self.async_create_entry(
                    title=f"KittY ({URL(api_url).host})", data=user_input
                )

        # 设备名称置于最顶部（默认"哈基咪"，可改），其余为连接参数
        data_schema = vol.Schema({
            vol.Optional(CONF_DEVICE_NAME, default=DEFAULT_DEVICE_NAME): cv.string,
            vol.Required(CONF_API_URL): cv.string,
            vol.Required(CONF_BEAR_TOKEN): cv.string,
            vol.Optional(CONF_USE_SSL, default=False): cv.boolean,
            vol.Optional(CONF_ALLOW_UNSAFE, default=False): cv.boolean,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(data_schema, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """处理重新配置流程。"""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_url = self._normalize_url(user_input[CONF_API_URL], user_input.get(CONF_USE_SSL, False))
            api = KittyAPI(
                self.hass,
                api_url,
                user_input[CONF_BEAR_TOKEN],
                allow_unsafe=user_input.get(CONF_ALLOW_UNSAFE, False),
            )
            errors = await self._test_connection(api)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, **user_input, CONF_API_URL: api_url}
                )

        # 预填当前数据（设备名称置于最顶部，与初始配置保持一致）
        data_schema = vol.Schema({
            vol.Optional(CONF_DEVICE_NAME): cv.string,
            vol.Required(CONF_API_URL): cv.string,
            vol.Required(CONF_BEAR_TOKEN): cv.string,
            vol.Optional(CONF_USE_SSL): cv.boolean,
            vol.Optional(CONF_ALLOW_UNSAFE): cv.boolean,
        })

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(data_schema, user_input or entry.data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KittyControllerOptionsFlow:
        """开启选项流处理器。"""
        return KittyControllerOptionsFlow()

class KittyControllerOptionsFlow(OptionsFlowWithReload):
    """运行时选项更新（保存后由框架自动重新加载条目）。"""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """选项设置主步骤。"""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema({
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Clamp(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),

            vol.Optional(
                CONF_STREAMING_DETECTION,
                default=self.config_entry.options.get(CONF_STREAMING_DETECTION, DEFAULT_STREAMING_DETECTION)
            ): cv.boolean,

            # 额外默认启用组关键词（逗号分隔）：叠加在内置关键词之上
            vol.Optional(
                CONF_DEFAULT_GROUPS,
                default=self.config_entry.options.get(CONF_DEFAULT_GROUPS, DEFAULT_DEFAULT_GROUPS)
            ): cv.string,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                options_schema, user_input
            ),
        )