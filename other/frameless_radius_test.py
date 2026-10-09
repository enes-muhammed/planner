import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel

RADIUS = 8

class RoundedWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
        )

        # Pencerenin köşelerinin transparan olmasını sağlar.
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )

        self.resize(500, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        label = QLabel("Frameless Rounded Window")
        label.setStyleSheet("color: white; font-size: 20px;")
        layout.addWidget(label)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing, True
        )

        rect = self.rect().adjusted(1, 1, -1, -1)

        path = QPainterPath()
        path.addRoundedRect(rect, RADIUS, RADIUS)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawPath(path)


app = QApplication(sys.argv)

window = RoundedWindow()
window.show()

sys.exit(app.exec())