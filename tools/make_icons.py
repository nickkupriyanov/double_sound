"""Генерирует icon.ico и icon.png из SVG (запускать в dev-окружении)."""

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "app" / "resources" / "icon.svg"
OUT = ROOT / "app" / "resources"


def main() -> None:
    app = QGuiApplication([])
    renderer = QSvgRenderer(str(SVG))
    image = QImage(512, 512, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    png = OUT / "icon.png"
    image.save(str(png))

    source = Image.open(png).convert("RGBA")
    source.save(
        OUT / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("Готово:", png, OUT / "icon.ico")


if __name__ == "__main__":
    main()
