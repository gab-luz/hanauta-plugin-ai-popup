"""Hanauta Sidebar Nest settings — Python 3.10+, PyQt6 >=6.6.
Run this file for a preview, or embed SettingsView in the existing shell.
Sidebar starts collapsed on every show; item hover expands temporarily,
leaving collapses after 220 ms; hamburger pins/unpins the expansion.
Connect save_requested(dict), test_requested(dict), process_requested(str),
section_requested(str), close_requested() to existing controllers.
No network, process launch or disk persistence is performed by the view.
Use set_backend_state(), mark_saved(), set_validation() with real results.
Replace placeholder navigation pages through set_section_widget().
Parameters 1–3 have provisional names: map existing runtime keys before use.
"""
from __future__ import annotations
import sys
from PyQt6.QtCore import Qt, QSize, QEvent, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QPen, QPainterPath
from PyQt6.QtWidgets import (QApplication, QWidget, QFrame, QLabel, QPushButton,
    QToolButton, QLineEdit, QComboBox, QCheckBox, QSpinBox, QHBoxLayout, QVBoxLayout,
    QGridLayout, QScrollArea, QStackedWidget, QFileDialog, QSizePolicy)

def make_icon(name: str, color: str) -> QIcon:
    """Original line-icon fallbacks. Inject Hanauta's icon provider instead."""
    pix = QPixmap(48, 48); pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.scale(2, 2)
    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    path = QPainterPath()
    def lines(points):
        path.moveTo(*points[0])
        for point in points[1:]: path.lineTo(*point)
    if name == 'wifi':
        for y, width in ((3, 20), (8, 13), (13, 6)):
            p.drawArc(int(12-width/2), y, width, width, 35*16, 110*16)
        p.drawPoint(12, 19)
    elif name == 'bluetooth':
        lines([(12, 2), (18, 7), (6, 17), (12, 22), (12, 2), (6, 7), (18, 17), (12, 22)])
    elif name == 'dnd':
        p.drawEllipse(3, 3, 18, 18); p.drawLine(7, 12, 17, 12)
    elif name == 'airplane':
        lines([(12, 2), (14, 10), (22, 14), (22, 16), (14, 14), (14, 20), (17, 22),
               (7, 22), (10, 20), (10, 14), (2, 16), (2, 14), (10, 10), (12, 2)])
    elif name == 'night':
        path.moveTo(16, 2); path.cubicTo(1, 0, -1, 21, 14, 22)
        path.cubicTo(18, 22, 21, 19, 22, 17); path.cubicTo(10, 21, 7, 7, 16, 2)
    elif name == 'caffeine':
        p.drawRoundedRect(3, 5, 14, 13, 3, 3); p.drawArc(15, 6, 7, 8, -90*16, 180*16)
        p.drawLine(2, 21, 19, 21)
    elif name == 'brightness':
        p.drawEllipse(7, 7, 10, 10)
        for a,b in [((12,1),(12,4)),((12,20),(12,23)),((1,12),(4,12)),((20,12),(23,12)),
                    ((4,4),(6,6)),((18,18),(20,20)),((4,20),(6,18)),((18,6),(20,4))]: p.drawLine(*a,*b)
    elif name == 'volume':
        lines([(3,9),(7,9),(12,4),(12,20),(7,15),(3,15),(3,9)])
        p.drawArc(11, 6, 9, 12, -70*16, 140*16); p.drawArc(10, 2, 15, 20, -65*16, 130*16)
    elif name == 'power':
        p.drawArc(3, 3, 18, 18, 130*16, 280*16); p.drawLine(12, 1, 12, 12)
    elif name in ('settings', 'sliders'):
        for y,x in ((5,8),(12,16),(19,10)):
            p.drawLine(3,y,21,y); p.drawEllipse(x-2,y-2,4,4)
    elif name in ('previous', 'next', 'left', 'right', 'play'):
        if name in ('previous','left'): lines([(15,5),(8,12),(15,19)])
        else: lines([(9,5),(16,12),(9,19)])
        if name == 'previous': p.drawLine(5,5,5,19)
        if name == 'next': p.drawLine(19,5,19,19)
    elif name == 'pause': p.drawLine(8,5,8,19); p.drawLine(16,5,16,19)
    elif name == 'trash':
        p.drawLine(3,5,21,5); p.drawRoundedRect(6,5,12,16,2,2)
        p.drawLine(9,2,15,2); p.drawLine(10,9,10,17); p.drawLine(14,9,14,17)
    elif name == 'calendar':
        p.drawRoundedRect(3,4,18,18,2,2); p.drawLine(3,9,21,9)
        p.drawLine(8,2,8,6); p.drawLine(16,2,16,6)
        for x,y in ((8,13),(12,13),(16,13),(8,17),(12,17)): p.drawPoint(x,y)
    elif name == 'bell':
        path.moveTo(4,18); path.cubicTo(9,17,3,4,12,4); path.cubicTo(21,4,15,17,20,18)
        path.closeSubpath(); p.drawLine(10,22,14,22); p.drawLine(12,2,12,4)
    elif name == 'device': p.drawRoundedRect(6,1,12,22,2,2); p.drawLine(10,19,14,19)
    elif name == 'clipboard':
        p.drawRoundedRect(5,4,14,18,2,2); p.drawRoundedRect(9,1,6,6,1,1)
    elif name == 'home':
        lines([(2,11),(12,2),(22,11),(19,11),(19,22),(14,22),(14,15),(10,15),(10,22),(5,22),(5,11)])
    elif name == 'folder': lines([(2,6),(10,6),(12,9),(22,9),(21,21),(3,21),(2,6)])
    elif name == 'terminal': lines([(3,6),(9,12),(3,18)]); p.drawLine(12,18,21,18)
    elif name == 'music':
        p.drawLine(9,17,9,4); p.drawLine(9,4,21,2); p.drawLine(21,2,21,15)
        p.drawEllipse(3,16,6,5); p.drawEllipse(15,14,6,5)
    elif name == 'image':
        p.drawRoundedRect(2,3,20,18,2,2); p.drawEllipse(6,6,4,4); lines([(3,19),(10,12),(14,16),(18,11),(22,16)])
    elif name == 'document':
        lines([(5,2),(15,2),(20,7),(20,22),(5,22),(5,2)]); p.drawLine(8,12,17,12); p.drawLine(8,17,17,17)
    elif name == 'game':
        p.drawRoundedRect(2,5,20,14,5,5); p.drawLine(5,12,11,12); p.drawLine(8,9,8,15)
        p.drawPoint(16,10); p.drawPoint(19,14)
    else: p.drawEllipse(4,4,16,16); p.drawLine(5,18,19,6)
    p.drawPath(path); p.end(); pix.setDevicePixelRatio(2)
    return QIcon(pix)


