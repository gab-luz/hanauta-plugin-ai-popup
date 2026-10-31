"""Hanauta Nest: passive, embeddable PyQt6 view. Python >=3.10."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QPen, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QWidget, QFrame, QLabel, QPushButton, QTextEdit,
    QHBoxLayout, QVBoxLayout, QScrollArea, QSizePolicy,
)


@dataclass(frozen=True)
class Theme:
    background: str = '#141218'
    surface: str = '#211e27'
    raised: str = '#302b3a'
    hover: str = '#40384e'
    primary: str = '#d0bcff'
    on_primary: str = '#381e72'
    text: str = '#f7f4ff'
    muted: str = '#bdb4ca'
    positive: str = '#a6dfc0'
    error: str = '#ffb4ab'


def icon(name: str, color: str, size: int = 24) -> QIcon:
    """Small original vector fallback set; replace with shared icon provider."""
    pix = QPixmap(size * 2, size * 2)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * 2 / 24, size * 2 / 24)
    pen = QPen(QColor(color), 1.65)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    if name == 'close':
        p.drawLine(6, 6, 18, 18); p.drawLine(18, 6, 6, 18)
    elif name == 'history':
        p.drawEllipse(3, 3, 18, 18); p.drawLine(12, 6, 12, 12); p.drawLine(12, 12, 16, 15)
    elif name in ('settings', 'tune'):
        for y, x in ((6, 15), (12, 8), (18, 14)):
            p.drawLine(3, y, 21, y)
            p.setBrush(QColor(color if name == 'settings' else '#d0bcff'))
            p.drawEllipse(x-2, y-2, 4, 4)
            p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == 'model':
        path = QPainterPath()
        for a, b in [((12, 2), (21, 7)), ((21, 7), (21, 17)), ((21, 17), (12, 22)),
                     ((12, 22), (3, 17)), ((3, 17), (3, 7)), ((3, 7), (12, 2)),
                     ((3, 7), (12, 12)), ((21, 7), (12, 12)), ((12, 12), (12, 22))]:
            path.moveTo(*a); path.lineTo(*b)
        p.drawPath(path)
    elif name == 'mic':
        p.drawRoundedRect(9, 2, 6, 13, 3, 3)
        p.drawArc(6, 7, 12, 12, 180*16, 180*16)
        p.drawLine(12, 19, 12, 22); p.drawLine(8, 22, 16, 22)
    elif name == 'screen':
        p.drawRoundedRect(2, 3, 20, 14, 2, 2)
        p.drawLine(12, 17, 12, 21); p.drawLine(7, 21, 17, 21)
    elif name == 'send':
        path = QPainterPath(); path.moveTo(3, 3); path.lineTo(22, 12)
        path.lineTo(3, 21); path.lineTo(7, 12); path.closeSubpath()
        p.drawPath(path); p.drawLine(7, 12, 17, 12)
    elif name == 'attach':
        path = QPainterPath(); path.moveTo(9, 17); path.lineTo(17, 9)
        path.cubicTo(21, 5, 16, 0, 12, 4); path.lineTo(4, 12)
        path.cubicTo(-2, 18, 6, 26, 12, 20); path.lineTo(21, 11)
        p.drawPath(path)
    elif name == 'chevron':
        p.drawLine(9, 5, 16, 12); p.drawLine(16, 12, 9, 19)
    else:  # Hanauta leaf mark, replace with the ecosystem's official asset.
        path = QPainterPath(); path.moveTo(12, 22)
        path.cubicTo(12, 12, 2, 8, 2, 14); path.cubicTo(2, 20, 12, 20, 12, 22)
        path.moveTo(12, 22); path.cubicTo(12, 12, 22, 8, 22, 14)
        path.cubicTo(22, 20, 12, 20, 12, 22)
        path.moveTo(12, 17); path.cubicTo(4, 10, 12, 2, 12, 2)
        path.cubicTo(20, 10, 12, 17, 12, 17); p.drawPath(path)
    p.end()
    pix.setDevicePixelRatio(2)
    return QIcon(pix)


class Editor(QTextEdit):
    submitted = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            if not event.isAutoRepeat():
                self.submitted.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class NestView(QFrame):
    """No network, persistence, permissions, or QApplication ownership."""
    send_requested = pyqtSignal(str)
    configure_requested = pyqtSignal()
    history_requested = pyqtSignal()
    attachment_requested = pyqtSignal()
    microphone_requested = pyqtSignal()
    screen_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, parent=None, theme: Theme | None = None):
        super().__init__(parent)
        self.theme = theme or Theme()
        self._connected = False
        self._busy = False
        self._messages: dict[str, QLabel] = {}
        self.setObjectName('nest')
        self.setMinimumSize(400, 580)
        self.setAccessibleName(self.tr('Assistente Hanauta AI'))
        self._build()
        self.apply_theme(self.theme)
        self.set_backend_state(False)

    def _panel(self, name='surface'):
        frame = QFrame()
        frame.setObjectName(name)
        return frame

    def _button(self, glyph, title, signal, primary=False):
        button = QPushButton(title if primary else '')
        button.setObjectName('primary' if primary else 'iconButton')
        button.setProperty('glyph', glyph)
        button.setProperty('primary', primary)
        button.setAccessibleName(title)
        button.setToolTip(title)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(40 if primary else 48)
        if not primary:
            button.setFixedWidth(48)
        button.clicked.connect(lambda checked=False: signal.emit())
        return button

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(10, 12, 10, 12); root.setSpacing(10)
        header = self._panel(); h = QHBoxLayout(header); h.setContentsMargins(12, 10, 10, 10)
        self.brand = QLabel(); self.brand.setObjectName('brand'); self.brand.setFixedSize(48, 48)
        self.brand.setAlignment(Qt.AlignmentFlag.AlignCenter); h.addWidget(self.brand)
        labels = QVBoxLayout(); labels.setSpacing(3)
        title = QLabel('Hanauta AI'); title.setObjectName('title')
        self.subtitle = QLabel(); self.subtitle.setObjectName('muted')
        labels.addWidget(title); labels.addWidget(self.subtitle); h.addLayout(labels, 1)
        for glyph, title, signal in [('history', self.tr('Histórico'), self.history_requested),
            ('settings', self.tr('Configurações'), self.configure_requested),
            ('close', self.tr('Fechar'), self.close_requested)]:
            h.addWidget(self._button(glyph, title, signal))
        root.addWidget(header)
        model = self._panel(); m = QVBoxLayout(model); m.setContentsMargins(10, 10, 10, 10); m.setSpacing(8)
        row = QHBoxLayout()
        self.model_icon = QLabel(); self.model_icon.setFixedSize(48, 48); self.model_icon.setObjectName('tile')
        self.model_icon.setAlignment(Qt.AlignmentFlag.AlignCenter); row.addWidget(self.model_icon)
        ml = QVBoxLayout(); ml.setSpacing(3); ml.addWidget(QLabel(self.tr('Modelo de IA')))
        self.model_label = QLabel(); self.model_label.setObjectName('muted'); ml.addWidget(self.model_label)
        row.addLayout(ml, 1)
        self.status = QPushButton(); self.status.setObjectName('status'); self.status.setMinimumHeight(48)
        self.status.clicked.connect(lambda: self.configure_requested.emit()); row.addWidget(self.status)
        m.addLayout(row)
        self.configure = self._button('tune', self.tr('Configurar modelo'), self.configure_requested, True)
        m.addWidget(self.configure); root.addWidget(model)
        chat = self._panel(); cl = QVBoxLayout(chat); cl.setContentsMargins(10, 12, 10, 12)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transcript = QWidget(); self.transcript.setObjectName('transcript')
        self.messages_layout = QVBoxLayout(self.transcript)
        self.messages_layout.setContentsMargins(0, 0, 0, 0); self.messages_layout.setSpacing(14)
        self.messages_layout.addStretch(1); self.scroll.setWidget(self.transcript)
        cl.addWidget(self.scroll); root.addWidget(chat, 1)
        composer = self._panel(); c = QHBoxLayout(composer); c.setContentsMargins(10, 10, 10, 10); c.setSpacing(6)
        input_panel = self._panel('input'); il = QHBoxLayout(input_panel); il.setContentsMargins(2, 2, 6, 2)
        il.addWidget(self._button('attach', self.tr('Anexar arquivo'), self.attachment_requested))
        self.editor = Editor(); self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText(self.tr('Escreva sua mensagem…'))
        self.editor.setAccessibleName(self.tr('Mensagem')); self.editor.setFixedHeight(46)
        self.editor.setTabChangesFocus(True); self.editor.textChanged.connect(self._sync_send)
        self.editor.submitted.connect(self._submit); il.addWidget(self.editor, 1)
        c.addWidget(input_panel, 1)
        c.addWidget(self._button('mic', self.tr('Microfone'), self.microphone_requested))
        c.addWidget(self._button('screen', self.tr('Contexto da tela'), self.screen_requested))
        self.send_button = self._button('send', self.tr('Enviar mensagem'), self.editor.submitted)
        c.addWidget(self.send_button); root.addWidget(composer)

    def apply_theme(self, theme: Theme):
        self.theme = theme
        t = theme
        self.setStyleSheet(f'''
        QFrame#nest {{ background:{t.background}; border-radius:30px; }}
        QFrame#nest QWidget {{ color:{t.text}; font-family:Inter,"Noto Sans",sans-serif; font-size:13px; }}
        QFrame#surface {{ background:{t.surface}; border-radius:24px; }}
        QLabel {{ background:transparent; }}
        QFrame#nest QLabel#title {{ font-size:17px; font-weight:600; }}
        QFrame#nest QLabel#muted {{ color:{t.muted}; font-size:11px; }}
        QLabel#brand {{ background:{t.primary}; border-radius:24px; }}
        QLabel#tile {{ background:{t.raised}; border-radius:18px; }}
        QPushButton {{ border:0; padding:6px; border-radius:17px; background:{t.raised}; }}
        QPushButton:hover {{ background:{t.hover}; }}
        QPushButton:focus {{ border:2px solid {t.primary}; }}
        QFrame#nest QPushButton#primary {{ background:{t.primary}; color:{t.on_primary}; font-weight:600; border-radius:20px; }}
        QFrame#nest QPushButton#primary:hover {{ background:#e1d3ff; }}
        QPushButton:disabled {{ color:{t.muted}; background:{t.raised}; }}
        QFrame#input {{ background:{t.raised}; border-radius:20px; }}
        QTextEdit {{ background:transparent; border:0; padding-top:7px; selection-background-color:{t.primary}; selection-color:{t.on_primary}; }}
        QScrollArea, QScrollArea>QWidget>QWidget, QWidget#transcript {{ background:transparent; border:0; }}
        QScrollBar:vertical {{ background:transparent; width:5px; margin:0; }}
        QScrollBar::handle:vertical {{ background:{t.hover}; border-radius:2px; min-height:24px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
        ''')
        for button in self.findChildren(QPushButton):
            if button.property('glyph'):
                button.setIcon(icon(button.property('glyph'), t.on_primary if button.property('primary') else t.primary))
                button.setIconSize(QSize(22, 22))
        self.brand.setPixmap(icon('leaf', t.on_primary).pixmap(30, 30))
        self.model_icon.setPixmap(icon('model', t.primary).pixmap(26, 26))
        # Message surfaces use per-role colors and are repolished here too.
        for bubble in self.findChildren(QFrame, 'bubble'):
            self._style_bubble(bubble, bool(bubble.property('user')))

    def _style_bubble(self, bubble, user):
        t = self.theme
        bubble.setStyleSheet(f'QFrame#bubble {{background:{t.primary if user else t.raised}; border-radius:20px;}} '
                            f'QFrame#bubble QLabel {{color:{t.on_primary if user else t.text};background:transparent;}}')

    def set_backend_state(self, connected: bool, model_name: str = ''):
        self._connected = bool(connected)
        self.subtitle.setText(model_name if connected and model_name else self.tr('Modelo não configurado') if not connected else self.tr('Modelo conectado'))
        self.model_label.setText(model_name or (self.tr('Conectado') if connected else self.tr('Não configurado')))
        self.status.setText(self.tr('● Conectado  ›') if connected else self.tr('● Desconectado  ›'))
        self.status.setAccessibleName(self.status.text())
        self.configure.setVisible(not connected)
        if hasattr(self, 'setup_card'):
            self.setup_card.setVisible(not connected)
        self._sync_send()

    def set_busy(self, busy: bool):
        self._busy = busy
        self._sync_send()

    def _sync_send(self):
        enabled = self._connected and not self._busy and bool(self.editor.toPlainText().strip())
        self.send_button.setEnabled(enabled)
        self.send_button.setIcon(icon('send', self.theme.primary if enabled else '#69616f'))

    def _submit(self):
        if self.send_button.isEnabled():
            # Controller owns acceptance, persistence and clearing the draft.
            self.send_requested.emit(self.editor.toPlainText().strip())

    def clear_draft(self):
        self.editor.clear()

    def add_message(self, message_id: str, role: str, text: str, timestamp: str = ''):
        if role not in ('user', 'assistant', 'system'):
            raise ValueError('role must be user, assistant or system')
        if message_id in self._messages:
            raise ValueError('duplicate message_id')
        user = role == 'user'
        row = QWidget(); row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0)
        bubble = QFrame(); bubble.setObjectName('bubble'); bubble.setProperty('user', user)
        bubble.setMaximumWidth(310); b = QVBoxLayout(bubble); b.setContentsMargins(14, 12, 14, 12)
        label = QLabel(text); label.setTextFormat(Qt.TextFormat.PlainText); label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        b.addWidget(label); self._messages[message_id] = label
        if timestamp:
            meta = QLabel(timestamp); meta.setAlignment(Qt.AlignmentFlag.AlignRight)
            meta.setStyleSheet('font-size:10px;'); b.addWidget(meta)
        if user: h.addStretch(1)
        h.addWidget(bubble)
        if not user: h.addStretch(1)
        self._style_bubble(bubble, user)
        self.messages_layout.insertWidget(self.messages_layout.count()-1, row)
        self._scroll_bottom()
        return bubble

    def update_message(self, message_id: str, text: str):
        """Replace full plain-text content, suitable for coalesced streaming."""
        bar = self.scroll.verticalScrollBar()
        near_bottom = bar.maximum() - bar.value() < 40
        self._messages[message_id].setText(text)
        if near_bottom: self._scroll_bottom()

    def show_setup_card(self):
        if hasattr(self, 'setup_card'): return
        self.setup_card = self.add_message('hanauta:setup', 'system', self.tr('Configure um modelo\npara começar.'))
        self.setup_card.setMinimumWidth(270)
        self.setup_card.layout().addWidget(self._button('tune', self.tr('Configurar modelo'), self.configure_requested, True))
        self.setup_card.setVisible(not self._connected)

    def clear_messages(self):
        self._messages.clear()
        if hasattr(self, 'setup_card'): del self.setup_card
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def _scroll_bottom(self):
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))


class NestWindow(QWidget):
    """Optional frameless desktop shell; do not use when a shell already exists."""
    def __init__(self, theme=None):
        super().__init__()
        self.setWindowTitle('Hanauta AI')
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.view = NestView(theme=theme); layout.addWidget(self.view)
        self.view.close_requested.connect(self.hide)
        self.resize(440, 650)


def main():
    app = QApplication(sys.argv)
    window = NestWindow()
    window.view.add_message('preview:user', 'user', 'Você está aí?', '01:59')
    window.view.show_setup_card()
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
