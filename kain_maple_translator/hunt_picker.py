"""User calibrates the keyboard on a screenshot of the game client (not the desktop)."""
from __future__ import annotations
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox


class _ImageCanvas(QLabel):
    def __init__(self, image, parent=None):
        super().__init__(parent)
        self.source_w,self.source_h=image.width(),image.height()
        # Keep original ratio; downscale only for reasonable selection size.
        self.scale=min(1.0,940/self.source_w,600/self.source_h)
        size=image.size()
        scaled=image.scaled(round(size.width()*self.scale),round(size.height()*self.scale),
                            Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(QPixmap.fromImage(scaled))
        self.setFixedSize(scaled.size())
        self.start=None
        self.end=None

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.start=event.position().toPoint();self.end=self.start;self.update()

    def mouseMoveEvent(self,event):
        if self.start is not None:
            self.end=event.position().toPoint();self.update()

    def mouseReleaseEvent(self,event):
        if self.start is not None:
            self.end=event.position().toPoint();self.update()

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.start is None or self.end is None:return
        painter=QPainter(self)
        painter.setPen(QPen(QColor('#ffba33'),2,Qt.PenStyle.SolidLine))
        painter.drawRect(QRect(self.start,self.end).normalized())

    def relative_rect(self):
        if self.start is None or self.end is None:return None
        r=QRect(self.start,self.end).normalized().intersected(self.rect())
        if r.width()<35 or r.height()<25:return None
        x,y,w,h=(r.x()/self.width(),r.y()/self.height(),r.width()/self.width(),r.height()/self.height())
        if not .95<w*self.source_w/(h*self.source_h)<2.:return None
        return [round(v,6) for v in (x,y,w,h)]


class KeyboardPicker(QDialog):
    def __init__(self,jpeg,parent=None):
        super().__init__(parent)
        self.setWindowTitle('글클메 경험치 측정기 · 단축키 영역 지정')
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True)
        image=QImage.fromData(jpeg,'JPG')
        if image.isNull():raise ValueError('캡처 이미지가 없습니다')
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('메이플 화면의 단축키 패널 4열×3행 전체를 마우스로 드래그하세요.'))
        self.canvas=_ImageCanvas(image,self)
        layout.addWidget(self.canvas)
        self.info=QLabel('설정하면 현재 게임 창 크기에 대한 상대 좌표로 저장합니다.')
        layout.addWidget(self.info)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate(self):
        if self.canvas.relative_rect() is None:
            self.info.setText('4열×3행 단축키 패널 전체를 선택해주세요. (가로가 세로보다 약간 길게)')
            return
        self.accept()

    def selected(self):
        return self.canvas.relative_rect()
