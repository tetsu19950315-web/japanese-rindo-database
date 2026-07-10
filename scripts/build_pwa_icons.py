from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "icons"


def build_icon(size: int) -> Image.Image:
    scale = 4
    canvas_size = size * scale
    image = Image.new("RGB", (canvas_size, canvas_size), "#314c24")
    draw = ImageDraw.Draw(image)

    # Maskableアイコンの安全領域内に、山並みと林道を単純化して描く。
    draw.ellipse(
        (canvas_size * 0.08, canvas_size * 0.08, canvas_size * 0.92, canvas_size * 0.92),
        fill="#efe7d7",
    )
    draw.polygon(
        [
            (canvas_size * 0.18, canvas_size * 0.64),
            (canvas_size * 0.42, canvas_size * 0.31),
            (canvas_size * 0.55, canvas_size * 0.49),
            (canvas_size * 0.67, canvas_size * 0.35),
            (canvas_size * 0.84, canvas_size * 0.64),
        ],
        fill="#506a3f",
    )
    draw.polygon(
        [
            (canvas_size * 0.18, canvas_size * 0.64),
            (canvas_size * 0.42, canvas_size * 0.31),
            (canvas_size * 0.53, canvas_size * 0.64),
        ],
        fill="#6f845d",
    )
    road_points = [
        (canvas_size * 0.30, canvas_size * 0.77),
        (canvas_size * 0.53, canvas_size * 0.69),
        (canvas_size * 0.43, canvas_size * 0.58),
        (canvas_size * 0.63, canvas_size * 0.51),
    ]
    draw.line(road_points, fill="#f7f5ef", width=int(canvas_size * 0.07), joint="curve")
    draw.line(road_points, fill="#b57938", width=int(canvas_size * 0.035), joint="curve")
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        build_icon(size).save(OUTPUT / f"rindo-{size}.png", optimize=True)


if __name__ == "__main__":
    main()
