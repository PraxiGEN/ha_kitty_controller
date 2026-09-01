"""Kitty Controller API 客户端。"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

# 协调器每轮轮询的固定端点：(数据键, 端点路径)，全部为 GET
_POLL_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("version", "version"),
    ("traffic", "traffic"),
    ("memory", "memory"),
    ("connections", "connections"),
    ("proxies", "proxies"),
    ("configs", "configs"),
    ("providers_proxies", "providers/proxies"),
    ("providers_rules", "providers/rules"),
)
# 流式子端点：/traffic 与 /memory 每秒推送一帧、连接保持打开不以 EOF 结束，
# 不能用 response.json() 整体解析（会读到超时），改用 _fetch_stream_sample 取首帧
_STREAM_ENDPOINTS: frozenset[str] = frozenset({"traffic", "memory"})
# 部分 POST 端点（如 restart、upgrade）要求携带此空请求体
RESTART_BODY: dict[str, str] = {"path": "", "payload": ""}
# 流媒体解锁探测服务表
SERVICE_TABLE: dict[str, dict[str, Any]] = {
    "netflix": {
        "name": "Netflix",
        "icon": "mdi:netflix",
        "url": "https://www.netflix.com/title/81280792",
        "code_table": {
            200: "unlocked",
            403: "blocked",
            404: "original_only",
            0: "unavailable",
        },
    },
}
# 内核 REST API 无"检查更新"端点，版本对比只能走 GitHub 官方接口；
# 无 token 配额 60 次/小时，协调器按 6 小时间隔查询一次，远低于配额。
GITHUB_LATEST_RELEASE_URL: str = (
    "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest"
)

class APIAuthError(Exception):
    """认证失败（HTTP 401）。"""

class APIClientError(Exception):
    """通用 API 客户端错误。"""

class APITimeoutError(Exception):
    """请求超时。"""

class APIConnectionError(Exception):
    """无法建立连接。"""

class KittyAPI:
    """内核 REST API 异步客户端（会话由 HA 核心托管，无需手动关闭）。"""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        token: str,
        *,
        allow_unsafe: bool = False,
    ) -> None:
        """初始化客户端。"""
        self.hass = hass
        # 端点拼接不含前导斜杠，host 必须保留末尾斜杠
        self.host = host if host.endswith("/") else f"{host}/"
        self.token = token
        self.allow_unsafe = allow_unsafe
        self._session = async_get_clientsession(hass, verify_ssl=not allow_unsafe)

    def _headers(self) -> dict[str, str]:
        """请求头。"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def async_request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """发起请求，返回解析后的 JSON（204 空响应返回 None）。"""
        url = f"{self.host}{endpoint}"
        _LOGGER.debug("小猫咪 API %s %s", method, url)
        try:
            async with self._session.request(
                method,
                url,
                params=params,
                json=json_data,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 204:
                    return None
                response.raise_for_status()
                if response.content_type == "application/json":
                    return await response.json()
                text = await response.text()
                if not text:
                    return None
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return None
        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                raise APIAuthError("无效的小猫咪 API 令牌。") from err
            raise APIClientError(
                f"小猫咪 API 返回 HTTP {err.status}（{endpoint}）"
            ) from err
        except asyncio.TimeoutError as err:
            raise APITimeoutError(f"小猫咪 API 请求超时: {err}") from err
        except aiohttp.ClientConnectionError as err:
            raise APIConnectionError(f"小猫咪 API 连接错误: {err}") from err
        except Exception as err:
            raise APIClientError(f"小猫咪 API 意外错误: {err}") from err

    async def connected(self) -> bool:
        """探测内核是否可达且认证通过。"""
        response = await self.async_request("GET", "version")
        if not isinstance(response, dict) or "version" not in response:
            raise APIClientError("/version 响应格式异常。")
        return True

    async def get_version(self) -> dict[str, str]:
        """读取内核版本信息（/version）。"""
        response = await self.async_request("GET", "version")
        if not isinstance(response, dict):
            return {"meta": False, "version": "unknown"}
        return {
            "meta": bool(response.get("meta", False)),
            "version": str(response.get("version", "unknown")),
        }

    async def fetch_data(self, streaming_detection: bool = False) -> dict[str, Any]:
        """并发拉取全部轮询端点并组装为键值字典。"""
        tasks = []
        for key, endpoint in _POLL_ENDPOINTS:
            if key in _STREAM_ENDPOINTS:
                tasks.append(self._fetch_stream_sample(endpoint))
            else:
                tasks.append(self.async_request("GET", endpoint))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        data: dict[str, Any] = {}
        for (key, _), result in zip(_POLL_ENDPOINTS, results):
            if isinstance(result, Exception):
                _LOGGER.debug("获取 %s 失败: %s", key, result)
                continue
            data[key] = result if isinstance(result, dict) else {}

        if streaming_detection:
            data["streaming"] = await self._fetch_streaming()
        return data

    async def _fetch_stream_sample(self, endpoint: str) -> dict[str, Any]:
        """读取流式子端点（/traffic、/memory）的最新一帧。"""
        url = f"{self.host}{endpoint}"
        _LOGGER.debug("小猫咪流式采样 %s", url)
        try:
            async with self._session.get(
                url,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                frame: dict[str, Any] = {}
                for _ in range(4):
                    line = await response.content.readline()
                    if not line:
                        break
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(parsed, dict):
                        continue
                    frame = parsed
                    # /memory 首帧为全 0 占位帧，跳过直到拿到真实 inuse
                    if "inuse" not in frame or frame.get("inuse"):
                        break
                return frame
        except asyncio.TimeoutError as err:
            raise APITimeoutError(f"小猫咪流式端点 {endpoint} 读取超时: {err}") from err
        except aiohttp.ClientResponseError as err:
            if err.status == 401:
                raise APIAuthError("无效的小猫咪 API 令牌。") from err
            raise APIClientError(
                f"小猫咪 API 返回 HTTP {err.status}（{endpoint}）"
            ) from err
        except aiohttp.ClientConnectionError as err:
            raise APIConnectionError(f"小猫咪 API 连接错误: {err}") from err
        except (json.JSONDecodeError, ValueError) as err:
            raise APIClientError(f"小猫咪流式端点 {endpoint} 解析失败: {err}") from err
        except Exception as err:  # noqa: BLE001 - 单个端点失败不影响整体更新
            raise APIClientError(f"小猫咪 API 意外错误: {err}") from err

    async def _fetch_streaming(self) -> dict[str, Any]:
        """探测第三方流媒体服务，返回解锁状态映射。"""
        results = await asyncio.gather(
            *[self.get_url_status(details["url"]) for details in SERVICE_TABLE.values()],
            return_exceptions=True,
        )
        streaming: dict[str, Any] = {}
        for service, result in zip(SERVICE_TABLE, results):
            if isinstance(result, Exception):
                _LOGGER.debug("流媒体探测 %s 失败: %s", service, result)
                streaming[service] = {"latency": -1, "status_code": 0}
            else:
                streaming[service] = result
        return streaming

    async def get_latest_release(self) -> dict[str, str] | None:
        """查询内核最新正式版信息（GitHub Releases API）。"""
        session = async_get_clientsession(self.hass, verify_ssl=False)
        try:
            async with session.get(
                GITHUB_LATEST_RELEASE_URL,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    _LOGGER.debug("GitHub 返回 HTTP %s", response.status)
                    return None
                payload = await response.json()
                tag = str(payload.get("tag_name", "")).strip()
                if not tag:
                    return None
                return {
                    "tag_name": tag,
                    "published_at": str(payload.get("published_at", "")),
                }
        except asyncio.TimeoutError as err:
            _LOGGER.debug("查询小猫咪最新版本超时: %s", err)
            return None
        except aiohttp.ClientError as err:
            _LOGGER.debug("查询小猫咪最新版本失败: %s", err)
            return None
        except Exception as err:  # noqa: BLE001 - 版本检查失败不影响整体功能
            _LOGGER.error("查询小猫咪最新版本异常: %s", err)
            return None

    async def get_url_status(
        self, url: str, headers: dict[str, str] | None = None
    ) -> dict[str, float | int]:
        """探测指定 URL，返回延迟与状态码。"""
        session = async_get_clientsession(self.hass, verify_ssl=False)
        request_headers = headers or {}
        start_time = time.monotonic()
        try:
            async with session.get(url, headers=request_headers) as response:
                duration = time.monotonic() - start_time
                return {"latency": duration, "status_code": response.status}
        except asyncio.TimeoutError:
            return {"latency": -1, "status_code": 0}
        except aiohttp.ClientError as err:
            duration = time.monotonic() - start_time
            _LOGGER.debug("流媒体探测错误 %s: %s", url, err)
            return {"latency": duration, "status_code": 0}
        except Exception as err:  # noqa: BLE001 - never crash the update for a probe
            _LOGGER.error("流媒体探测错误 %s: %s", url, err)
            return {"latency": -1, "status_code": 0}