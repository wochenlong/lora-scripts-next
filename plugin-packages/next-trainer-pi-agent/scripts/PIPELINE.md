# 插件开发管线（CR-012，win32-x64 + linux-x64）

## 完整开发流程（三层环路，由快到慢）

日常改插件**不要**每次都打包重装。三层环路各管一段：

### Loop A — 快速开发（改 pi-web 源码的日常环路，秒级反馈）

```powershell
.\.venv-dev\Scripts\python.exe plugin-packages\next-trainer-pi-agent\scripts\dev-pi-web.py
```

- 直接在**工作树**（`plugin-packages/next-trainer-pi-agent/pi-web/`）跑 Next.js HMR dev server，`http://127.0.0.1:30141/`，改完保存即热更新，**零打包、零重装、脱离宿主**。
- 默认共享已安装插件实例的会话库（`.runtime/plugin-marketplace/data/next-trainer-pi-agent/pi-agent`，即浮动对话框里看到的那些会话）；`--agent-dir <path>` 可指定，不存在时落隔离目录。
- HOME/APPDATA/TMP 全部隔离在 `plugin-packages/next-trainer-pi-agent/.runtime/dev/`，不碰你的真实用户目录。
- `--port N` 换端口。
- 注意：**dev 运行期间不要跑 `next build` / 打包管线**（pi-web 上游约定：会污染 `.next` 弄坏 HMR）。

### Loop B — 免打包契约预览（改 launcher 时用）

```powershell
.\.venv-dev\Scripts\python.exe plugin-packages\next-trainer-pi-agent\scripts\dev-pi-web.py --launcher
```

- 重新编译工作树 `bin/next-trainer-pi-agent.exe`（bun，~40s）→ 以**工作树为包根**跑真实宿主契约：临时端口、READY 行、Bearer /health、uiUrl 探活。
- Ctrl+C 退出：launcher 的父进程死亡监控会自行拆掉 pi-web 树，脚本最后打印 scoped 残留数（应为 0）。
- `--built` 是同级的中间档：服务**打包过的 .next**（先跑过 Loop C 或 `npm run build`），不打包就能验证"构建产物"形态的行为（端口 30142）。

### Loop C — 集成发布（满意后，进宿主）

```powershell
.\.venv-dev\Scripts\python.exe plugin-packages\next-trainer-pi-agent\scripts\build-all-platforms.py
```

- 一条命令重建双端包 + 双平台 dev catalog（详见下节）。
- **运行前停掉 Loop A 的 dev server**（共享 `.next`）。
- 之后：UI 市场页 refresh → uninstall + install 插件 → 浮动对话框里验收；可选 `e2e-pi-web-plugin.py`（Windows 12 步）/ `wsl-contract-test.sh`（Linux 契约）。
- 打包后想回 Loop A 继续开发：dev server 直接起即可（若 HMR 异常，删 `pi-web/.next` 重来）。

### 打包命令（Loop C 详情）

修改插件后，用**一条命令**重建两个平台的安装包与双平台 dev catalog：

```powershell
# 在 project/ 下执行
.\.venv-dev\Scripts\python.exe plugin-packages\next-trainer-pi-agent\scripts\build-all-platforms.py
```

## 模式

| 命令 | 适用场景 | 大致耗时 |
|---|---|---|
| `build-all-platforms.py`（默认 full） | 改了 pi-web 源码 / launcher / 混合改动 | ~20–25 min |
| `build-all-platforms.py --launcher-only` | 只改 `launcher/src/main.ts` | ~10 min（WSL 树热时更快） |
| `build-all-platforms.py --piweb-only` | 只改 `pi-web/` 源码（复用现有 launcher 二进制） | ~15 min |

可选：`--distro <name>` 指定 WSL 发行版（默认 `kali-linux`）。

## full 模式做了什么（7 步）

1. **定位 bun 1.4.0**（npx 缓存，逐候选校验 `--version`；缺失时 `npm exec -y bun@1.4.0` 取回——在 project 根执行以避免插件包内本地 `node_modules/bun` 遮蔽），然后交叉编译两个 launcher：
   - `bin/next-trainer-pi-agent.exe`（bun-windows-x64）
   - `bin/next-trainer-pi-agent`（bun-linux-x64 ELF）
