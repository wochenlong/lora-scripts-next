# 分发许可内容清单

主项目与独立helper声明为 AGPL-3.0-or-later。分发应保留仓库根 `LICENSE` 完整文本和 `NOTICE.md` 上游致谢。本文是内容索引，第三方原始许可仍以对应版本上游文件为准。

| 内容 | 生成或来源 | 适用范围 |
| --- | --- | --- |
| `LICENSE` | 仓库根原件，打包时复制 | 主项目 AGPL 完整文本 |
| `NOTICE.md` | 仓库根原件，打包时复制 | 秋叶训练包、sd-scripts 等上游致谢与集成关系 |
| `dependencies.json` | 两个 Cargo.lock 与 package-lock.json | 壳/helper/前端及构建工具依赖、版本和声明许可 |
| `THIRD-PARTY-NOTICES.md` | 本机锁定版本缓存中的原始 LICENSE/COPYING/NOTICE | 本次可提取的第三方许可原文与出处 |
| `windows-delivery.md` | `docs/launcher/windows-delivery.md`，打包时复制 | 安装、诊断、恢复、卸载保留资料与未验证边界 |
| `build-manifest.json` / 哈希清单 | 交付构建脚本 | 训练器提交、壳构建提交、catalog/recipe摘要、候选包身份 |

生成命令：`python desktop-launcher/scripts/generate_license_inventory.py`。脚本只读取已锁定依赖与本机缓存，不下载依赖，不修改环境。它记录缓存缺失或未发现原始许可文件的情况；依赖声明许可、原文可用性和是否编入当前平台是不同事实，不将缺失内容自动称为合规完成。锁文件变化后需重新生成清单。

当前清单包含534个锁定依赖，其中184个本机无缓存（包含其他平台和可选依赖），149个声明许可未从缓存取得，192个未取得包内完整原始许可文本。另已提取`selectors`源码许可头、两个Windows工具平台包同版本主包的关联许可，并单独标注来源；这些关联声明不冒充缺失的包内完整原文。真实生产分发仍须按实际编入和携带的组件收齐所需声明。

主要壳组件包括 Tauri（MIT OR Apache-2.0）、Vue（MIT）、ring（Apache-2.0 AND ISC）、sha2（MIT OR Apache-2.0）、fs2（MIT/Apache-2.0）等。完整版本与实际缓存提取情况参见生成文件。

Microsoft WebView2 Runtime / 安装引导程序按 Microsoft 自身条款提供，不归入项目 AGPL 许可；生产分发前应使用官方来源并核对适用再分发条款。系统 Windows 组件不由本项目重新授权。

训练引擎、Python、uv 与安装时下载的 wheels 有各自独立许可。其资产身份、来源、许可与收据应随对应安装内容保留，不把“桌面壳许可清单”当作已安装的全部训练环境许可。模型、数据集和用户作品由其权利人另行授权。
