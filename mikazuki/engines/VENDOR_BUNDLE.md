# Vendor 源码分发包（vendor-bundle）

> 弱网/生产环境的**一次性**离线源码分发方式：把各引擎**钉版 commit 的生产代码**打成
> 一个包放在 `vendor/` 下，首次安装时自动解压，全程不碰网络、不需要 git。

## 契约（一次性分发，不覆盖）

- **只展开，不覆盖**：`vendor/<dir>` 已存在时**永不覆盖、永不刷新**——bundle 只在
  目录缺失时被展开一次。换 bundle 不会触发任何替换。
- **我们解压的目录**：凭 extraction marker（包名 + SHA-256）识别，原样信任。
- **手动安装的目录（DIY）**：优先于 bundle，**仅告警**一行（「手动目录，不覆盖，
  版本不一致请自行对齐」），不阻塞、不报错——你 DIY 你负责。
- **升级路径**：不走 bundle。版本升级 = manifest 钉版 bump，旧快照的 `.source_commit`
  与新 pin 不匹配会被安装流程自动跳过，落到 **GitHub/Gitee clone** 拉取新钉版。
  如确需以 bundle 内容为准，手动删除 `vendor/<dir>` 后重新触发安装。

## 约定

- **位置与命名**：`vendor/vendor-bundle.zip`（也认 `.tar.gz` / `.tgz` / `.tar`，按此顺序取第一个）。
- **内容结构**：包内**平铺**各引擎源码目录，目录名 = 引擎 vendor 目录名：

  ```text
  vendor-bundle.zip
  ├── musubi-tuner/        # kohya-ss/musubi-tuner @ manifest 钉版 commit
  │   ├── .source_commit   # 完整 commit sha（必填，一行）
  │   ├── pyproject.toml
  │   └── src/...
  ├── anima_lora/          # sorryhyun/anima_lora @ manifest 钉版 commit
  │   ├── .source_commit
  │   └── train.py ...
  └── sd-scripts/ ...      # 可选，其他 vendor 目录同理
  ```

- **行为**：引擎 resolve 源码时发现 `vendor/<dir>` 缺失且 bundle 存在 → 经 staging
  目录原子展开到 `vendor/`（同一 bundle 只解一次，marker：
  `vendor/.vendor_bundle_extracted`，按**包名 + SHA-256 摘要**识别）→ 之后按
  vendor 源码直通安装。目录内容已是钉版 commit（凭 `.source_commit` 认定，必须为
  完整 40 位 sha），installer 不再要求 git checkout。
- **优先级**：bundle → `vendor/<dir>` 已有目录 → GitHub clone →（Gitee 镜像，未实现）。
- **不入 git**：bundle 是分发物（整合包内带 / release 附件），仓库只约定格式。

## 打包办法

在每个引擎的源码 clone 里，先 checkout 到 manifest 钉的 commit，用 `git archive`
导出该版本完整代码（这就是"生产代码快照"），再写上 `.source_commit`：

```bash
BUNDLE=$(mktemp -d)

# musubi-tuner（commit 见 mikazuki/engines/musubi/manifest.py UPSTREAM）
git -C musubi-tuner archive --format=tar --output=/tmp/musubi.tar <commit>
mkdir -p "$BUNDLE/musubi-tuner"
tar -xf /tmp/musubi.tar -C "$BUNDLE/musubi-tuner"
git -C musubi-tuner rev-parse <commit> > "$BUNDLE/musubi-tuner/.source_commit"

# anima_lora（commit 见 mikazuki/engines/anima_fast/manifest.py UPSTREAM）
git -C anima_lora archive --format=tar --output=/tmp/anima.tar <commit>
mkdir -p "$BUNDLE/anima_lora"
tar -xf /tmp/anima.tar -C "$BUNDLE/anima_lora"
git -C anima_lora rev-parse <commit> > "$BUNDLE/anima_lora/.source_commit"

# 打成 zip 放进项目
(cd "$BUNDLE" && zip -qr vendor-bundle.zip .)
cp "$BUNDLE/vendor-bundle.zip" /path/to/lora-scripts-next/vendor/
```

注意：

- `.source_commit` 必须写**完整 sha**（`git rev-parse <commit>` 的输出），安装时按
  前缀比对认定快照版本。
- 只打包引擎 manifest 钉的版本；它是**一次性安装分发物**——版本升级不换新 bundle，
  走 GitHub/Gitee clone（见上方「契约」）。
- tar 系格式把最后两步换成 `(cd "$BUNDLE" && tar -czf vendor-bundle.tar.gz .)`。
