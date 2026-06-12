"""
rubi_gui.py — 振假名 PNG 生成器 GUI (PyQt6)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Optional

# ══════════════════════════════════════════════════════════════
#  ★ 默认参数配置（所有可调数值集中于此，方便快速修改）★
# ══════════════════════════════════════════════════════════════

TEXTS = "どんよりとした青空の下、私は雨傘を差し、長靴を履いて家路を急いでいた。\n\
途中、お気に入りの古本屋に寄り、本棚から昔話の絵本や千代紙の本を引っ張り出した。隣のカフェでは、恋人らしき二人が楽しそうに長話をしており、その幸せそうな笑い声や歌声が店外まで聞こえてくる。\n\
その後、私は駅前の人込みを抜けて、赤提灯の誘う居酒屋へ。温かい焼き魚と巻き寿司を味わっていると、大将のさりげない気遣いが身に染み、冷えた心と体がじんわりとほぐれていくのを感じた。"

# ── 预览框专用（左右两框显示效果，与 PNG 生成完全独立）────────
PREV_FONT_SIZE    = 32      # 预览字号（像素）
PREV_RUBY_RATIO   = 0.55    # 振假名大小（占正文字号的比例，0.55 = 55%）
PREV_RUBY_LIFT    = 0       # 振假名顶距（像素，正值下移）
PREV_RUBY_GAP     = -4      # 振假名底距（像素，负值上移）
PREV_LINE_SPACING = 6       # 预览行间距（像素）
PREV_SYNC_SCROLL  = True    # 两框是否同步滚动

# ── PNG 生成专用（与预览无关，改这里不影响预览框）─────────────
PNG_WIDTH        = 1600     # 画布宽度（像素）
PNG_MARGIN_TOP   = 100      # 上边距（像素）
PNG_MARGIN_BOT   = 100      # 下边距（像素）
PNG_MARGIN_LEFT  = 100      # 左边距（像素）
PNG_MARGIN_RIGHT = 100      # 右边距（像素）
PNG_FONT_SIZE    = 60       # 正文字号（像素）
PNG_FONT_WEIGHT  = 500      # 字重（100–900，400=Regular，700=Bold）
PNG_RUBY_SIZE    = 0        # 振假名字号（像素，0 = 自动取字号之半）
PNG_RUBY_LIFT    = 0        # 振假名顶距（像素）
PNG_RUBY_GAP     = -8       # 振假名底距（像素）
PNG_LINE_SPACING = 30       # 行间距（像素）
PNG_PARA_SPACING = 55       # 段落间距（像素）
PNG_BG_COLOR     = "#ffffff"  # 背景色（十六进制）
PNG_FG_COLOR     = "#000000"  # 正文颜色
PNG_RUBY_COLOR   = "#000000"  # 振假名颜色

# ── 界面尺寸 ──────────────────────────────────────────────────
WIN_W = 1540    # 窗口初始宽度
WIN_H = 900     # 窗口初始高度

# ══════════════════════════════════════════════════════════════
#  路径辅助
# ══════════════════════════════════════════════════════════════
def _base() -> str:
    return (os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))

_BASE       = _base()
_FONTS      = os.path.join(_BASE, "fonts")
_OUT        = os.path.join(_BASE, "out")
_KYOKAI_OTF = os.path.join(_FONTS, "A-OTF-KYOKAICAPRO-MEDIUM.OTF")
_NOTO_TTF   = os.path.join(_FONTS, "NotoSerifJP-VF.ttf")
_ICON_PNG   = (os.path.join(sys._MEIPASS, "icon.png")
               if getattr(sys, "frozen", False)
               else os.path.join(_BASE, "icon.png"))

def _ensure_dirs():
    os.makedirs(_FONTS, exist_ok=True)
    os.makedirs(_OUT,   exist_ok=True)

# ══════════════════════════════════════════════════════════════
#  Qt
# ══════════════════════════════════════════════════════════════
from PyQt6.QtCore    import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui     import (QColor, QFont, QFontDatabase,QPainter,
                              QTextBlockFormat, QTextCursor, QTextOption)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QFileDialog, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSlider, QSpinBox, QSplitter, QStatusBar, QTextEdit, QToolButton,
    QVBoxLayout, QWidget,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore    import QWebEngineSettings

# ── UI 字体（系统中文，用于所有标签/按钮等非渲染控件）──────────
_UI = "Microsoft YaHei UI"

# ── 预览专用字体（教科书体，左右两框内容）──────────────────────
_KYOKAI_FAMILY = "A-OTF Kyoukasho ICA Pro"

# ── 和风配色常量 ────────────────────────────────────────────────
_C_PAPER   = "#f5f0e8"   # 和纸底色
_C_INK     = "#2c1a0e"   # 墨色（深棕黑）
_C_GOLD    = "#8b6914"   # 金茶
_C_BORDER  = "#c4a882"   # 边框（浅褐）
_C_GRP_BG  = "#faf7f0"   # GroupBox 背景
_C_SIDE_BG = "#ede8dc"   # 右侧参数面板背景
_C_BTN_P   = "#4a3728"   # 预览按钮（墨茶）
_C_BTN_PH  = "#6b5040"   # 预览按钮悬停
_C_BTN_G   = "#2e5a3a"   # 生成按钮（深緑）
_C_BTN_GH  = "#3d7a4f"   # 生成按钮悬停
_C_BTN_C   = "#2e3d5a"   # 复制按钮（深藍）
_C_BTN_CH  = "#3d5280"   # 复制按钮悬停

_COPY_LABELS = {
    "HTML": "📋  以HTML复制",
    "JSON": "📋  以JSON复制",
    "文本": "📋  复制文本",
}


def _load_preview_font() -> str:
    if not os.path.exists(_KYOKAI_OTF):
        return _KYOKAI_FAMILY
    fid = QFontDatabase.addApplicationFont(_KYOKAI_OTF)
    if fid >= 0:
        fams = QFontDatabase.applicationFontFamilies(fid)
        if fams:
            return fams[0]
    return _KYOKAI_FAMILY


# ══════════════════════════════════════════════════════════════
#  HTML 预览构建（仅用于右框）
# ══════════════════════════════════════════════════════════════
def _build_preview_html(
    tokens: list,
    font_size: int,
    ruby_ratio: float,
    line_spacing: int,
    ruby_lift: int,
    ruby_gap: int,
    bg: str = "#ffffff",
    fg: str = "#000000",
    ruby_fg: str = "#000000",
) -> str:
    ruby_size = max(int(font_size * ruby_ratio), 8)
    line_h    = (font_size + ruby_size + line_spacing) / max(font_size, 1)
    font_file = os.path.basename(_KYOKAI_OTF)

    # ── 构建段落：每个 \n 对应一个新段落（1:1 换行）
    # 每个可见字符带 data-i="N"
    parts: list[str] = []
    para:  list[str] = []

    def flush_para():
        # 空行也保留为空段落，维持视觉空行
        parts.append('<p>' + (''.join(para) if para else '&nbsp;') + '</p>')
        para.clear()

    for i, (char, reading) in enumerate(tokens):
        if char == "\n":
            flush_para()
        else:
            if reading:
                para.append(
                    f'<ruby data-i="{i}">{char}<rt>{reading}</rt></ruby>')
            else:
                para.append(f'<span data-i="{i}">{char}</span>')
    if para:
        flush_para()

    body = "\n".join(parts)
    indent = font_size  # 1em 首行缩进

    hl_css = ""
    hl_js  = ""

    return (
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>\n'
        f'@font-face {{\n'
        f'  font-family:"KyokaiFont";\n'
        f'  src:url("{font_file}");\n'
        f'}}\n'
        f'*{{margin:0;padding:0;box-sizing:border-box;}}\n'
        f'html,body{{\n'
        f'  font-family:"KyokaiFont","MS Mincho",serif;\n'
        f'  font-size:{font_size}px;\n'
        f'  line-height:{line_h:.3f};\n'
        f'  background:{bg};\n'
        f'  color:{fg};\n'
        f'  padding:14px;\n'
        f'  word-break:break-all;\n'
        f'  text-align:justify;\n'
        f'}}\n'
        f'p{{\n'
        f'  margin-bottom:{line_spacing}px;\n'
        f'  text-indent:{indent}px;\n'
        f'  text-align:justify;\n'
        f'}}\n'
        f'ruby{{ruby-align:space-around;}}\n'
        f'rt{{\n'
        f'  font-size:{ruby_size}px;\n'
        f'  line-height:1;\n'
        f'  color:{ruby_fg};\n'
        f'}}\n'
        f'::-webkit-scrollbar{{width:8px;}}\n'
        f'::-webkit-scrollbar-track{{background:{_C_PAPER};border-radius:4px;}}\n'
        f'::-webkit-scrollbar-thumb{{background:{_C_BORDER};border-radius:4px;min-height:24px;}}\n'
        f'::-webkit-scrollbar-thumb:hover{{background:{_C_GOLD};}}\n'
        f'{hl_css}\n'
        f'</style>{hl_js}</head>\n'
        f'<body>{body}</body></html>'
    )


# ══════════════════════════════════════════════════════════════
#  后台线程
# ══════════════════════════════════════════════════════════════
class FuriganaWorker(QThread):
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def run(self):
        try:
            from gen_rubi_fugashi2 import add_furigana
            tokens: list = []
            # 逐行标注，保留换行符（分词器会吞掉 \n）
            lines = self.text.split("\n")
            for i, line in enumerate(lines):
                if i > 0:
                    tokens.append(("\n", None))
                if line:
                    tokens += [
                        (item[0], item[1] if item[1] else None)
                        for item in add_furigana(line, mode="json")
                    ]
            self.done.emit(tokens)
        except Exception as exc:
            self.error.emit(str(exc))


class PngWorker(QThread):
    done  = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, text: str, kwargs: dict):
        super().__init__()
        self.text   = text
        self.kwargs = kwargs

    def run(self):
        try:
            from html2png_rubi import render_rubi_text
            path = render_rubi_text(self.text, **self.kwargs)
            self.done.emit(path)
        except Exception as exc:
            self.error.emit(str(exc))


# ══════════════════════════════════════════════════════════════
#  左框：可编辑输入框（教科书体，两端对齐，首行缩进）
# ══════════════════════════════════════════════════════════════
class _TextEdit(QTextEdit):
    def __init__(self, family: str, px_size: int):
        super().__init__()
        self.setAcceptRichText(False)
        self._apply_font(family, px_size)
        self.setStyleSheet(
            "QTextEdit{"
            f"background:{_C_PAPER};"
            f"border:1px solid {_C_BORDER};"
            "border-radius:3px;"
            "padding:14px;"
            "}"
            "QScrollBar:vertical{"
            f"background:{_C_PAPER}; width:8px; border-radius:4px; margin:0;"
            "}"
            "QScrollBar::handle:vertical{"
            f"background:{_C_BORDER}; border-radius:4px; min-height:24px;"
            "}"
            "QScrollBar::handle:vertical:hover{"
            f"background:{_C_GOLD};"
            "}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:none;}"
        )
        # 正文文字的换行与对齐
        opt = QTextOption()
        opt.setAlignment(Qt.AlignmentFlag.AlignJustify)
        opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDefaultTextOption(opt)

    def _apply_font(self, family: str, px_size: int):
        f = QFont(family)
        f.setPixelSize(px_size)
        self.setFont(f)
        # 首行缩进 = 1em
        fmt = QTextBlockFormat()
        fmt.setTextIndent(float(px_size))
        fmt.setAlignment(Qt.AlignmentFlag.AlignJustify)
        cur = self.textCursor()
        cur.select(QTextCursor.SelectionType.Document)
        cur.setBlockFormat(fmt)
        cur.clearSelection()
        self.setTextCursor(cur)

    def update_font_size(self, family: str, px_size: int):
        self._apply_font(family, px_size)

    # ★ 核心修复：接管绘制事件，强制让占位符自动换行
    def paintEvent(self, event):
        placeholder = self.placeholderText()
        # 当输入框没有内容，且设置了占位符时
        if not self.toPlainText() and placeholder:
            # 1. 暂时清空原生占位符并调用父类绘制，避免原生单行文本重叠
            self.setPlaceholderText("")
            super().paintEvent(event)
            self.setPlaceholderText(placeholder)

            # 2. 开始手动绘制我们自己的高性能换行占位符
            painter = QPainter(self.viewport())
            
            # 使用半透明的墨色（RGB: 44, 26, 14），透明度 110，视觉效果更柔和优雅
            painter.setPen(QColor(44, 26, 14, 110))
            painter.setFont(self.font())
            
            # 核心：顺应 QStylesheet 里的 padding: 14px，四边均内缩 14 像素
            rect = self.viewport().rect().adjusted(14, 14, -14, -14)
            
            # 组合 Flags：TextWordWrap（自动换行） + AlignJustify（两端对齐）
            draw_flags = Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignJustify
            painter.drawText(rect, draw_flags, placeholder)
            painter.end()
        else:
            # 正常有字的状态下，走原生的绘制流程
            super().paintEvent(event)


# ══════════════════════════════════════════════════════════════
#  通用控件辅助
# ══════════════════════════════════════════════════════════════
def _lbl(text: str, size: int = 12, bold: bool = False,
         color: str = _C_INK) -> QLabel:
    lbl = QLabel(text)
    w = "bold" if bold else "normal"
    lbl.setStyleSheet(
        f"font-family:'{_UI}'; font-size:{size}px; font-weight:{w};"
        f"color:{color}; background:transparent;")
    return lbl


def _group(title: str) -> QGroupBox:
    gb = QGroupBox(title)
    gb.setStyleSheet(
        f"QGroupBox{{font-family:'{_UI}';font-weight:bold;font-size:12px;"
        f"color:{_C_INK};"
        f"border:1px solid {_C_BORDER};border-radius:5px;"
        f"margin-top:10px;padding:6px;"
        f"background:{_C_GRP_BG};}}"
        f"QGroupBox::title{{subcontrol-origin:margin;left:10px;padding:0 5px;"
        f"background:{_C_GRP_BG};}}"
    )
    return gb


def _btn_style(normal: str, hover: str, text_col: str = "white") -> str:
    return (
        f"QPushButton{{background:{normal};color:{text_col};border:none;"
        f"border-radius:4px;font-size:13px;font-weight:bold;"
        f"font-family:'{_UI}';}}"
        f"QPushButton:hover{{background:{hover};}}"
        f"QPushButton:disabled{{background:#bdc3c7;color:#888;}}"
    )


def _sld_style() -> str:
    return (
        f"QSlider::groove:horizontal{{height:4px;background:{_C_BORDER};"
        "border-radius:2px;}"
        f"QSlider::handle:horizontal{{background:{_C_GOLD};width:14px;height:14px;"
        "margin:-5px 0;border-radius:7px;}"
        f"QSlider::sub-page:horizontal{{background:{_C_GOLD};border-radius:2px;}}"
    )


# ══════════════════════════════════════════════════════════════
#  主窗口
# ══════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        _ensure_dirs()
        self._kyokai = _load_preview_font()
        self.setWindowTitle("振假名 PNG 生成器")
        # self.setMinimumSize(1100, 700)
        self.setMinimumSize(950, 580)
        from PyQt6.QtGui import QIcon
        if os.path.exists(_ICON_PNG):
            self.setWindowIcon(QIcon(_ICON_PNG))

        # ── 预览参数（从顶部常量初始化）
        self._prev_font_size    = PREV_FONT_SIZE
        self._prev_ruby_ratio   = PREV_RUBY_RATIO
        self._prev_ruby_lift    = PREV_RUBY_LIFT
        self._prev_ruby_gap     = PREV_RUBY_GAP
        self._prev_line_spacing = PREV_LINE_SPACING
        self._prev_sync         = PREV_SYNC_SCROLL

        # ── PNG 参数（从顶部常量初始化）
        self._p_out          = self._new_out()
        self._p_width        = PNG_WIDTH
        self._p_mg_top       = PNG_MARGIN_TOP
        self._p_mg_bot       = PNG_MARGIN_BOT
        self._p_mg_left      = PNG_MARGIN_LEFT
        self._p_mg_right     = PNG_MARGIN_RIGHT
        self._p_font_size    = PNG_FONT_SIZE
        self._p_font_weight  = PNG_FONT_WEIGHT
        self._p_ruby_size    = PNG_RUBY_SIZE
        self._p_ruby_lift    = PNG_RUBY_LIFT
        self._p_ruby_gap     = PNG_RUBY_GAP
        self._p_line_spacing = PNG_LINE_SPACING
        self._p_para_spacing = PNG_PARA_SPACING
        self._p_bg           = PNG_BG_COLOR
        self._p_fg           = PNG_FG_COLOR
        self._p_ruby_fg      = PNG_RUBY_COLOR

        # ── 内部状态
        self._copy_format: str    = "HTML"
        self._cached_tokens: list = []
        self._furigana_worker: Optional[FuriganaWorker] = None
        self._png_worker:     Optional[PngWorker]       = None
        self._suppress_sync   = False

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._trigger_furigana)

        # 右框滚动 → 左框同步（poll 方式）
        self._web_scroll_timer = QTimer()
        self._web_scroll_timer.setInterval(60)
        self._web_scroll_timer.timeout.connect(self._poll_web_scroll)
        self._web_scroll_timer.start()


        self._build_ui()
        self._center(WIN_W, WIN_H)
        # 初始化时让左右两框等宽
        QTimer.singleShot(0, self._equalize_panes)
        QTimer.singleShot(600, self._trigger_furigana)

    # ──────────────────────────────────────────────────────────
    # 布局
    # ──────────────────────────────────────────────────────────
    def _build_ui(self):
        # 全局窗口底色
        self.setStyleSheet(f"QMainWindow{{background:{_C_PAPER};}}")

        root = QWidget()
        root.setStyleSheet(f"background:{_C_PAPER};")
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(self._make_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet(
            f"QSplitter::handle{{background:{_C_BORDER};width:2px;}}")
        splitter.addWidget(self._build_left_col())
        splitter.addWidget(self._build_right_col())
        self._params_panel = self._build_params_panel()
        self._params_panel.setMinimumWidth(240)
        splitter.addWidget(self._params_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        self._splitter = splitter
        vbox.addWidget(splitter, stretch=1)

        self._statusbar = QStatusBar()
        self._statusbar.setStyleSheet(
            f"font-family:'{_UI}'; font-size:11px;"
            f"background:{_C_PAPER}; color:{_C_INK};"
            f"border-top:1px solid {_C_BORDER};")
        self._statusbar.showMessage("就绪")
        self.setStatusBar(self._statusbar)

    def _make_header(self) -> QWidget:
        hdr = QFrame()
        hdr.setFixedHeight(62)
        hdr.setStyleSheet(
            f"background:{_C_INK};"
            f"border-bottom:2px solid {_C_GOLD};")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(24, 0, 24, 0)

        # 日语标题，使用教科书体
        title = QLabel("振り仮名　PNGジェネレーター")
        title.setStyleSheet(
            f"color:{_C_PAPER};"
            f"font-family:'{self._kyokai}','{_KYOKAI_FAMILY}','MS Mincho',serif;"
            "font-size:26px;"
            "background:transparent;"
            "letter-spacing:2px;"
        )
        lay.addWidget(title)
        lay.addStretch()

        # 副标题
        sub = QLabel("振假名标注  ·  PNG 图像生成工具")
        sub.setStyleSheet(
            f"color:{_C_BORDER}; font-size:18px;"
            f"font-family:'{_UI}'; background:transparent;")
        lay.addWidget(sub)
        return hdr

    # ── 左列
    def _build_left_col(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background:{_C_PAPER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 5, 10)
        lay.setSpacing(7)

        lay.addWidget(_lbl("输入文本", size=13, bold=True))

        self.txt_input = _TextEdit(self._kyokai, self._prev_font_size)
        self.txt_input.setPlaceholderText("ここに日本語のテキストを入力。右側のプレビューに自動で振り仮名が表示されます。")
        self.txt_input.setPlainText(TEXTS)
        self.txt_input.textChanged.connect(self._on_text_changed)
        self.txt_input.verticalScrollBar().valueChanged.connect(
            self._sync_left_to_right)
        lay.addWidget(self.txt_input, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_preview = QPushButton("🔍  刷新预览")
        self.btn_preview.setFixedHeight(40)
        self.btn_preview.setStyleSheet(_btn_style(_C_BTN_P, _C_BTN_PH))
        self.btn_preview.clicked.connect(self._trigger_furigana)
        btn_row.addWidget(self.btn_preview, stretch=1)

        self.btn_generate = QPushButton("▶  生成 PNG")
        self.btn_generate.setFixedHeight(40)
        self.btn_generate.setStyleSheet(_btn_style(_C_BTN_G, _C_BTN_GH))
        self.btn_generate.clicked.connect(self._on_generate)
        btn_row.addWidget(self.btn_generate, stretch=1)

        # ── 复制分裂按钮（左：动作；右：下拉选格式）
        copy_wrap = QFrame()
        copy_wrap.setFixedHeight(40)
        copy_wrap.setStyleSheet("QFrame{border:none;background:transparent;}")
        cw_lay = QHBoxLayout(copy_wrap)
        cw_lay.setContentsMargins(0, 0, 0, 0)
        cw_lay.setSpacing(0)

        self.btn_copy = QPushButton(_COPY_LABELS[self._copy_format])
        self.btn_copy.setFixedHeight(40)
        self.btn_copy.setStyleSheet(
            f"QPushButton{{background:{_C_BTN_C};color:white;border:none;"
            f"border-top-left-radius:4px;border-bottom-left-radius:4px;"
            f"border-top-right-radius:0;border-bottom-right-radius:0;"
            f"font-size:13px;font-weight:bold;font-family:'{_UI}';}}"
            f"QPushButton:hover{{background:{_C_BTN_CH};}}"
            f"QPushButton:disabled{{background:#bdc3c7;color:#888;}}"
        )
        self.btn_copy.clicked.connect(self._on_copy)
        cw_lay.addWidget(self.btn_copy, stretch=1)

        self.btn_copy_arrow = QToolButton()
        self.btn_copy_arrow.setFixedWidth(24)
        self.btn_copy_arrow.setFixedHeight(40)
        self.btn_copy_arrow.setText("▾")
        self.btn_copy_arrow.setStyleSheet(
            f"QToolButton{{background:{_C_BTN_C};color:white;border:none;"
            f"border-left:1px solid {_C_BTN_CH};"
            f"border-top-right-radius:4px;border-bottom-right-radius:4px;"
            f"border-top-left-radius:0;border-bottom-left-radius:0;"
            f"font-size:12px;}}"
            f"QToolButton:hover{{background:{_C_BTN_CH};}}"
            f"QToolButton::menu-indicator{{image:none;}}"
        )
        copy_menu = QMenu(self)
        copy_menu.setStyleSheet(
            f"QMenu{{font-family:'{_UI}';font-size:13px;"
            f"background:white;border:1px solid {_C_BORDER};border-radius:4px;}}"
            f"QMenu::item{{padding:6px 20px;}}"
            f"QMenu::item:selected{{background:{_C_BTN_C};color:white;}}"
        )
        for fmt in ("HTML", "JSON", "文本"):
            act = copy_menu.addAction(fmt)
            act.triggered.connect(lambda *_, f=fmt: self._set_copy_format(f))
        self.btn_copy_arrow.setMenu(copy_menu)
        self.btn_copy_arrow.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        cw_lay.addWidget(self.btn_copy_arrow)

        btn_row.addWidget(copy_wrap, stretch=1)
        lay.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.progress.setStyleSheet(
            f"QProgressBar{{border:none;background:{_C_BORDER};border-radius:2px;}}"
            f"QProgressBar::chunk{{background:{_C_GOLD};border-radius:2px;}}"
        )
        lay.addWidget(self.progress)
        return w

    # ── 右列
    def _build_right_col(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background:{_C_PAPER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(5, 10, 10, 10)
        lay.setSpacing(7)

        title_row = QHBoxLayout()
        title_row.addWidget(_lbl("振假名预览", size=13, bold=True))
        self.lbl_status = _lbl("", size=11, color=_C_GOLD)
        title_row.addWidget(self.lbl_status)
        title_row.addStretch()
        lay.addLayout(title_row)

        self.web = QWebEngineView()
        self.web.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.web.setStyleSheet(
            f"border:1px solid {_C_BORDER}; border-radius:3px;")
        self.web.setHtml(
            f"<body style='background:{_C_PAPER}'></body>",
            QUrl.fromLocalFile(_FONTS + os.sep),
        )
        lay.addWidget(self.web, stretch=1)

        # 字号滑块行
        fs_row = QHBoxLayout()
        fs_row.setSpacing(8)
        lfs = _lbl("字号", size=12)
        lfs.setFixedWidth(32)
        fs_row.addWidget(lfs)

        self.sld_fs = QSlider(Qt.Orientation.Horizontal)
        self.sld_fs.setRange(8, 120)
        self.sld_fs.setValue(self._prev_font_size)
        self.sld_fs.setStyleSheet(_sld_style())
        self.sld_fs.valueChanged.connect(self._on_fs_changed)
        fs_row.addWidget(self.sld_fs, stretch=1)

        self.lbl_fs_val = _lbl(f"{self._prev_font_size} px", size=12)
        self.lbl_fs_val.setFixedWidth(50)
        fs_row.addWidget(self.lbl_fs_val)

        self.btn_gear = QToolButton()
        self.btn_gear.setText("⚙")
        self.btn_gear.setCheckable(True)
        self.btn_gear.setToolTip("更多显示设置")
        self.btn_gear.setStyleSheet(
            "QToolButton{font-size:19px;border:none;background:transparent;"
            "color:" + _C_GOLD + ";padding:0 4px;}"
            "QToolButton:checked{color:" + _C_INK + ";}"
        )
        self.btn_gear.toggled.connect(self._toggle_gear)
        fs_row.addWidget(self.btn_gear)
        lay.addLayout(fs_row)

        self.gear_panel = self._build_gear_panel()
        self.gear_panel.hide()
        lay.addWidget(self.gear_panel)
        return w

    def _build_gear_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame{{background:{_C_GRP_BG};"
            f"border:1px solid {_C_BORDER};border-radius:6px;}}")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(7)

        self.sld_ruby, _ = self._slider_row(
            lay, "振假名大小", 10, 90,
            int(self._prev_ruby_ratio * 100),
            fmt=lambda v: f"{v} %", cb=self._on_ruby_ratio_changed)
        self.sld_lift, _ = self._slider_row(
            lay, "振假名顶距", -20, 30, self._prev_ruby_lift,
            fmt=lambda v: f"{v} px", cb=self._on_ruby_lift_changed)
        self.sld_gap, _ = self._slider_row(
            lay, "振假名底距", -20, 20, self._prev_ruby_gap,
            fmt=lambda v: f"{v} px", cb=self._on_ruby_gap_changed)
        self.sld_ls, _ = self._slider_row(
            lay, "行间距", 0, 80, self._prev_line_spacing,
            fmt=lambda v: f"{v} px", cb=self._on_ls_changed)

        self.chk_sync = QCheckBox("两框按比例同步滚动")
        self.chk_sync.setChecked(PREV_SYNC_SCROLL)
        self.chk_sync.setStyleSheet(
            f"font-family:'{_UI}'; font-size:12px; color:{_C_INK};")
        self.chk_sync.stateChanged.connect(
            lambda s: setattr(self, "_prev_sync", bool(s)))
        lay.addWidget(self.chk_sync)
        return panel

    def _slider_row(self, parent_lay, label: str, min_: int, max_: int,
                    value: int, fmt, cb) -> tuple:
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = _lbl(label, size=12)
        lbl.setFixedWidth(72)
        row.addWidget(lbl)

        sld = QSlider(Qt.Orientation.Horizontal)
        sld.setRange(min_, max_)
        sld.setValue(value)
        sld.setStyleSheet(_sld_style())
        row.addWidget(sld, stretch=1)

        val = _lbl(fmt(value), size=12)
        val.setFixedWidth(48)
        row.addWidget(val)

        parent_lay.addLayout(row)
        sld.valueChanged.connect(lambda v: val.setText(fmt(v)))
        sld.valueChanged.connect(cb)
        return sld, val

    def _toggle_gear(self, on: bool):
        self.gear_panel.setVisible(on)

    # ── PNG 参数面板（右侧，完全独立）
    def _build_params_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{border:none;background:{_C_SIDE_BG};}}"
            "QScrollBar:vertical{width:8px;background:transparent;}"
            f"QScrollBar::handle:vertical{{background:{_C_BORDER};"
            "border-radius:4px;min-height:20px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical"
            "{height:0px;}"
        )

        inner = QWidget()
        inner.setStyleSheet(f"background:{_C_SIDE_BG};")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(14, 14, 14, 14)   # 内边距，不紧贴侧面
        lay.setSpacing(10)

        # 标题
        t = QLabel("PNG 生成参数")
        t.setStyleSheet(
            f"font-family:'{_UI}'; font-size:14px; font-weight:bold;"
            f"color:{_C_INK}; background:transparent;"
            f"padding-bottom:4px; border-bottom:1px solid {_C_BORDER};")
        lay.addWidget(t)

        # 输出文件
        grp = _group("输出文件")
        gl  = QVBoxLayout(grp)
        pr  = QHBoxLayout()
        self.le_out = QLineEdit(self._p_out)
        self.le_out.setStyleSheet(
            f"font-family:'{_UI}'; font-size:11px;"
            f"background:white; border:1px solid {_C_BORDER};"
            "border-radius:3px; padding:2px 5px;")
        pr.addWidget(self.le_out)
        b = QPushButton("…"); b.setFixedWidth(30)
        b.setStyleSheet(f"font-family:'{_UI}'; font-size:12px;")
        b.clicked.connect(self._browse_out)
        pr.addWidget(b)
        gl.addLayout(pr)
        rb = QPushButton("↺ 新时间戳")
        rb.setFixedHeight(26)
        rb.setStyleSheet(
            f"font-family:'{_UI}'; font-size:12px;"
            f"background:{_C_GRP_BG}; border:1px solid {_C_BORDER};"
            "border-radius:3px;")
        rb.clicked.connect(self._reset_out)
        gl.addWidget(rb)
        lay.addWidget(grp)

        # 画布 & 边距
        grp2 = _group("画布 & 边距")
        gl2  = QVBoxLayout(grp2)
        self.sp_width = self._spinrow(gl2, "宽度 (px)", self._p_width,   100, 9999)
        self.sp_mgt   = self._spinrow(gl2, "上边距",    self._p_mg_top,   0, 500)
        self.sp_mgb   = self._spinrow(gl2, "下边距",    self._p_mg_bot,   0, 500)
        self.sp_mgl   = self._spinrow(gl2, "左边距",    self._p_mg_left,  0, 500)
        self.sp_mgr   = self._spinrow(gl2, "右边距",    self._p_mg_right, 0, 500)
        lay.addWidget(grp2)

        # 字体 & 间距
        grp3 = _group("字体 & 间距")
        gl3  = QVBoxLayout(grp3)
        fr   = QHBoxLayout()
        fr.setContentsMargins(0, 0, 0, 0)
        lff = _lbl("字体文件", size=12); lff.setFixedWidth(78)
        fr.addWidget(lff)
        self.le_font = QLineEdit(_NOTO_TTF if os.path.exists(_NOTO_TTF) else "")
        self.le_font.setStyleSheet(
            f"font-family:'{_UI}'; font-size:10px;"
            f"background:white; border:1px solid {_C_BORDER};"
            "border-radius:3px; padding:2px 4px;")
        fr.addWidget(self.le_font)
        bf = QPushButton("…"); bf.setFixedWidth(30)
        bf.setStyleSheet(f"font-family:'{_UI}'; font-size:12px;")
        bf.clicked.connect(self._browse_font)
        fr.addWidget(bf)
        gl3.addLayout(fr)

        self.sp_fs  = self._spinrow(gl3, "字号 (px)",  self._p_font_size,    8, 300)
        self.sp_fw  = self._spinrow(gl3, "字重",        self._p_font_weight, 100, 900)
        self.sp_rs  = self._spinrow(gl3, "振假名字号",  self._p_ruby_size,    0, 200)
        self.sp_rl  = self._spinrow(gl3, "振假名顶距",  self._p_ruby_lift, -100, 100)
        self.sp_rg  = self._spinrow(gl3, "振假名底距",  self._p_ruby_gap,  -100, 100)
        self.sp_lsp = self._spinrow(gl3, "行间距",      self._p_line_spacing,  0, 300)
        self.sp_psp = self._spinrow(gl3, "段落间距",    self._p_para_spacing,  0, 300)
        lay.addWidget(grp3)

        # 颜色
        grp4 = _group("颜色")
        gl4  = QVBoxLayout(grp4)
        self.btn_bg  = self._color_row(gl4, "背景色",    "_p_bg")
        self.btn_fg  = self._color_row(gl4, "正文颜色",  "_p_fg")
        self.btn_rfg = self._color_row(gl4, "振假名颜色","_p_ruby_fg")
        lay.addWidget(grp4)

        lay.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _spinrow(self, parent_lay, label: str,
                 default: int, minv: int, maxv: int) -> QSpinBox:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        lbl = _lbl(label, size=12)
        lbl.setFixedWidth(78)
        row.addWidget(lbl)
        sp = QSpinBox()
        sp.setRange(minv, maxv)
        sp.setValue(default)
        sp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sp.setStyleSheet(
            f"font-family:'{_UI}'; font-size:12px;"
            f"background:white; border:1px solid {_C_BORDER};"
            "border-radius:3px; padding:1px 4px;")
        row.addWidget(sp)          # 不加 addStretch，让 spinbox 充满剩余宽度
        parent_lay.addLayout(row)
        return sp

    def _color_row(self, parent_lay, label: str, attr: str) -> QPushButton:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        lbl = _lbl(label, size=12)
        lbl.setFixedWidth(78)
        row.addWidget(lbl)
        btn = QPushButton()
        btn.setFixedHeight(26)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        color = getattr(self, attr)
        btn.setStyleSheet(
            f"background:{color}; border:1px solid {_C_BORDER};"
            "border-radius:3px;")

        def pick(b=btn, a=attr):
            c = QColorDialog.getColor(QColor(getattr(self, a)), self)
            if c.isValid():
                setattr(self, a, c.name())
                b.setStyleSheet(
                    f"background:{c.name()}; border:1px solid {_C_BORDER};"
                    "border-radius:3px;")

        btn.clicked.connect(pick)
        row.addWidget(btn)
        parent_lay.addLayout(row)
        return btn

    # ──────────────────────────────────────────────────────────
    # 滚动同步
    # ──────────────────────────────────────────────────────────
    def _sync_left_to_right(self, value: int):
        if not self._prev_sync or self._suppress_sync:
            return
        bar  = self.txt_input.verticalScrollBar()
        maxv = bar.maximum()
        if maxv <= 0:
            return
        pct = value / maxv
        js  = (f"var h=document.documentElement.scrollHeight-window.innerHeight;"
               f"if(h>0)window.scrollTo(0,h*{pct:.6f});")
        self.web.page().runJavaScript(js)

    def _poll_web_scroll(self):
        if not self._prev_sync:
            return
        self.web.page().runJavaScript(
            "(function(){var h=document.documentElement.scrollHeight-window.innerHeight;"
            "return h>0?window.scrollY/h:0;})()",
            self._apply_right_scroll)

    def _apply_right_scroll(self, pct):
        if self._suppress_sync or not self._prev_sync or pct is None:
            return
        bar  = self.txt_input.verticalScrollBar()
        maxv = bar.maximum()
        if maxv <= 0:
            return
        target = int(pct * maxv)
        if abs(target - bar.value()) < 2:   # 差异极小则不动，避免抖动
            return
        self._suppress_sync = True
        bar.setValue(target)
        self._suppress_sync = False


    # ──────────────────────────────────────────────────────────
    # 振假名标注
    # ──────────────────────────────────────────────────────────
    def _on_text_changed(self):
        text = self.txt_input.toPlainText().strip()
        if not text:
            # ★ 核心修改 1：如果左边完全空了，立即清空右边和缓存，不等防抖定时器
            self._debounce.stop()
            self._cached_tokens = []
            self.web.setHtml(f"<body style='background:{_C_PAPER}'></body>")
            self.lbl_status.setText("等待输入")
        else:
            self._debounce.start(1200)
        
        self._reset_out()   # 文本有改动就刷新时间戳

    def _trigger_furigana(self):
        if self._furigana_worker and self._furigana_worker.isRunning():
            return
        text = self.txt_input.toPlainText()   # 不 strip，保持位置与光标一致
        
        if not text.strip():
            # ★ 核心修改 2：防止用户手动点击“刷新预览”时，空文本导致右边不刷新
            self._cached_tokens = []
            self.web.setHtml(f"<body style='background:{_C_PAPER}'></body>")
            self.lbl_status.setText("等待输入")
            return
            
        self.lbl_status.setText("标注中…")
        self.btn_preview.setEnabled(False)
        self._furigana_worker = FuriganaWorker(text)
        self._furigana_worker.done.connect(self._on_furigana_done)
        self._furigana_worker.error.connect(self._on_furigana_error)
        self._furigana_worker.start()

    def _on_furigana_done(self, tokens: list):
        self._cached_tokens = tokens
        self._refresh_html()
        self.lbl_status.setText("预览就绪")
        self.btn_preview.setEnabled(True)

    def _on_furigana_error(self, msg: str):
        self.lbl_status.setText(f"失败：{msg}")
        self.btn_preview.setEnabled(True)

    def _refresh_html(self):
        if not self._cached_tokens:
            return
        html = _build_preview_html(
            self._cached_tokens,
            font_size     = self._prev_font_size,
            ruby_ratio    = self._prev_ruby_ratio,
            line_spacing  = self._prev_line_spacing,
            ruby_lift     = self._prev_ruby_lift,
            ruby_gap      = self._prev_ruby_gap,
            bg            = _C_PAPER,
        )
        self.web.setHtml(html, QUrl.fromLocalFile(_FONTS + os.sep))

    # ──────────────────────────────────────────────────────────
    # 预览滑块回调
    # ──────────────────────────────────────────────────────────
    def _on_fs_changed(self, v: int):
        self._prev_font_size = v
        self.lbl_fs_val.setText(f"{v} px")
        self.txt_input.update_font_size(self._kyokai, v)
        self._refresh_html()

    def _on_ruby_ratio_changed(self, v: int):
        self._prev_ruby_ratio = v / 100.0
        self._refresh_html()

    def _on_ruby_lift_changed(self, v: int):
        self._prev_ruby_lift = v
        self._refresh_html()

    def _on_ruby_gap_changed(self, v: int):
        self._prev_ruby_gap = v
        self._refresh_html()

    def _on_ls_changed(self, v: int):
        self._prev_line_spacing = v
        self._refresh_html()

    # ──────────────────────────────────────────────────────────
    # 复制按钮
    # ──────────────────────────────────────────────────────────
    def _set_copy_format(self, fmt: str):
        self._copy_format = fmt
        self.btn_copy.setText(_COPY_LABELS[fmt])

    def _on_copy(self):
        fmt = self._copy_format
        if not self._cached_tokens:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "请先刷新预览以生成标注。")
            return
        if fmt == "HTML":
            parts: list[str] = []
            for char, reading in self._cached_tokens:
                if char == "\n":
                    parts.append("\n")
                elif reading:
                    parts.append(f"<ruby>{char}<rt>{reading}</rt></ruby>")
                else:
                    parts.append(char)
            QApplication.clipboard().setText("".join(parts))
            self._statusbar.showMessage("已复制 HTML")
        elif fmt == "文本":  # Anki
            parts: list[str] = []
            for char, reading in self._cached_tokens:
                if char == "\n":
                    parts.append("\n")
                elif reading:
                    parts.append(f"{char}[{reading}]")
                else:
                    parts.append(char)
            QApplication.clipboard().setText("".join(parts))
            self._statusbar.showMessage("已复制 文本 格式")
        else:  # JSON
            import json
            data = [{"char": c, "reading": r} for c, r in self._cached_tokens]
            QApplication.clipboard().setText(
                json.dumps(data, ensure_ascii=False, indent=2))
            self._statusbar.showMessage("已复制 JSON")

    # ──────────────────────────────────────────────────────────
    # PNG 生成
    # ──────────────────────────────────────────────────────────
    def _on_generate(self):
        if self._png_worker and self._png_worker.isRunning():
            return
        text = self.txt_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请先输入文本。")
            return

        out = self.le_out.text().strip()
        if not out or os.path.exists(out):
            out = self._new_out()
            self.le_out.setText(out)
        os.makedirs(os.path.dirname(out), exist_ok=True)

        fp = self.le_font.text().strip() or None
        rs = self.sp_rs.value() or None

        kwargs = dict(
            output_path   = out,
            width         = self.sp_width.value(),
            margin_top    = self.sp_mgt.value(),
            margin_bottom = self.sp_mgb.value(),
            margin_left   = self.sp_mgl.value(),
            margin_right  = self.sp_mgr.value(),
            font_path     = fp,
            font_size     = self.sp_fs.value(),
            font_weight   = self.sp_fw.value(),
            ruby_size     = rs,
            ruby_lift     = self.sp_rl.value(),
            ruby_gap      = self.sp_rg.value(),
            line_spacing  = self.sp_lsp.value(),
            para_spacing  = self.sp_psp.value(),
            bg_color      = self._hex_rgb(self._p_bg),
            text_color    = self._hex_rgb(self._p_fg),
            ruby_color    = self._hex_rgb(self._p_ruby_fg),
        )

        self.btn_generate.setEnabled(False)
        self.progress.show()
        self._statusbar.showMessage("正在生成…")

        self._png_worker = PngWorker(text, kwargs)
        self._png_worker.done.connect(self._on_png_done)
        self._png_worker.error.connect(self._on_png_error)
        self._png_worker.start()

    def _on_png_done(self, path: str):
        self.progress.hide()
        self.btn_generate.setEnabled(True)
        self._statusbar.showMessage(f"已保存：{path}")
        reply = QMessageBox.question(
            self, "生成完成",
            f"PNG 已保存：\n{path}\n\n是否立即打开？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.startfile(path)
            except AttributeError:
                import subprocess
                subprocess.call(
                    ["open" if sys.platform == "darwin" else "xdg-open", path])

    def _on_png_error(self, msg: str):
        self.progress.hide()
        self.btn_generate.setEnabled(True)
        self._statusbar.showMessage(f"错误：{msg}")
        QMessageBox.critical(self, "生成失败", msg)

    # ──────────────────────────────────────────────────────────
    # 工具方法
    # ──────────────────────────────────────────────────────────
    def _new_out(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(_OUT, f"{ts}.png")

    def _reset_out(self):
        self._p_out = self._new_out()
        self.le_out.setText(self._p_out)

    def _center(self, w: int, h: int):
        scr = QApplication.primaryScreen().availableGeometry()
        # 动态安全适配：如果预设宽高超过了屏幕可用区域的 90%，则强制限制在安全线以内
        target_w = min(w, int(scr.width() * 0.9))
        target_h = min(h, int(scr.height() * 0.9))
        
        self.resize(target_w, target_h)
        self.move((scr.width() - target_w) // 2, (scr.height() - target_h) // 2)

    def _equalize_panes(self):
        total = self._splitter.width()
        panel_w = 280
        half = (total - panel_w) // 2
        self._splitter.setSizes([half, half, panel_w])

    def _browse_out(self):
        p, _ = QFileDialog.getSaveFileName(
            self, "保存 PNG", self.le_out.text(),
            "PNG 图像 (*.png);;全部 (*.*)")
        if p:
            self.le_out.setText(p)

    def _browse_font(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择字体", _FONTS,
            "字体文件 (*.ttf *.otf *.ttc);;全部 (*.*)")
        if p:
            self.le_font.setText(p)

    @staticmethod
    def _hex_rgb(h: str) -> tuple:
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


# ══════════════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════════════
def main():
    # 隐藏控制台黑窗口（仅 Windows，未打包时也生效）
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0)
        myappid = "mycompany.rubitools.pnggenerator.1.0" 
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont(_UI, 11))


    # 设置程序图标
    from PyQt6.QtGui import QIcon
    if os.path.exists(_ICON_PNG):
        app.setWindowIcon(QIcon(_ICON_PNG))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