class Sidebar(QFrame):
    section_requested = pyqtSignal(str)
    SECTIONS = [('backends','Backends','device'),('tokens','Tokens','document'),
                ('skills','Skills','settings'),('benchmarking','Benchmarking','sliders'),
                ('storage','Storage','folder')]

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('sidebar'); self.pinned=False; self._width=64; self._keyboard_focus=False
        self.setFixedWidth(64)
        self.animation=QPropertyAnimation(self,b'railWidth',self)
        self.animation.setDuration(180); self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.leave_timer=QTimer(self); self.leave_timer.setSingleShot(True)
        self.leave_timer.setInterval(220); self.leave_timer.timeout.connect(self._maybe_collapse)
        layout=QVBoxLayout(self);layout.setContentsMargins(8,12,8,12);layout.setSpacing(7)
        self.hamburger=QToolButton();self.hamburger.setText('☰');self.hamburger.setObjectName('hamburger')
        self.hamburger.setFixedSize(44,44);self.hamburger.setCheckable(True)
        self.hamburger.setAccessibleName('Expand sidebar');self.hamburger.setToolTip('Expand / pin sidebar')
        self.hamburger.clicked.connect(self._toggle_pin); layout.addWidget(self.hamburger)
        self.brand=QLabel('Hanauta AI');self.brand.setObjectName('brand');layout.addWidget(self.brand)
        self.buttons={}
        for key,title,glyph in self.SECTIONS:
            b=QToolButton();b.setText(title);b.setToolTip(title);b.setAccessibleName(title)
            b.setProperty('glyph',glyph);b.setProperty('title',title);b.setObjectName('nav')
            b.setCheckable(True);b.setChecked(key=='backends');b.setMinimumHeight(46)
            b.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            b.setIconSize(QSize(23,23));b.installEventFilter(self)
            b.clicked.connect(lambda checked=False,k=key:self.select(k))
            self.buttons[key]=b;layout.addWidget(b)
        layout.addStretch();self._set_width(64);self.recolor()

    def recolor(self):
        for b in self.buttons.values():
            b.setIcon(make_icon(b.property('glyph'),'#381e72' if b.isChecked() else '#d0bcff'))

    def select(self,key):
        for name,b in self.buttons.items():b.setChecked(name==key)
        self.recolor();self.section_requested.emit(key)

    def _set_width(self,value):
        self._width=int(value);self.setFixedWidth(self._width)
        expanded=self._width>=145
        self.brand.setVisible(expanded)
        for b in self.buttons.values():
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if expanded else Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.updateGeometry()

    railWidth=pyqtProperty(int,fget=lambda self:self._width,fset=_set_width)

    def expand(self):
        self.leave_timer.stop();self._animate(220)

    def _animate(self,width):
        self.animation.stop();self.animation.setStartValue(self._width);self.animation.setEndValue(width);self.animation.start()

    def reset(self):
        self.leave_timer.stop();self.animation.stop();self.pinned=False
        self.hamburger.setChecked(False);self.hamburger.setAccessibleName('Expand sidebar')
        self._set_width(64)

    def _toggle_pin(self,checked):
        self.pinned=checked;self.leave_timer.stop()
        self.hamburger.setAccessibleName('Collapse sidebar' if checked else 'Expand sidebar')
        self._animate(220 if checked else 64)

    def _maybe_collapse(self):
        focus=QApplication.focusWidget()
        keyboard_inside=self._keyboard_focus and focus is not None and focus in self.buttons.values() and focus.hasFocus()
        if not self.pinned and not self.underMouse() and not keyboard_inside:self._animate(64)

    def eventFilter(self,watched,event):
        if watched in self.buttons.values():
            if event.type()==QEvent.Type.Enter:
                self._keyboard_focus=False;self.expand()
            elif event.type()==QEvent.Type.FocusIn:
                self._keyboard_focus=event.reason() in (Qt.FocusReason.TabFocusReason,Qt.FocusReason.BacktabFocusReason)
                if self._keyboard_focus:self.expand()
            elif event.type() in (QEvent.Type.Leave,QEvent.Type.FocusOut):
                if event.type()==QEvent.Type.FocusOut:self._keyboard_focus=False
                self.leave_timer.start()
        return super().eventFilter(watched,event)

    def enterEvent(self,event):
        self.leave_timer.stop();super().enterEvent(event)

    def leaveEvent(self,event):
        self.leave_timer.start();super().leaveEvent(event)


