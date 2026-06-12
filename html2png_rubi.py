"""
html2png_rubi.py — 振假名文字图像生成器
使用 gen_rubi_fugashi2.add_furigana() 标注后渲染为 PNG。

依赖：
    pip install Pillow
"""
from __future__ import annotations

import os
import sys
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from gen_rubi_fugashi2 import add_furigana

# (char, reading_or_None)
Token = tuple[str, Optional[str]]


# ──────────────────────────────────────────────────────────────
# 字体自动探测
# ──────────────────────────────────────────────────────────────
_FONT_CANDIDATES = [
    # ── Noto Serif JP（最优先）──────────────────────────────
    # Windows：手动安装到字体目录的常见路径
    "C:/Windows/Fonts/NotoSerifJP-VF.ttf",
    # "C:/Windows/Fonts/NotoSerifJP[wght].ttf",
    # # 用户字体目录（%LOCALAPPDATA%\Microsoft\Windows\Fonts）
    # os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft/Windows/Fonts/NotoSerifJP-Regular.otf"),
    # os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft/Windows/Fonts/NotoSerifJP[wght].ttf"),
    # # macOS
    # "/Library/Fonts/NotoSerifJP-Regular.otf",
    # os.path.expanduser("~/Library/Fonts/NotoSerifJP-Regular.otf"),
    # # Linux
    # "/usr/share/fonts/opentype/noto/NotoSerifJP-Regular.otf",
    # "/usr/local/share/fonts/NotoSerifJP-Regular.otf",
    # # ── 其他日文字体（后备）────────────────────────────────
    # # Windows
    # "C:/Windows/Fonts/YuMincho.ttf",
    # "C:/Windows/Fonts/msmincho.ttc",
    # "C:/Windows/Fonts/meiryo.ttc",
    # "C:/Windows/Fonts/YuGothB.ttc",
    # "C:/Windows/Fonts/msgothic.ttc",
    # # macOS
    # "/System/Library/Fonts/ヒラギノ明朝 ProN W3.ttc",
    # "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    # # Linux
    # "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    # "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
]


def _find_default_font() -> str:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        "找不到日文字体，请通过 font_path 参数手动指定 TTF/OTF/TTC 文件路径。"
    )


def _load_font(path: str, size: int, weight: Optional[int] = None) -> ImageFont.FreeTypeFont:
    try:
        font = ImageFont.truetype(path, size)
    except Exception:
        font = ImageFont.truetype(path, size, index=0)
    if weight is not None:
        try:
            font.set_variation_by_axes([weight])
        except (AttributeError, OSError):
            pass  # 非可变字体时静默忽略
    return font


# ──────────────────────────────────────────────────────────────
# 字符宽度
# ──────────────────────────────────────────────────────────────
def _str_width(s: str, font: ImageFont.FreeTypeFont) -> int:
    """返回字符串在给定字体下的像素宽度（含 kerning）。"""
    if not s:
        return 0
    try:
        return int(font.getlength(s))
    except AttributeError:
        # Pillow < 9.2
        bbox = font.getbbox(s)
        return max(bbox[2] - bbox[0], 1)


def _token_slot_width(token: Token, main_font, ruby_font) -> int:
    """token 所占的水平槽宽 = max(主字宽, 振假名总宽)。"""
    char, reading = token
    w_main = _str_width(char, main_font)
    if reading:
        return max(w_main, _str_width(reading, ruby_font))
    return w_main


# 小假名集合（附在前字形成一个拍）
_SMALL_KANA = frozenset('ぁぃぅぇぉゃゅょゎっァィゥェォャュョヮッ')


def _mora_split(reading: str) -> list[str]:
    """将假名读音按拍（mora）分组，小假名附于前字。"""
    groups: list[str] = []
    for ch in reading:
        if ch in _SMALL_KANA and groups:
            groups[-1] += ch
        else:
            groups.append(ch)
    return groups


# 行首禁则字符：这些字符不能出现在行首，需跟在前一行末尾
_KINSOKU_START = frozenset(
    '。、．，！？…‥・ー〜）」』】〕｝〉》'
    '!),.:;?]}¢°′″‰℃'
)


