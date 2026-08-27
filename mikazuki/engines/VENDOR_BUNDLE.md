# Vendor 源码分发包（vendor-bundle）

> 弱网/生产环境的离线源码分发方式：把各引擎**钉版 commit 的生产代码**打成一个包放在
> `vendor/` 下，引擎安装时自动解压，全程不碰网络、不需要 git。

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

- **行为**：引擎 resolve 源码时发现 `vendor/<dir>` 缺失且 bundle 存在 → 整个包解压到
  `vendor/`（同一 bundle 只解一次，marker：`vendor/.vendor_bundle_extracted`，按
  **包名 + SHA-256 摘要**识别）→ 之后按 vendor 源码直通安装。目录内容已是钉版
  commit（凭 `.source_commit` 认定，必须为完整 40 位 sha），installer 不再要求
  git checkout。
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
- 只打包引擎 manifest 钉的版本；版本升级 = 重新打包并替换 bundle
  （解压 marker 按包名 + SHA-256 识别，换新包会自动重解一次）。
- tar 系格式把最后两步换成 `(cd "$BUNDLE" && tar -czf vendor-bundle.tar.gz .)`。
