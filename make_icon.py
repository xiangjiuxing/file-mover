# -*- coding: utf-8 -*-
"""
生成高清多尺寸图标（作者：微尘）· 多巴胺暖色版。

- icon.ico      : 16/20/24/32/40/48/64/96/128/256 十档尺寸，
                  全部由 1024x1024 主图经 LANCZOS 缩小，边缘无硬锯齿。
- icon_ui.png   : 56x56，用于软件渐变标题栏（Tk PhotoImage 直接显示）。
- 图标预览.png   : 256x256，方便直接查看成品。

依赖 Pillow，但只在生成图标时使用；打包后的 EXE 运行时不需要 Pillow。
"""
import os
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024

# 多巴胺暖色：珊瑚橙 → 中黄 → 玫红，与界面标题栏完全同色
FLAME = (255, 112, 67)
SUN = (255, 190, 45)
BERRY = (238, 71, 138)

ICO_PATH = os.path.join(HERE, "icon.ico")
UI_PATH = os.path.join(HERE, "icon_ui.png")
PREVIEW_PATH = os.path.join(HERE, "图标预览.png")

SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
         (48, 48), (64, 64), (96, 96), (128, 128), (256, 256)]


def p(v):
    return int(round(v * S))


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t + 0.5) for i in range(3))


def gradient():
    """对角渐变：珊瑚橙 → 中黄 → 玫红。在小图上算好再平滑放大。"""
    G = 256
    small = Image.new("RGB", (G, G))
    px = small.load()
    for y in range(G):
        for x in range(G):
            t = (x / (G - 1)) * 0.74 + (y / (G - 1)) * 0.26
            if t < 0.50:
                c = lerp(FLAME, SUN, t / 0.50)
            else:
                c = lerp(SUN, BERRY, (t - 0.50) / 0.50)
            lift = int(12 * (1 - y / (G - 1)))       # 顶部略提亮，做出光感
            px[x, y] = tuple(min(255, v + lift) for v in c)
    return small.resize((S, S), Image.Resampling.BICUBIC).convert("RGBA")


def make_mask():
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        (p(0.055), p(0.055), p(0.945), p(0.945)),
        radius=p(0.225), fill=255)
    return m.filter(ImageFilter.GaussianBlur(1.5))    # 边缘微柔，缩小后更顺滑


def highlight():
    """左上柔和光斑，给底色一点玻璃质感。"""
    h = Image.new("L", (S, S), 0)
    ImageDraw.Draw(h).ellipse(
        (p(-0.35), p(-0.55), p(0.85), p(0.42)), fill=80)
    h = h.filter(ImageFilter.GaussianBlur(p(0.10)))
    out = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    out.putalpha(h)
    return out


def motif():
    """白色符号：文件卡片 + 右向粗箭头。造型极简，16px 下也能辨认。"""
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle((p(0.185), p(0.295), p(0.435), p(0.705)),
                        radius=p(0.055), fill=255)
    d.rounded_rectangle((p(0.245), p(0.415), p(0.375), p(0.445)),
                        radius=p(0.015), fill=0)
    d.rounded_rectangle((p(0.245), p(0.545), p(0.375), p(0.575)),
                        radius=p(0.015), fill=0)
    d.rounded_rectangle((p(0.470), p(0.452), p(0.690), p(0.548)),
                        radius=p(0.048), fill=255)
    d.polygon([(p(0.625), p(0.315)), (p(0.845), p(0.500)),
               (p(0.625), p(0.685))], fill=255)
    d.ellipse((p(0.600), p(0.470), p(0.660), p(0.530)), fill=255)
    return m.filter(ImageFilter.GaussianBlur(0.8))


def shifted(img, dx, dy):
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    layer.paste(img, (dx, dy))
    return layer


def build():
    mask = make_mask()
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # ① 柔和投影（暖棕，配合多巴胺暖色）
    sh = mask.filter(ImageFilter.GaussianBlur(p(0.030)))
    sh = sh.point(lambda a: int(a * 0.28))
    shadow = Image.new("RGBA", (S, S), (104, 58, 32, 0))
    shadow.putalpha(sh)
    canvas = Image.alpha_composite(canvas, shifted(shadow, 0, p(0.022)))

    # ② 渐变底 + 高光，裁剪成圆角方形
    g = Image.alpha_composite(gradient(), highlight())
    g.putalpha(mask)
    canvas = Image.alpha_composite(canvas, g)

    # ③ 一圈极淡的内描边，让轮廓更干净
    edge = Image.new("L", (S, S), 0)
    ImageDraw.Draw(edge).rounded_rectangle(
        (p(0.066), p(0.066), p(0.934), p(0.934)),
        radius=p(0.212), outline=255, width=p(0.010))
    edge = edge.filter(ImageFilter.GaussianBlur(2)).point(lambda a: int(a * 0.22))
    rim = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    rim.putalpha(edge)
    canvas = Image.alpha_composite(canvas, rim)

    # ④ 符号的柔和阴影（暖深棕）
    msh = motif().filter(ImageFilter.GaussianBlur(p(0.016)))
    msh = msh.point(lambda a: int(a * 0.42))
    dark = Image.new("RGBA", (S, S), (122, 58, 26, 0))
    dark.putalpha(msh)
    canvas = Image.alpha_composite(canvas, shifted(dark, 0, p(0.014)))

    # ⑤ 暖白符号本体
    white = Image.new("RGBA", (S, S), (255, 252, 246, 0))
    white.putalpha(motif())
    canvas = Image.alpha_composite(canvas, white)
    return canvas


def main():
    img = build()
    img.save(ICO_PATH, format="ICO", sizes=SIZES)
    img.resize((56, 56), Image.Resampling.LANCZOS).save(UI_PATH)
    img.resize((256, 256), Image.Resampling.LANCZOS).save(PREVIEW_PATH)

    check = Image.open(ICO_PATH)
    print("ICON_OK:", ICO_PATH, os.path.getsize(ICO_PATH), "bytes")
    print("ICO_SIZES:", sorted({s[0] for s in check.info.get("sizes", SIZES)}) or SIZES)
    print("UI_PNG:", UI_PATH, Image.open(UI_PATH).size)
    print("PREVIEW:", PREVIEW_PATH, Image.open(PREVIEW_PATH).size)


if __name__ == "__main__":
    main()
