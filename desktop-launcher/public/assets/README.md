# 启动器品牌资源

- `home-logo.webp`：原样复制仓库 `frontend/public/assets/home-logo.webp`，由用户指定为启动器统一 Logo。品牌栏、首页、关于页、网页图标使用同一源图。
- `guide-mascot.webp`：复制仓库 `frontend/public/assets/guide-mascot.webp`，用于启动器背景合成。
- `launcher-wallpaper.webp`：1920×1080 默认背景，由项目角色、深蓝灰渐变与程序绘制的几何线条合成。未使用 Starward 游戏插画或用户截图。
- 应用 ICO / PNG / ICNS：均由 `home-logo.webp` 缩放生成，位于 `src-tauri/icons`。

可在仓库根运行 `python desktop-launcher/scripts/generate_brand_assets.py` 重建上述产品资源，需安装 Pillow。资源沿用仓库原有品牌资产的使用范围；背景合成不引入外部图片、字体或网络依赖。审稿目录中的游戏截图仍仅作为视觉参考，不进入产品资源。