2. **Windows pi-web 构建**：在 `pi-web/` 工作树内用 dev-runtimes 的 Node 22.19.0 跑 `npm run build`（`next build --webpack`），得到与源码一致的 `.next`。工作树的 dev `node_modules` 保持不变（可继续跑测试/dev server）。
3. **Windows zip**：`build-pi-web-package.py --zip-only`（暂存 → `npm prune --omit=dev` → dist-types 剥离 → lockfile 逐字还原 → zip）。产物 `dist-marketplace/packages/next-trainer-pi-agent-0.2.0-win32-x64.zip`。
4. **Linux zip**（三段，避免 1.3 GB 数据过 9p 桥）：
   - Windows 侧打源码 tar（`pi-web/` 全量，排除 `node_modules`/`.next`，落 `plugin-packages/next-trainer-pi-agent/.runtime/linux-src.tar.gz`，并校验 0 泄漏）；
   - `scripts/wsl/wsl-build-pi-web.sh`（WSL 内）：自备 Node 22.19.0 linux → `npm ci`（WSL NAT 不稳：fetch-retries + 缓存续传，最多 3 次）→ `next build --webpack` → prune → dist-types 剥离 → lockfile 逐字还原 → 冒烟（server 启动 + `/` + `/api/sessions` 200）；
   - `scripts/wsl/wsl-stage-linux-package.sh`（WSL 内）：组装包布局（ELF launcher + node + 全量 pi-web + plugin.json/LICENSES/NOTICE/SBOM）→ python3 zipfile 打包（保留 unix 权限位、跳过链接、排序确定性）→ 只把 zip 写回 `dist-marketplace/packages/`。
5. **双平台 catalog**：`build-marketplace-catalog.py`——读两份 zip，生成单条目双平台 entry（平铺字段=win32 主绑定 + `packages` 平台绑定），dev HMAC 签名，并逐平台跑宿主 validator 自检（inspect_package + manifest 平台校验 + trust verify + compatibility）。任一门失败则整体失败。
6. **卫生**：删除 dev 后端旧 catalog 缓存（`.runtime/plugin-marketplace/catalog.json`）——旧 schema 签名的缓存在新宿主下必然 untrusted，删除后下次 refresh 重建。
7. **汇总**：打印两份 zip 路径/大小 + 后续步骤。

任一步失败 → 非零退出码 + `PIPELINE FAILED` 行，可安全重跑（幂等：每次重建覆盖旧产物；WSL 工作目录 `/tmp/nt-pi-linux` 每次清空，npm 缓存在 `~/.npm` 跨次保留）。

## 打完包之后

1. dev 后端（28000）在运行 → UI 市场页点 **refresh**（或重启后端），然后 **uninstall + install** 插件以获得新包（同版本号不触发自动更新）。
2. 可选验证：
   - Windows 端到端：`.\.venv-dev\Scripts\python.exe plugin-packages\next-trainer-pi-agent\scripts\e2e-pi-web-plugin.py`（12 步；残留计数已限定到本次运行数据根，可与常开 dev 后端共存）
   - Linux 契约：`wsl -d kali-linux -- bash plugin-packages/next-trainer-pi-agent/scripts/wsl/wsl-contract-test.sh`（READY/health/uiUrl/sessions/父死亡树杀 0 残留）
3. 宿主侧单测（改了宿主代码时）：`.\.venv-dev\Scripts\python.exe -m pytest tests/test_pi_agent_server_mode.py tests/test_plugin_marketplace.py tests/test_plugin_marketplace_api.py -q`

## 边界与已知约束

- **Linux 验证环境是 WSL2**（x86_64 glibc）；裸机 Linux 未在本机条件下验证。
- catalog 默认 **local/test** 形态（dev HMAC + 本地包根映射）。发布分发的三层能力（A1+B1，均已合入）：
  1. **在线获取（B1）**：宿主 `HttpPackageAcquirer` 按 catalog 固定 URL 分块下载，边下边算 sha256，完成后校验 size+sha256，网络/5xx 错误自动重试 2 次，支持中途取消；`MIKAZUKI_MARKETPLACE_PACKAGE_MIRROR` 可把 URL 重写到镜像基址（明文 HTTP 仅限回环，用于本地文件服务器做 release dry-run）。`build-marketplace-catalog.py --remote-base <https 基址>` 生成真实 URL 的 release 形态 catalog；`verify-release-distribution.py` 用本地 HTTP 文件服务器端到端验证整条分发路径。
  2. **发布签名（A1）**：`--signing-key-id/--signing-key-hex`（或 `MIKAZUKI_RELEASE_SIGNING_*` 环境变量）注入 release HMAC 密钥；密钥只存在于 release 操作者手中，不进仓库；对应 trust.json 随发布包分发。
  3. **一键包捆绑（A1）**：`build_portable.ps1` 步骤 2c 把 `dist-marketplace/{catalog.json,trust.json,packages/<当前平台>.zip}` 打进 `SD-Trainer\plugin-marketplace\`；宿主 `_local_catalog_wiring` 三级查找 env > 捆绑目录（cwd/plugin-marketplace/）> 失败封闭，用户拿到 release 一键包后可直接在市场页离线安装。
  公网分发（真实 release 资产 + 版本门控）仍是 release 授权事项，本仓库不创建 release。
- `packages` 字段需要 CR-012 之后的宿主版本；旧宿主会拒绝双平台 catalog（失败封闭，不会装错包）。
- pi-tui 无 linux native 二进制是上游设计（darwin/win32 平台增强，Linux 纯 JS 路径），无需处理。
- WSL 侧前置条件：发行版存在、网络可达 nodejs.org 与 registry.npmjs.org；不需要 xz（用 Node .tar.gz）、不需要 build tools（pi 包无 linux 编译步骤）。
