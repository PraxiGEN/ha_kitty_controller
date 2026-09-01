# <img src="custom_components/kitty_controller/brand/icon.png" width="64"> KittY Controller for Home Assistant

[![Release](https://img.shields.io/github/v/release/PraxiGEN/ha_kitty_controller)](https://github.com/PraxiGEN/ha_kitty_controller/releases)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/PraxiGEN/ha_kitty_controller/blob/main/LICENSE)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

## 小猫咪（KittY Controller）是专为 Home Assistant 打造的 mihomo内核 管理集成插件。完全基于内核官方 REST API 构建，提供纯异步、稳定且安全的网络监控与自动化体验。

## 重点：只支持 mihomo 系内核，不支持旧版 Clash。

## ✨ 核心特性

- 🚀 **纯异步架构**: 基于 Python 异步与 `aiohttp`，协调器并发拉取内核数据，监控刷新无卡顿。
- 🏗️ **多实例支持**: 可同时添加多个内核实例，每个实例独立成设备，实体互不干扰。
- 📊 **深度监控**:
  - **实时速率**: 上传 / 下载速度，秒级刷新。
  - **累计流量**: 上传 / 下载总量统计。
  - **资源状态**: 内存占用、活动连接数。
  - **集合统计**: 代理集合、规则集合数量。
  - **版本检查**: 自动对比内核最新版本，配合升级按钮实现一键更新。
- 🎮 **灵活控制**:
  - **代理模式**: 规则 / 全局 / 直连 / 脚本一键切换。
  - **代理组选择器**: 每个策略组一个下拉选择器，秒切节点。
  - **缓存清理**: 清除 FakeIP、DNS 缓存。
  - **内核升级**: 一键升级内核与 GEO 数据库。
- 🔔 **流媒体检测**: 可选探测流媒体解锁状态（Netflix）。
- 🔧 **强大服务**: 9 个内置服务（筛选连接、测延迟、DNS 查询、更新订阅、集合健康检查等），多数支持返回结果，可自由接入自动化。
- 🔐 **安全认证**: 使用内核官方 Bearer Token，无需暴露面板密码。

## 📦 安装

### 通过 HACS 安装（推荐）

1. 在 HACS 的"集成"部分，点击右上角的三点菜单
2. 选择"自定义存储库"
3. 在存储库字段输入：
   ```yaml
   https://github.com/PraxiGEN/ha_kitty_controller
   ```
4. 类别选择"集成"
5. 点击"添加"保存
6. 在 HACS 中找到"KittY Controller"集成并点击安装
7. 重启 Home Assistant

### 手动安装

1. 下载最新的:
   ```yaml
   https://github.com/PraxiGEN/ha_kitty_controller
   ```
2. 解压并将 `kitty_controller` 文件夹放入 Home Assistant 的 `custom_components` 目录
3. 重启 Home Assistant

## 📖 文档导航
- [🚀 详细配置与使用教程 (DOCS.md)](md/DOCS.md)
- [📜 版本更新历史 (CHANGELOG.md)](md/CHANGELOG.md)

## 📜 声明

- 本项目与 MetaCubeX / mihomo 官方无直接隶属关系。
- 请遵守内核的 API 使用协议。

## 🤝 贡献

欢迎贡献代码、报告问题或提出功能建议！

1. 提交 Issues：报告问题或功能请求
2. 提交 Pull Requests：贡献代码改进
3. 项目讨论：分享使用经验或建议

## 📄 许可证

本项目基于 MIT 许可证开源。详情请查看 LICENSE 文件。

## ❤️ 支持

如果这个项目对您有帮助，请给项目点个 Star ⭐！

---
**兼容版本**:

- **Home Assistant 2026.1+**

- **为确保集成品牌图片正确显示，请选择 Home Assistant 2026.3+**

  为确保品牌图标能够正确显示，建议使用 HA 2026.3 或更高版本。
  从 2026.3 起，Home Assistant 引入了 custom_integrations 目录与 Brands Proxy API，自定义集成可以在自身目录中直接包含品牌图片。

- **mihomo 系内核**

  仅兼容 mihomo 系内核官方 REST API，不支持旧版 Clash。