# ──────────────────────────────────────────────────────────────
# 折行（含禁则处理）
# ──────────────────────────────────────────────────────────────
def _layout_lines(
    tokens: list[Token],
    max_width: int,
    main_font,
    ruby_font,
) -> list[list[Token]]:
    lines: list[list[Token]] = []
    current: list[Token] = []
    current_w = 0

    for token in tokens:
        w = _token_slot_width(token, main_font, ruby_font)
        if current and current_w + w > max_width:
            lines.append(current)
            current = [token]
            current_w = w
        else:
            current.append(token)
            current_w += w

    if current:
        lines.append(current)

    # 禁则后处理：若某行首 token 的第一字符是禁则字符，将其并入上一行
    i = 1
    while i < len(lines):
        first_char = lines[i][0][0][0]  # token → char → 首字符
        if first_char in _KINSOKU_START and len(lines[i - 1]) > 1:
            lines[i - 1].append(lines[i].pop(0))
            if not lines[i]:
                lines.pop(i)
                continue
        i += 1

    return lines


# ──────────────────────────────────────────────────────────────
# 主渲染函数
# ──────────────────────────────────────────────────────────────
def render_rubi_text(
    text: str,
    output_path: str = "output.png",
    *,
    # 尺寸与边距
    width: int = 900,
    margin_top: int = 60,
    margin_bottom: int = 60,
    margin_left: int = 60,
    margin_right: int = 60,
    # 字体
    font_path: Optional[str] = None,
    font_size: int = 36,
    font_weight: Optional[int] = None,  # 可变字体字重（如 400=Regular, 500=Medium, 700=Bold）
    # 振假名
    ruby_size: Optional[int] = None,
    ruby_lift: int = 4,    # 振假名顶部与行区域顶部之间的空隙
    ruby_gap: int = 3,     # 振假名底部与正文顶部之间的空隙
    # 间距
    line_spacing: int = 18,   # 同段落内行间距（行区域之间的额外空白）
    para_spacing: int = 40,   # 段落之间的额外空白（应 > line_spacing）
    # 颜色
    bg_color: tuple = (255, 255, 255),
    text_color: tuple = (0, 0, 0),
    ruby_color: Optional[tuple] = None,
) -> str:
    """
    将日文文本渲染为带振假名的 PNG 图像。

    Parameters
    ----------
    text          : 输入文本，段落间用 '\\n' 分隔
    output_path   : 输出 PNG 文件路径
    width         : 图像总宽度（像素）
    margin_top/bottom/left/right : 边距（像素）
    font_path     : 字体路径（TTF/OTF/TTC），None 时自动探测
    font_size     : 正文字号（像素）
    ruby_size     : 振假名字号（像素），默认 font_size // 2
    ruby_lift     : 振假名顶部距行区域顶部的空隙（像素）
    ruby_gap      : 振假名底部距正文顶部的空隙（像素）
    line_spacing  : 同段落内行间距（像素）
    para_spacing  : 段落间距（像素）
    bg_color      : 背景色 RGB
    text_color    : 正文颜色 RGB
    ruby_color    : 振假名颜色 RGB，默认同 text_color

    Returns
    -------
    str : 输出文件的绝对路径
    """
    if ruby_size is None:
        ruby_size = max(font_size // 2, 10)
    if ruby_color is None:
        ruby_color = text_color

    font_path = font_path or _find_default_font()
    main_font = _load_font(font_path, font_size, font_weight)
    ruby_font = _load_font(font_path, ruby_size, font_weight)

    # 每行的垂直槽高 = 振假名顶空 + 振假名 + 振假名底空 + 正文
    slot_h = ruby_lift + ruby_size + ruby_gap + font_size
    canvas_w = width - margin_left - margin_right

    # ── 解析段落，标注振假名 ──────────────────────────────────
    paragraphs = [p for p in text.split('\n') if p.strip()]

    para_lines: list[list[list[Token]]] = []
    for para in paragraphs:
        # 段首加全角空格
        para_text = '　' + para.strip()
        tokens: list[Token] = [
            (item[0], item[1] if item[1] else None)
            for item in add_furigana(para_text, mode="json")
        ]
        lines = _layout_lines(tokens, canvas_w, main_font, ruby_font)
        para_lines.append(lines)

    # ── 计算图像总高度 ────────────────────────────────────────
    total_h = 0
    for i, lines in enumerate(para_lines):
        n = len(lines)
        total_h += n * slot_h + (n - 1) * line_spacing
        if i < len(para_lines) - 1:
            total_h += para_spacing

    img_h = margin_top + total_h + margin_bottom

    # ── 创建图像 ──────────────────────────────────────────────
    img  = Image.new("RGB", (width, img_h), bg_color)
    draw = ImageDraw.Draw(img)

    y = margin_top

    for para_idx, lines in enumerate(para_lines):
        for line_idx, line in enumerate(lines):
            is_last_line = (line_idx == len(lines) - 1)

            # 两端对齐：非末行在 token 间均匀分配剩余空间
            slot_widths = [_token_slot_width(t, main_font, ruby_font) for t in line]
            total_w = sum(slot_widths)
            if not is_last_line and len(line) > 1:
                gap = (canvas_w - total_w) / (len(line) - 1)
            else:
                gap = 0.0

            x = float(margin_left)
            for tok_idx, token in enumerate(line):
                char, reading = token
                slot_w = slot_widths[tok_idx]
                w_main = _str_width(char, main_font)

                # 正文字符在槽内水平居中
                x_main = int(x) + (slot_w - w_main) // 2
                y_main = y + ruby_lift + ruby_size + ruby_gap
                draw.text((x_main, y_main), char, font=main_font, fill=text_color)

                # 振假名：1-2-1 分散对齐（按拍分组，两端各占 0.5 单元，拍间占 1 单元）
                if reading:
                    mora_groups = _mora_split(reading)
                    mora_widths = [_str_width(m, ruby_font) for m in mora_groups]
                    total_ruby_w = sum(mora_widths)
                    y_ruby = y + ruby_lift
                    n_mora = len(mora_groups)
                    if n_mora <= 1 or total_ruby_w >= slot_w:
                        # 单拍或振假名比槽宽：居中
                        x_ruby = int(x) + (slot_w - total_ruby_w) // 2
                        draw.text((x_ruby, y_ruby), reading, font=ruby_font, fill=ruby_color)
                    else:
                        # 1-2-1 分散：unit = extra / n_mora，左边距 0.5*unit，拍间 1*unit
                        extra = slot_w - total_ruby_w
                        unit  = extra / n_mora
                        rx    = x + unit / 2
                        for mora, mw in zip(mora_groups, mora_widths):
                            draw.text((int(rx), y_ruby), mora, font=ruby_font, fill=ruby_color)
                            rx += mw + unit

                x += slot_w + gap

            y += slot_h
            if line_idx < len(lines) - 1:
                y += line_spacing

        if para_idx < len(para_lines) - 1:
            y += para_spacing

    img.save(output_path)
    abs_path = os.path.abspath(output_path)
    print(f"[html2png_rubi] 已保存：{abs_path}  ({width}×{img_h}px)")
    return abs_path


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="振假名文字 → PNG")
    parser.add_argument("input",  nargs="?", help="输入文本文件路径（省略则使用内置示例）")  # 输入文件，可选；省略时运行内置示例
    parser.add_argument("output", nargs="?", default="rubi_output.png", help="输出 PNG 路径")  # 输出 PNG 文件路径
    parser.add_argument("--width",         type=int,   default=1600)   # 画布总宽度（像素）
    parser.add_argument("--margin-top",    type=int,   default=100)    # 上边距（像素）
    parser.add_argument("--margin-bottom", type=int,   default=100)    # 下边距（像素）
    parser.add_argument("--margin-left",   type=int,   default=100)    # 左边距（像素）
    parser.add_argument("--margin-right",  type=int,   default=100)    # 右边距（像素）
    parser.add_argument("--font",          type=str,   default=None,  dest="font_path")  # 字体文件路径（TTF/OTF），省略则使用默认字体
    parser.add_argument("--font-size",     type=int,   default=60)    # 正文字号（像素）
    parser.add_argument("--font-weight",   type=int,   default=500,  dest="font_weight")  # 可变字体字重（400=Regular, 500=Medium, 700=Bold）
    parser.add_argument("--ruby-size",     type=int,   default=None)  # 振假名字号（像素），省略则自动取正文字号的一半
    parser.add_argument("--ruby-lift",     type=int,   default=0)     # 振假名顶部距行区域顶端的留白（不影响振假名与正文的间距）
    parser.add_argument("--ruby-gap",      type=int,   default=-8)     # 振假名底部与正文顶部之间的间距（调大可让振假名离汉字更远）
    parser.add_argument("--line-spacing",  type=int,   default=30)    # 行间距，即两行基线之间的额外空白（像素）
    parser.add_argument("--para-spacing",  type=int,   default=55)    # 段落间距，即段落之间的额外空白（像素）
    args = parser.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            sample = f.read()
    else:
        sample = (
            # "来年、日本への留学を予定している私は、海洋科学の研究を深めたいと考えています。そのため、まず日本語能力試験のN2に合格する必要があります。日々の学習では、毎日欠かさず勉強を続けており、アニメやドラマを通じてリスニング力を鍛えています。また、インターネットのニュース記事を読むことで、社会問題や時事に関する語彙を増やしています。留学生活では、専門的な研究活動だけでなく、日本の人々や文化との交流を通じて、さまざまな経験を積み、視野を広げたいと思っています。"
            # "太原科技大学電子情報工学学院に所属する喬建華先生は、電子情報分野の教育改革に積極的に取り組んでいる教員です。彼は「デジタル信号処理」という必修科目の教育内容や指導方法を再構築し、「一教二学三練」という指導モードを導入することで、学生の理論理解とプログラミングによる実践能力の向上に努めています。また、大学院生向けの学術英語ライティング教育においても、モジュール式のオンライン授業を実践し、論文執筆能力の育成に貢献しています。近年は山西省の教学改革プロジェクトにも参加し、電子情報専攻の人材育成に重要な役割を果たしています。\n電子情報工学は、電子工学と情報工学を融合した専門分野であり、コンピュータや通信システム、人工知能などの技術を学ぶことができます。この分野の学生は、プログラミングやデータ解析、回路設計といった実践的なスキルを身につけるとともに、最新の技術動向についても理解を深めます。5GやIoTの普及に伴い、電子情報分野の人材需要は増加しており、卒業後はさまざまな業界で活躍する機会が広がっています。"
            # "太原科技大学機械工学学院に所属する智晋寧先生は、工程機械分野の教育と研究に力を注いでいる教授です。彼は同学院高端工程機械与鉱山装備研究所の所長を務め、工程機械の智能化制御技術、車両伝動理論および特種車両の設計を専門としています。これまで山西省基礎研究プロジェクトや産学連携プロジェクトを複数主宰し、学術論文を30編以上発表、発明特許を10件取得するなど、顕著な研究成果を上げています。また、修士課程指導教員として学生の育成にも尽力しており、山西省科技進歩賞三等賞を受賞するなど、教育・研究の両面で重要な役割を果たしています。\n機械工学は、機械の設計・製造・制御を総合的に学ぶ伝統的な工学分野です。この専攻では、力学、材料力学、熱力学、制御工学などの基礎理論を学び、CAD/CAM、自動化技術、ロボット工学などの実践的なスキルを身につけます。近年、スマート製造や新エネルギー車両の急速な発展に伴い、機械工学の人材需要はますます高まっています。卒業生は、自動車産業、航空宇宙、工程機械、重工業などの分野で幅広く活躍しており、社会のものづくりを支える重要な役割を担っています。"
            "どんよりとした青空の下、私は雨傘を差し、長靴を履いて家路を急いでいた。\n\
途中、お気に入りの古本屋に寄り、本棚から昔話の絵本や千代紙の本を引っ張り出した。隣のカフェでは、恋人らしき二人が楽しそうに長話をしており、その幸せそうな笑い声や歌声が店外まで聞こえてくる。\n\
その後、私は駅前の人込みを抜けて、赤提灯の誘う居酒屋へ。温かい焼き魚と巻き寿司を味わっていると、大将のさりげない気遣いが身に染み、冷えた心と体がじんわりとほぐれていくのを感じた。"
        )

    render_rubi_text(
        sample,
        args.output,
        width=args.width,
        margin_top=args.margin_top,
        margin_bottom=args.margin_bottom,
        margin_left=args.margin_left,
        margin_right=args.margin_right,
        font_path=args.font_path,
        font_size=args.font_size,
        font_weight=args.font_weight,
        ruby_size=args.ruby_size,
        ruby_lift=args.ruby_lift,
        ruby_gap=args.ruby_gap,
        line_spacing=args.line_spacing,
        para_spacing=args.para_spacing,
    )
