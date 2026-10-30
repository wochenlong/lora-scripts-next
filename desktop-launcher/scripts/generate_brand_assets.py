"""从仓库现有品牌资源生成桌面启动器图标与默认背景（需 Pillow）。"""

from pathlib import Path
import math
import shutil

from PIL import Image, ImageDraw, ImageFilter


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

    width, height = 1920, 1080
    base = Image.new("RGB", (width, height))
    pixels = base.load()
    for y in range(height):
        for x in range(width):
            halo = math.exp(-(((x - 1430) / 820) ** 2 + ((y - 250) / 740) ** 2))
            rim = math.exp(-(((x - 1000) / 950) ** 2 + ((y - 1050) / 500) ** 2))
            pixels[x, y] = (
                int(23 + 54 * halo + 11 * rim),
                int(38 + 69 * halo + 16 * rim),
                int(55 + 79 * halo + 23 * rim),
            )
    base = base.convert("RGBA")
    lines = Image.new("RGBA", base.size)
    draw = ImageDraw.Draw(lines)
    for inset, alpha in ((0, 24), (74, 18), (170, 12)):
        draw.ellipse(
            (500 + inset, -380 + inset, 2270 - inset, 1350 - inset),
            outline=(169, 200, 221, alpha), width=2,
        )
    draw.polygon(
        [(1350, 20), (1770, 830), (1790, 820), (1370, 10)],
        fill=(185, 210, 228, 8),
    )
    base = Image.alpha_composite(base, lines)
    mascot = Image.open(assets / "guide-mascot.webp").convert("RGBA")
    mascot = mascot.resize((894, 1521), Image.Resampling.LANCZOS)
    alpha = Image.new("L", base.size)
    alpha.paste(mascot.getchannel("A"), (995, -72))
    alpha = alpha.filter(ImageFilter.GaussianBlur(55)).point(lambda value: int(value * .38))
    shadow = Image.new("RGBA", base.size, (12, 24, 39, 0))
    shadow.putalpha(alpha)
    base = Image.alpha_composite(base, shadow)
    base.alpha_composite(mascot, (970, -92))
    shade = Image.new("RGBA", base.size)
    draw = ImageDraw.Draw(shade)
    for y in range(height):
        alpha = int(80 * max(0, (y / height - .58) / .42) ** 1.4)
        draw.line((0, y, width, y), fill=(10, 21, 34, alpha))
    Image.alpha_composite(base, shade).convert("RGB").save(
        assets / "launcher-wallpaper.webp", quality=93, method=6,
    )


if __name__ == "__main__":
    main()