class SettingsView(QFrame):
    save_requested=pyqtSignal(dict)
    test_requested=pyqtSignal(dict)
    process_requested=pyqtSignal(str)
    section_requested=pyqtSignal(str)
    backend_selected=pyqtSignal(str)
    close_requested=pyqtSignal()
    activation_requested=pyqtSignal(bool)

    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName('settingsRoot')
        self.setMinimumSize(760,580);self._loading=True;self.fields={};self._page_indexes={}
        root=QHBoxLayout(self);root.setContentsMargins(10,10,10,10);root.setSpacing(12)
        self.sidebar=Sidebar();root.addWidget(self.sidebar)
        main=QVBoxLayout();main.setSpacing(10);root.addLayout(main,1)
        header=QHBoxLayout();self.title=QLabel('Backend settings');self.title.setObjectName('heading')
        header.addWidget(self.title,1);close=QPushButton('×');close.setObjectName('close')
        close.setAccessibleName('Close settings');close.setFixedSize(36,36)
        close.clicked.connect(self.close_requested.emit);header.addWidget(close);main.addLayout(header)
        self.description=QLabel('Configure each backend and make it available in the popup.')
        self.description.setObjectName('muted');self.description.setWordWrap(True);main.addWidget(self.description)
        self.stack=QStackedWidget();main.addWidget(self.stack,1)
        backends=QWidget();backend_layout=QVBoxLayout(backends);backend_layout.setContentsMargins(0,0,0,0);backend_layout.setSpacing(10)
        summary,sl=self.card();summary_row=QHBoxLayout()
        self.backend=QComboBox();self.backend.addItem('LFM3-Omni 2B','lfm3-omni-2b');self.backend.setMinimumWidth(160)
        self.backend.currentIndexChanged.connect(lambda _:self.backend_selected.emit(str(self.backend.currentData())))
        summary_row.addWidget(self.backend,1);self.process_status=QLabel('●  Stopped');summary_row.addWidget(self.process_status)
        self.active=QCheckBox('Use in popup');self.active.setEnabled(False)
        self.active.setToolTip('Availability is controlled by the existing backend service.')
        self.active.clicked.connect(self.activation_requested.emit);summary_row.addWidget(self.active);sl.addLayout(summary_row)
        backend_layout.addWidget(summary)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        backend_layout.addWidget(scroll,1);body=QWidget();scroll.setWidget(body)
        body_layout=QVBoxLayout(body);body_layout.setContentsMargins(0,0,5,0);body_layout.setSpacing(10)
        connection,cl=self.card('Connection');grid=QGridLayout();grid.setHorizontalSpacing(12);grid.setVerticalSpacing(9)
        grid.addWidget(self.field('backend_name','Backend name','LFM3-Omni 2B'),0,0)
        grid.addWidget(self.field('model_id','Model ID','lfm3-omni-2b'),0,1)
        grid.addWidget(self.field('endpoint','Endpoint','127.0.0.1:8082'),1,0)
        grid.addWidget(self.path_field('executable','Server executable','~/.local/share/ai-popup/runtimes/lfm3-llama-cpp/current/llama-server'),1,1)
        device=QWidget();dl=QVBoxLayout(device);dl.setContentsMargins(0,0,0,0);dl.addWidget(QLabel('Compute device'))
        self.compute=QComboBox();self.compute.addItems(['CPU','GPU']);self.compute.currentTextChanged.connect(self.mark_dirty);dl.addWidget(self.compute)
        grid.addWidget(device,2,0)
        controls=QWidget();controls_layout=QHBoxLayout(controls);controls_layout.setContentsMargins(0,18,0,0)
        for name in ('Start','Restart','Stop'):
            b=QPushButton(name);b.setMinimumHeight(38)
            b.clicked.connect(lambda checked=False,key=name.lower():self.process_requested.emit(key));controls_layout.addWidget(b)
        grid.addWidget(controls,2,1);cl.addLayout(grid);body_layout.addWidget(connection)
        model,ml=self.card('Model')
        ml.addWidget(self.path_field('model_path','GGUF model path','~/.cache/hanauta-ai-popup/llm-models/LFM3-Omni-2B-Abliter8-Q6_K.gguf'))
        self.model_info=QLabel('LFM3-Omni-2B-Abliter8-Q6_K.gguf · 1.33 GB · Q6_K');self.model_info.setObjectName('muted');self.model_info.setWordWrap(True)
        ml.addWidget(self.model_info)
        self.token_saver=QCheckBox('Token saver — compress voice prompts before the LLM');self.token_saver.setChecked(True)
        self.token_saver.toggled.connect(self.mark_dirty);ml.addWidget(self.token_saver);body_layout.addWidget(model)
        tuning,tl=self.card('llama.cpp Runtime tuning')
        switches=QHBoxLayout();self.flash=QCheckBox('Flash Attention');self.mtp=QCheckBox('MTP / speculative decoding')
        self.flash.toggled.connect(self.mark_dirty);self.mtp.toggled.connect(self._mtp_changed)
        switches.addWidget(self.flash);switches.addWidget(self.mtp);tl.addLayout(switches)
        self.draft_widget=self.path_field('draft_path','Draft model GGUF','');self.draft_widget.setEnabled(False);tl.addWidget(self.draft_widget)
        numbers=QHBoxLayout()
        for index,value in enumerate((16,1024,99),1):
            container=QWidget();layout=QVBoxLayout(container);layout.setContentsMargins(0,0,0,0)
            layout.addWidget(QLabel(f'Parameter {index}'));spin=QSpinBox();spin.setRange(-1,2147483647);spin.setValue(value)
            spin.setAccessibleName(f'Runtime parameter {index}');spin.valueChanged.connect(self.mark_dirty)
            self.fields[f'parameter_{index}']=spin;layout.addWidget(spin);numbers.addWidget(container)
        tl.addLayout(numbers)
        note=QLabel('Parameter names must be mapped to the existing runtime settings.');note.setObjectName('muted');note.setWordWrap(True);tl.addWidget(note)
        self.runtime_extra=QVBoxLayout();tl.addLayout(self.runtime_extra);body_layout.addWidget(tuning);body_layout.addStretch()
        self._page_indexes['backends']=self.stack.addWidget(backends)
        for key,title,_ in Sidebar.SECTIONS[1:]:
            placeholder=QWidget();pl=QVBoxLayout(placeholder);label=QLabel(f'{title}\nConnect the existing Hanauta settings page here.')
            label.setAlignment(Qt.AlignmentFlag.AlignCenter);pl.addWidget(label)
            self._page_indexes[key]=self.stack.addWidget(placeholder)
        footer,fl=self.card();footer_row=QHBoxLayout();self.validation=QLabel('○  Not validated');self.saved=QLabel('Changes saved');self.saved.setObjectName('muted')
        footer_row.addWidget(self.validation);footer_row.addWidget(self.saved);footer_row.addStretch()
        test=QPushButton('Test connection');test.clicked.connect(lambda:self.test_requested.emit(self.values()))
        close=QPushButton('Close');close.clicked.connect(self.close_requested.emit)
        save=QPushButton('Save changes');save.setObjectName('primary');save.clicked.connect(lambda:self.save_requested.emit(self.values()))
        for b in (test,close,save):b.setMinimumHeight(40);footer_row.addWidget(b)
        fl.addLayout(footer_row);main.addWidget(footer)
        self.sidebar.section_requested.connect(self._navigate)
        self.setStyleSheet(STYLE);self._loading=False

    def card(self,title=None):
        frame=QFrame();frame.setObjectName('card');layout=QVBoxLayout(frame)
        layout.setContentsMargins(14,12,14,12);layout.setSpacing(10)
        if title:
            label=QLabel(title);label.setObjectName('sectionTitle');layout.addWidget(label)
        return frame,layout

    def field(self,key,label,value):
        container=QWidget();layout=QVBoxLayout(container);layout.setContentsMargins(0,0,0,0);layout.setSpacing(5)
        layout.addWidget(QLabel(label));edit=QLineEdit(value);edit.setAccessibleName(label)
        edit.setToolTip(value);edit.textChanged.connect(lambda text,e=edit:(e.setToolTip(text),self.mark_dirty()))
        self.fields[key]=edit;layout.addWidget(edit);return container

    def path_field(self,key,label,value):
        container=self.field(key,label,value);edit=self.fields[key]
        container.layout().removeWidget(edit);row=QHBoxLayout();row.addWidget(edit,1)
        browse=QPushButton();browse.setIcon(make_icon('folder','#d0bcff'));browse.setFixedSize(38,36)
        browse.setToolTip('Browse '+label);browse.setAccessibleName('Browse '+label)
        browse.clicked.connect(lambda:self._browse(key,label));row.addWidget(browse);container.layout().addLayout(row)
        return container

    def _browse(self,key,label):
        from pathlib import Path
        current=str(Path(self.fields[key].text()).expanduser())
        path,_=QFileDialog.getOpenFileName(self,label,current,'GGUF models (*.gguf);;All files (*)' if key!='executable' else 'All files (*)')
        if path:self.fields[key].setText(path)

    def _mtp_changed(self,value):
        self.draft_widget.setEnabled(value);self.mark_dirty()

    def mark_dirty(self,*_):
        if not self._loading:self.saved.setText('Unsaved changes')

    def mark_saved(self):
        self.saved.setText('Changes saved')

    def set_validation(self,text):
        self.validation.setText(text)

    def set_backend_state(self,status,can_activate=False,active=False):
        self.process_status.setText('●  '+status);self.active.setEnabled(can_activate);self.active.setChecked(active)

    def values(self):
        data={key:(w.value() if isinstance(w,QSpinBox) else w.text()) for key,w in self.fields.items()}
        data.update(backend_id=self.backend.currentData(),compute=self.compute.currentText(),
                    active=self.active.isChecked(),token_saver=self.token_saver.isChecked(),
                    flash_attention=self.flash.isChecked(),speculative=self.mtp.isChecked())
        return data

    def load_values(self,data):
        self._loading=True
        try:
            for key,w in self.fields.items():
                if key in data:
                    if isinstance(w,QSpinBox):w.setValue(int(data[key]))
                    else:w.setText(str(data[key]))
            self.compute.setCurrentText(data.get('compute','CPU'))
            self.token_saver.setChecked(bool(data.get('token_saver',True)))
            self.flash.setChecked(bool(data.get('flash_attention',False)))
            self.mtp.setChecked(bool(data.get('speculative',False)))
            self.active.setChecked(bool(data.get('active',False)))
            if 'backend_id' in data:
                index=self.backend.findData(data['backend_id'])
                if index>=0:
                    blocked=self.backend.blockSignals(True);self.backend.setCurrentIndex(index);self.backend.blockSignals(blocked)
        finally:self._loading=False
        self.mark_saved()

    def set_section_widget(self,key,widget):
        """Replace Tokens/Skills/Benchmarking/Storage with existing production pages."""
        if key=='backends' or key not in self._page_indexes:raise ValueError('Unknown or reserved section')
        index=self._page_indexes[key];old=self.stack.widget(index);selected=self.stack.currentWidget() is old
        self.stack.removeWidget(old);old.deleteLater();self.stack.insertWidget(index,widget)
        if selected:self.stack.setCurrentIndex(index)

    def _navigate(self,key):
        self.stack.setCurrentIndex(self._page_indexes[key])
        self.title.setText('Backend settings' if key=='backends' else dict((k,t) for k,t,_ in Sidebar.SECTIONS)[key])
        self.section_requested.emit(key)

    def showEvent(self,event):
        self.sidebar.reset();super().showEvent(event)


