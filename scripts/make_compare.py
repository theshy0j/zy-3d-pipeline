"""make_compare.py — 把输入图（Before）和重建渲染图（After）拼成对比图。

用法：
    .venv\\Scripts\\python.exe scripts\\make_compare.py --before samples/building/input.png --after samples/building/after.png --out samples/building/before_after.png
"""
import argparse
import os


def load_font(size):
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    from PIL import ImageFont

    for p in candidates:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label-before", default="输入图")
    ap.add_argument("--label-after", default="重建 + 清理后")
    args = ap.parse_args()

    from PIL import Image, ImageDraw

    before = Image.open(args.before).convert("RGB")
    after = Image.open(args.after).convert("RGB")

    h = 640
    w_b = int(before.width * h / before.height)
    w_a = int(after.width * h / after.height)
    before = before.resize((w_b, h), Image.LANCZOS)
    after = after.resize((w_a, h), Image.LANCZOS)

    pad, label_h, gap = 24, 44, 16
    W = pad * 2 + w_b + gap + w_a
    H = label_h + h + pad * 2
    canvas = Image.new("RGB", (W, H), (251, 250, 247))
    draw = ImageDraw.Draw(canvas)
    font = load_font(24)

    canvas.paste(before, (pad, label_h + pad))
    canvas.paste(after, (pad + w_b + gap, label_h + pad))

    draw.text((pad, pad + 6), args.label_before, fill=(43, 41, 38), font=font)
    draw.text((pad + w_b + gap, pad + 6), args.label_after, fill=(43, 41, 38), font=font)
    draw.line([(pad + w_b + gap // 2, pad), (pad + w_b + gap // 2, H - pad)], fill=(203, 200, 186), width=2)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    canvas.save(args.out)
    print("[make_compare] written:", args.out)


if __name__ == "__main__":
    main()
