"""从仓库现有品牌资源生成桌面启动器图标与默认背景（需 Pillow）。"""

from pathlib import Path
import shutil

from PIL import Image


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    assets = repo / "desktop-launcher/public/assets"
    icons = repo / "desktop-launcher/src-tauri/icons"
    assets.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)
    for name in ("home-logo.webp", "guide-mascot.webp"):
        shutil.copyfile(repo / "frontend/public/assets" / name, assets / name)

    logo = Image.open(assets / "home-logo.webp").convert("RGBA")
    for name, size in (
        ("32x32.png", 32), ("128x128.png", 128),
        ("128x128@2x.png", 256), ("icon.png", 512),
    ):
        logo.resize((size, size), Image.Resampling.LANCZOS).save(icons / name)
    logo.save(
        icons / "icon.ico", format="ICO",
        sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)],
    )
    logo.resize((1024, 1024), Image.Resampling.LANCZOS).save(
        icons / "icon.icns", format="ICNS",
    )

    # 默认背景与训练器现有海报逐字节一致，运行时无需依赖本地服务。
    shutil.copyfile(
        repo / "frontend/src/assets/qwen-image-21-poster-16-9.png",
        assets / "launcher-wallpaper.png",
    )


if __name__ == "__main__":
    main()