STYLE='''
QFrame#settingsRoot {background:#141218;border-radius:24px;}
QFrame#settingsRoot QWidget {color:#f7f4ff;font-family:"Inter","Noto Sans","DejaVu Sans";font-size:12px;}
QFrame#sidebar {background:#1b1821;border-radius:18px;}
QFrame#card {background:#211e27;border-radius:18px;}
QLabel {background:transparent;}
QFrame#settingsRoot QLabel#heading {font-size:23px;font-weight:700;}
QFrame#settingsRoot QLabel#sectionTitle {font-size:15px;font-weight:600;}
QFrame#settingsRoot QLabel#brand {font-size:17px;font-weight:700;padding:8px;}
QFrame#settingsRoot QLabel#muted {color:#bdb4ca;font-size:11px;}
QPushButton,QToolButton {background:#302b3a;border:0;border-radius:12px;padding:8px;}
QPushButton:hover,QToolButton:hover {background:#40384e;}
QPushButton:focus,QToolButton:focus,QLineEdit:focus,QComboBox:focus,QSpinBox:focus {border:1px solid #d0bcff;}
QFrame#settingsRoot QPushButton#primary,QFrame#settingsRoot QToolButton#nav:checked {background:#d0bcff;color:#381e72;font-weight:600;}
QToolButton#nav {text-align:left;padding:8px;}
QFrame#settingsRoot QToolButton#hamburger {font-size:23px;}
QFrame#settingsRoot QPushButton#close {font-size:23px;}
QLineEdit,QComboBox,QSpinBox {background:#302b3a;border:1px solid #40384e;border-radius:10px;padding:8px;min-height:18px;selection-background-color:#d0bcff;selection-color:#381e72;}
QComboBox QAbstractItemView {background:#302b3a;color:#f7f4ff;selection-background-color:#d0bcff;selection-color:#381e72;}
QCheckBox {spacing:7px;}
QCheckBox::indicator {width:20px;height:20px;border:1px solid #5b5268;border-radius:6px;background:#302b3a;}
QCheckBox::indicator:checked {background:#d0bcff;border-color:#d0bcff;}
QCheckBox::indicator:disabled {background:#29262f;border-color:#40384e;}
QFrame#settingsRoot QWidget:disabled {color:#81798c;}
QScrollArea,QScrollArea>QWidget>QWidget,QStackedWidget {background:transparent;border:0;}
QScrollBar:vertical {width:6px;background:transparent;}
QScrollBar::handle:vertical {background:#6d5a88;border-radius:3px;min-height:28px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
'''


class SettingsWindow(QWidget):
    def __init__(self):
        super().__init__();self.setWindowTitle('Hanauta AI · Settings');self.resize(1120,870)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.view=SettingsView();layout.addWidget(self.view);self.view.close_requested.connect(self.close)


def main():
    app=QApplication(sys.argv);window=SettingsWindow();window.show();return app.exec()


if __name__=='__main__':sys.exit(main())
