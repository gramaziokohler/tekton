import sys
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt

app = QGuiApplication(sys.argv)
svg_path = 'packages/tekton_app/src/tekton_app/assets/tekton.svg'
png_path = 'packages/tekton_app/src/tekton_app/assets/tekton.png'
ico_path = 'packages/tekton_app/src/tekton_app/assets/tekton.ico'

# Render to 256x256 PNG
image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
renderer = QSvgRenderer(svg_path)
renderer.render(painter)
painter.end()

image.save(png_path)

# Converting to ICO
try:
    from PIL import Image
    img = Image.open(png_path)
    img.save(ico_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("ICO created with Pillow")
except ImportError:
    print("Pillow not installed, using generic Qt save")
    image.save(ico_path, 'ICO')
