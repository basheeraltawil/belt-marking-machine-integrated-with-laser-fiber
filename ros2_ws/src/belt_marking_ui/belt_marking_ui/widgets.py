"""Touch widgets: big buttons, numeric fields with an on-screen keypad, tiles, light tower."""

from PyQt5.QtCore import pyqtSignal, QSize, Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QSizePolicy, QVBoxLayout, QWidget)

STYLE = """
QWidget { background: #1e2327; color: #e8eaed; font-size: 17px; }
QPushButton { background: #37404a; border: 1px solid #4b5561; border-radius: 8px;
              padding: 6px 10px; min-height: 48px; }
QPushButton:pressed { background: #56616d; }
QPushButton:disabled { color: #6c747c; background: #2a3036; }
QPushButton:checked { background: #1f6feb; border-color: #58a6ff; }
QPushButton[role="start"] { background: #1a7f37; font-weight: bold; font-size: 20px; }
QPushButton[role="hold"] { background: #9a6700; font-weight: bold; font-size: 20px; }
QPushButton[role="stop"] { background: #cf222e; font-weight: bold; font-size: 20px; }
QPushButton[role="nav"] { text-align: left; min-height: 34px; padding: 3px 8px; font-size: 16px; }
QPushButton[role="nav"]:checked { background: #1f6feb; }
QLabel[role="title"] { font-size: 20px; font-weight: bold; }
QLabel[role="value"] { font-size: 26px; font-weight: bold; }
QLabel[role="small"] { font-size: 13px; color: #9aa4ad; }
QFrame[role="tile"] { background: #262c31; border-radius: 8px; }
QListWidget, QTableWidget { background: #262c31; font-size: 16px; gridline-color: #3a434c; }
QHeaderView::section { background: #37404a; padding: 4px; }
QProgressBar { border: 1px solid #4b5561; border-radius: 6px; text-align: center;
               min-height: 28px; }
QProgressBar::chunk { background: #1a7f37; border-radius: 6px; }
QLineEdit { background: #262c31; border: 1px solid #4b5561; border-radius: 6px;
            min-height: 40px; padding: 0 8px; }
"""


def big_button(text: str, role: str = '', checkable: bool = False) -> QPushButton:
    b = QPushButton(text)
    if role:
        b.setProperty('role', role)
    b.setCheckable(checkable)
    b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    b.setMinimumSize(QSize(64, 52))
    return b


class Keypad(QDialog):
    """Numeric keypad dialog (works with gloves: 64 px keys)."""

    def __init__(self, title: str, value: str = '', minimum=None, maximum=None,
                 secret: bool = False, decimals: int = 2, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.minimum, self.maximum, self.decimals = minimum, maximum, decimals
        lay = QVBoxLayout(self)
        head = QLabel(title)
        head.setProperty('role', 'title')
        lay.addWidget(head)
        rng = ''
        if minimum is not None and maximum is not None:
            rng = f'{minimum:g} … {maximum:g}'
        self.hint = QLabel(rng)
        self.hint.setProperty('role', 'small')
        lay.addWidget(self.hint)
        self.edit = QLineEdit(value)
        self.edit.setAlignment(Qt.AlignRight)
        if secret:
            self.edit.setEchoMode(QLineEdit.Password)
        lay.addWidget(self.edit)
        grid = QGridLayout()
        keys = ['7', '8', '9', '4', '5', '6', '1', '2', '3', '.', '0', '⌫']
        for i, k in enumerate(keys):
            b = QPushButton(k)
            b.setMinimumSize(QSize(72, 56))
            b.clicked.connect(lambda _=False, key=k: self._key(key))
            grid.addWidget(b, i // 3, i % 3)
        lay.addLayout(grid)
        row = QHBoxLayout()
        cancel, ok = QPushButton('✕'), QPushButton('✓')
        ok.setProperty('role', 'start')
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def _key(self, k):
        t = self.edit.text()
        if k == '⌫':
            self.edit.setText(t[:-1])
        elif k == '.' and ('.' in t or self.decimals == 0):
            return
        else:
            self.edit.setText(t + k)

    def value(self) -> str:
        return self.edit.text()

    def _accept(self):
        if self.minimum is None:
            self.accept()
            return
        try:
            v = float(self.edit.text())
        except ValueError:
            self.hint.setText('invalid number')
            return
        if not (self.minimum <= v <= self.maximum):
            self.hint.setText(f'must be {self.minimum:g} … {self.maximum:g}')
            return
        self.accept()


class NumField(QPushButton):
    """Button showing a number; tap to edit with the keypad. Range-checked."""

    changed = pyqtSignal(float)

    def __init__(self, title: str, value: float, minimum: float, maximum: float,
                 decimals: int = 1, parent=None):
        super().__init__(parent)
        self.title, self.minimum, self.maximum, self.decimals = title, minimum, maximum, decimals
        self._value = value
        self.clicked.connect(self._edit)
        self._render()

    def _render(self):
        self.setText(f'{self._value:.{self.decimals}f}')

    def value(self) -> float:
        return self._value

    def set_value(self, v: float):
        self._value = float(v)
        self._render()

    def set_range(self, minimum, maximum):
        self.minimum, self.maximum = minimum, maximum

    def _edit(self):
        dlg = Keypad(self.title, self.text(), self.minimum, self.maximum,
                     decimals=self.decimals, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.set_value(float(dlg.value()))
            self.changed.emit(self._value)


class Tile(QFrame):
    """Label + large value."""

    def __init__(self, caption: str, value: str = '–'):
        super().__init__()
        self.setProperty('role', 'tile')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        self.caption = QLabel(caption)
        self.caption.setProperty('role', 'small')
        self.value = QLabel(value)
        self.value.setProperty('role', 'value')
        lay.addWidget(self.caption)
        lay.addWidget(self.value)

    def set_text(self, text):
        self.value.setText(str(text))


class LightTower(QWidget):

    def __init__(self):
        super().__init__()
        self.lights = (False, False, False)
        self.setMinimumSize(QSize(34, 96))
        self.setMaximumWidth(40)

    def set_lights(self, red, yellow, green):
        self.lights = (red, yellow, green)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cols = [QColor(220, 30, 30), QColor(230, 190, 0), QColor(20, 170, 60)]
        h = self.height() / 3
        for i, (on, c) in enumerate(zip(self.lights, cols)):
            p.setBrush(c if on else c.darker(400))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(3, int(i * h) + 3, self.width() - 6, int(h) - 6, 5, 5)
