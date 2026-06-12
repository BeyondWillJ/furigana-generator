"""
gen_rubi_fugashi2.py — 振假名（ふりがな）标注器
第一步分词由 fugashi + UniDic 完成，DP 对齐层使用 KANJIDIC2。

依赖：
    pip install fugashi unidic-lite   # 或 unidic（完整版）
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from functools import lru_cache
from typing import Optional

import fugashi
from get_xml import get_kanjidic


def _make_tagger() -> fugashi.Tagger:
    if getattr(sys, 'frozen', False):
        dicdir = os.path.join(os.path.dirname(sys.executable), 'unidic', 'dicdir')
        return fugashi.Tagger(f'-d "{dicdir}"')
    import unidic
    return fugashi.Tagger(f'-d "{unidic.DICDIR}"')

# ──────────────────────────────────────────────────────────────
# jamdict 懒加载（用于名词复合词连浊修正）
# SQLite 连接不可跨线程复用，用 threading.local() 保证每个线程独立实例
# ──────────────────────────────────────────────────────────────
import threading
_jmd_local = threading.local()


def _get_jmd():
    if hasattr(_jmd_local, 'jmd'):
        return _jmd_local.jmd
    try:
        from jamdict import Jamdict  # type: ignore
        if getattr(sys, 'frozen', False):
            db_path = os.path.join(sys._MEIPASS, 'jamdict_data', 'jamdict.db')
            _jmd_local.jmd = Jamdict(db_file=db_path, kd2_file=db_path, jmnedict_file=db_path)
        else:
            _jmd_local.jmd = Jamdict()
    except Exception:
        _jmd_local.jmd = None
    return _jmd_local.jmd


def _jmd_reading(surface: str) -> Optional[str]:
    """在 jamdict 中查 surface，返回第一个片假名读音；无词条则返回 None。"""
    jmd = _get_jmd()
    if jmd is None:
        return None
    try:
        res = jmd.lookup(surface)
        if res.entries and res.entries[0].kana_forms:
            return str(res.entries[0].kana_forms[0])
    except Exception:
        pass
    return None


def _jmd_segment_nouns(surfaces: list[str]) -> list[tuple[str, Optional[str]]]:
    """
    对连续名词语素串做全量扫描 + DP 最优分段。

    扫描：对所有 (i, j)（j-i >= 2）组合从短到长查 jamdict，命中则更新；
    不提前停止，因为更长的窗口可能覆盖不同的复合词组。

    DP：在所有命中中找覆盖复合词 token 数最多的非重叠分段方案。
    未被复合词覆盖的单 token 标记 reading=None，回退到 fugashi。
    """
    n = len(surfaces)

    # Step 1：全量扫描，收集所有 jamdict 命中
    hits: dict[tuple[int, int], str] = {}
    for i in range(n):
        for j in range(i + 2, n + 1):      # 从长度 2 一直扩张到最长
            candidate = ''.join(surfaces[i:j])
            r = _jmd_reading(candidate)
            if r is not None:
                hits[(i, j)] = r            # 匹配到也不停止，持续更新

    if not hits:
        return [(s, None) for s in surfaces]

    # Step 2：DP 找最优分段（最大化被复合词覆盖的 token 数）
    # dp[i] = (已覆盖复合词 token 数, 分段列表)
    dp: list[Optional[tuple[int, list[tuple[str, Optional[str]]]]]] = [None] * (n + 1)
    dp[0] = (0, [])

    for i in range(n):
        if dp[i] is None:
            continue
        covered, segs = dp[i]

        # 选项 A：单步跳过当前 token（不用 jamdict）
        j = i + 1
        state_a = (covered, segs + [(surfaces[i], None)])
        if dp[j] is None or state_a[0] > dp[j][0]:
            dp[j] = state_a

        # 选项 B：以 i 为起点的所有 jamdict 命中复合词（从短到长均考虑）
        for j in range(i + 2, n + 1):
            if (i, j) in hits:
                compound_surf = ''.join(surfaces[i:j])
                new_covered = covered + (j - i)
                state_b = (new_covered, segs + [(compound_surf, hits[(i, j)])])
                if dp[j] is None or state_b[0] > dp[j][0]:
                    dp[j] = state_b

    return dp[n][1]  # type: ignore[return-value]


class UserEntry:
    """用户词典条目。
    reading  : 片假名读音
    katakana : True → 振假名保持片假名输出（不转平假名）
    seg      : 手动切分规格，如 ['2','3'] 或 ['2','g']
               数字 = 该表层字符消耗的读音字符数；'g'/'G' = 将剩余表层字符整体成组
    """
    __slots__ = ("reading", "katakana", "seg")

    def __init__(self, reading: str, katakana: bool = False,
                 seg: Optional[list[str]] = None) -> None:
        self.reading  = reading
        self.katakana = katakana
        self.seg      = seg


def _load_user_dict(csv_path: str) -> dict[str, UserEntry]:
    """从 CSV 加载用户词典。
    格式：表层形式,读音规格[,k][,切分规格]

    读音规格（第2列）两种写法：
      ソノアト          普通片假名读音，无切分
      ソ|ノ|アト        假名切分规格：每段对应一个表层字符的读音；
                        假名表层字符自动设为不标注（None）

    第3列起可选：k/K 保持片假名；数字|g 数字切分规格
    """
    entries: dict[str, UserEntry] = {}
    if not os.path.exists(csv_path):
        return entries
    with open(csv_path, encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if not row or row[0].strip().startswith("#"):
                continue
            if len(row) < 2:
                continue
            surface = row[0].strip()
            reading_raw = row[1].strip()
            if not surface or not reading_raw:
                continue
            katakana = False
            seg: Optional[list[str]] = None

            if '|' in reading_raw:
                # 假名切分规格：ソ|ノ|アト → reading='ソノアト', seg=['ソ','ノ','アト']
                parts = [p.strip() for p in reading_raw.split('|')]
                reading = ''.join(parts)
                seg = parts
                for col in row[2:]:
                    if col.strip().lower() == "k":
                        katakana = True
            else:
                reading = reading_raw
                for col in row[2:]:
                    col = col.strip()
                    if col.lower() == "k":
                        katakana = True
                    elif "|" in col:
                        seg = [s.strip() for s in col.split("|")]

            entries[surface] = UserEntry(reading=reading, katakana=katakana, seg=seg)
    return entries


_DICT_CSV     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rubi_dict.csv")
_USER_ENTRIES = _load_user_dict(_DICT_CSV)

# ──────────────────────────────────────────────────────────────
# 路径
# ──────────────────────────────────────────────────────────────
_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_KANJIDIC_XML = os.path.join(_SCRIPT_DIR, "kanjidic2.xml")

# ──────────────────────────────────────────────────────────────
# fugashi 分词器（使用系统已安装的 UniDic）
# ──────────────────────────────────────────────────────────────
_tagger = _make_tagger()


def _get_reading(word) -> str:
    """从 fugashi Word 对象提取片假名读音。
    优先使用实际发音 pron（以捕捉连浊、促音便），并结合 kana 修复长音符号「ー」，以防 DP 对齐失败。
    """
    try:
        if not hasattr(word, 'feature'):
            return ''
            
        kana = word.feature.kana
        pron = word.feature.pron
        
        # 当两个读音都存在且有效时
        if kana and kana != '*' and pron and pron != '*':
            if len(kana) == len(pron):
                # 等长时 kana 在所有位置都正确：
                # - 连浊已反映在 kana 中（与 pron 一致）
                # - kana 用实际母音而非 pron 的长音符「ー」
                # - kana 用正字法的「ヅ/ヂ」而非 pron 的同音「ズ/ジ」
                return kana
            else:
                # 长度不同 → 口语缩略等特殊音变，用 pron
                return pron
        
        # 兜底情况：哪边有值用哪边
        if kana and kana != '*':
            return kana
        if pron and pron != '*':
            return pron
    except AttributeError:
        pass
    return ''


def _correct_reading_by_context(w, prev_tok, next_tok) -> str:
    """
    UniDic は「の + 名詞 + 句読点/文末」パターンで抽象的な読みを選ぶ傾向がある
    （例：青空の下、→ 下=モト）。後続に「に」を付加して再解析することで
    より具体的・物理的な読みを取得できる。

    条件：
      - 対象トークンが 名詞
      - 直前トークンが の（格助詞）
      - 直後トークンが 補助記号（句読点）または文末
    """
    reading = _get_reading(w)
    if not reading:
        return reading
    try:
        if w.feature.pos1 != '名詞':
            return reading
    except AttributeError:
        return reading

    prev_is_no = (
        prev_tok is not None
        and getattr(prev_tok.feature, 'pos2', '') == '格助詞'
        and prev_tok.surface == 'の'
    )
    next_is_boundary = (
        next_tok is None
        or getattr(next_tok.feature, 'pos1', '') == '補助記号'
    )

    if not (prev_is_no and next_is_boundary):
        return reading

    try:
        alt_tokens = list(_tagger(w.surface + 'に'))
        if alt_tokens and alt_tokens[0].surface == w.surface:
            alt = _get_reading(alt_tokens[0])
            if alt and alt != reading:
                return alt
    except Exception:
        pass

    return reading


# ──────────────────────────────────────────────────────────────
# KANJIDIC2 懒加载单例
# ──────────────────────────────────────────────────────────────
_kanjidic = None


def _get_kanjidic():
    global _kanjidic
    if _kanjidic is None and os.path.exists(_KANJIDIC_XML):
        _kanjidic = get_kanjidic(_KANJIDIC_XML)
    return _kanjidic


# ──────────────────────────────────────────────────────────────
# 字符分类
# ──────────────────────────────────────────────────────────────
_RE_KANJI = re.compile(r'[一-鿿㐀-䶿豈-﫿]')
_NOMA     = '々'   # 々


def _is_kanji(ch: str) -> bool:
    return bool(_RE_KANJI.match(ch))


def _is_kana(ch: str) -> bool:
    cp = ord(ch)
    return (0x3041 <= cp <= 0x3096) or (0x30A1 <= cp <= 0x30F6) or cp == 0x30FC


def _is_target(ch: str) -> bool:
    return _is_kanji(ch) or ch == _NOMA


def _kata2hira(s: str) -> str:
    return ''.join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in s)


def _hira2kata(s: str) -> str:
    return ''.join(chr(ord(c) + 0x60) if 0x3041 <= ord(c) <= 0x3096 else c for c in s)


# ──────────────────────────────────────────────────────────────
# 浊化 / 半浊化辅助
# ──────────────────────────────────────────────────────────────
_VOICED = {
    'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
    'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
    'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
    'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
}
_SEMIVOICED = {
    'は': 'ぱ', 'ひ': 'ぴ', 'ふ': 'ぷ', 'へ': 'ぺ', 'ほ': 'ぽ',
}
_DEVOICED = {v: k for k, v in _VOICED.items()}
_DEVOICED.update({v: k for k, v in _SEMIVOICED.items()})


def _voiced_variants(reading: str) -> set[str]:
    if not reading:
        return set()
    variants = {reading}
    first = reading[0]
    if first in _VOICED:
        variants.add(_VOICED[first] + reading[1:])
    if first in _SEMIVOICED:
        variants.add(_SEMIVOICED[first] + reading[1:])
    if first in _DEVOICED:
        variants.add(_DEVOICED[first] + reading[1:])
    return variants


# ──────────────────────────────────────────────────────────────
# 促音便辅助
# ──────────────────────────────────────────────────────────────
_SOKUON_FINAL = frozenset('きくちつひふ')


def _sokuon_variants(reading: str) -> set[str]:
    if len(reading) >= 2 and reading[-1] in _SOKUON_FINAL:
        return {reading[:-1] + 'っ'}
    return set()


# ──────────────────────────────────────────────────────────────
# lookup 读音候选集（KANJIDIC2）
# ──────────────────────────────────────────────────────────────
@lru_cache(maxsize=8192)
def _lookup_readings(ch: str) -> frozenset[str]:
    if ch == _NOMA:
        return frozenset()
    result: set[str] = set()

    kd = _get_kanjidic()
    if kd:
        rdgs = kd.get_readings(ch)
        for r in rdgs["on"]:
            result.add(_kata2hira(r))
        for r in rdgs["kun"]:
            if '.' in r:
                base = r.split('.')[0]
                if base:
                    result.add(_kata2hira(base))
            else:
                # 无点裸词干（なま、うえ 等），去掉前缀/后缀标记符 '-'
                clean = r.strip('-')
                if clean:
                    result.add(_kata2hira(clean))

    return frozenset(result)


def _lookup_readings_with_voiced(ch: str) -> frozenset[str]:
    base = _lookup_readings(ch)
    extended = set(base)
    for r in base:
        extended |= _voiced_variants(r)
        extended |= _sokuon_variants(r)
    return frozenset(extended)


# ──────────────────────────────────────────────────────────────
# 々 专用对齐：等长约束组级 DP
# ──────────────────────────────────────────────────────────────
def _try_noma_split(surface: str, reading: str) -> Optional[list[CharAnnotation]]:
    """
    含々块的对齐逻辑。
    将连续的 (kanji + 々...) 视为一个"组"，组内每个成员分配等长的 reading 片段。
    例：生々/なまなま → 组=(生,cnt=2)，k=2 → 生[なま]々[なま]
        人々/ひとびと → 组=(人,cnt=2)，k=2 → 人[ひと]々[びと]
    若无法满足等长约束则返回 None，调用方应将整块作为一个单元输出。
    """
    # 构建组列表：每组 = (kanji字, 组内字符数)
    groups: list[tuple[str, int]] = []
    for ch in surface:
        if ch == _NOMA:
            if not groups:
                return None  # 々 出现在首位，无前字可重复
            char, cnt = groups[-1]
            groups[-1] = (char, cnt + 1)
        else:
            groups.append((ch, 1))

    n_g = len(groups)
    r   = len(reading)

    # 组级 DP：第 i 组消耗 k_i * cnt_i 个读音字符
    # k_i 必须是该组代表字的合法读音
    reachable = [[False] * (r + 1) for _ in range(n_g + 1)]
    back      = [[None]  * (r + 1) for _ in range(n_g + 1)]
    reachable[0][0] = True

    for i, (ch, cnt) in enumerate(groups):
        candidates = _lookup_readings_with_voiced(ch)
        is_oov     = not candidates
        for j in range(r + 1):
            if not reachable[i][j]:
                continue
            remaining = r - j
            if remaining == 0:
                continue
            max_k = min(remaining // cnt, 8)
            for k in range(1, max_k + 1):
                total = k * cnt
                seg   = reading[j : j + k]
                ok    = is_oov or (seg in candidates)
                if ok and not reachable[i + 1][j + total]:
                    reachable[i + 1][j + total] = True
                    back[i + 1][j + total]      = (i, j, k)

    if not reachable[n_g][r]:
        return None

    # 回溯，展开每组为逐字标注
    group_list: list[tuple[str, int, int, int]] = []  # (ch, cnt, r_start, k)
    ci, cj = n_g, r
    while ci > 0:
        pi, pj, k = back[ci][cj]
        ch, cnt   = groups[pi]
        group_list.append((ch, cnt, pj, k))
        ci, cj = pi, pj
    group_list.reverse()

    result: list[CharAnnotation] = []
    s_idx = 0
    for ch, cnt, r_start, k in group_list:
        result.append((ch, reading[r_start : r_start + k]))
        s_idx += 1
        for m in range(1, cnt):
            result.append((surface[s_idx], reading[r_start + m * k : r_start + (m + 1) * k]))
            s_idx += 1
    return result


# ──────────────────────────────────────────────────────────────
# DP 对齐
# ──────────────────────────────────────────────────────────────
def _dp_split(surface: str, reading: str) -> Optional[list[tuple[str, str]]]:
    n = len(surface)
    r = len(reading)
    reachable = [[False] * (r + 1) for _ in range(n + 1)]
    back      = [[None]  * (r + 1) for _ in range(n + 1)]
    reachable[0][0] = True

    for i in range(n):
        ch         = surface[i]
        candidates = _lookup_readings_with_voiced(ch)
        is_noma    = (ch == _NOMA)
        is_oov     = (not candidates) and (not is_noma)

        for j in range(r + 1):
            if not reachable[i][j]:
                continue
            remaining = r - j
            if remaining == 0:
                continue
            max_k = min(remaining, 8)
            for k in range(1, max_k + 1):
                seg = reading[j:j+k]
                if is_noma:
                    ok = k <= 4
                elif is_oov:
                    ok = True
                else:
                    ok = seg in candidates
                if ok and not reachable[i+1][j+k]:
                    reachable[i+1][j+k] = True
                    back[i+1][j+k]      = (i, j)

    if not reachable[n][r]:
        return None

    result = []
    ci, cj = n, r
    while ci > 0:
        pi, pj = back[ci][cj]
        result.append((surface[pi], reading[pj:cj]))
        ci, cj = pi, pj
    result.reverse()
    return result


CharAnnotation = tuple[str, Optional[str]]


# ──────────────────────────────────────────────────────────────
# 形态素处理
# ──────────────────────────────────────────────────────────────
def _process_morpheme(surface: str, reading_kata: str) -> list[CharAnnotation]:
    if not reading_kata:
        return [(ch, None) for ch in surface]

    reading = _kata2hira(reading_kata)

    if not any(_is_target(c) for c in surface):
        return [(ch, None) for ch in surface]

    blocks = _segment_by_kana_anchors(surface, reading)
    if blocks is None:
        return _fallback_whole(surface, reading)

    result: list[CharAnnotation] = []
    for block_surface, block_reading in blocks:
        if block_reading is None:
            for ch in block_surface:
                result.append((ch, None))
            continue
        if not any(_is_target(c) for c in block_surface):
            for ch in block_surface:
                result.append((ch, None))
            continue
        result.extend(_split_kanji_block(block_surface, block_reading))

    return result


def _segment_by_kana_anchors(
    surface: str, reading: str
) -> Optional[list[tuple[str, Optional[str]]]]:
    blocks: list[tuple[str, Optional[str]]] = []
    r_pos     = 0
    kanji_buf = []

    for ch in surface:
        if _is_target(ch):
            kanji_buf.append(ch)
            continue

        hira_ch = _kata2hira(ch)
        found   = reading.find(hira_ch, r_pos)
        # 若锚点落在当前指针位置（found == r_pos），漢字会得到空读音——假锚点。
        # 強制从 r_pos+1 重搜，确保漢字至少消耗 1 个读音字符。
        if found == r_pos and kanji_buf:
            found = reading.find(hira_ch, r_pos + 1)

        if found != -1 and kanji_buf:
            kanji_reading = reading[r_pos:found]
            blocks.append((''.join(kanji_buf), kanji_reading))
            kanji_buf = []
            r_pos     = found
        elif found == -1 and kanji_buf:
            kanji_buf.append(ch)
            continue
        elif found != -1 and not kanji_buf:
            r_pos = found
        elif found == -1 and not kanji_buf:
            blocks.append((ch, None))
            continue

        if r_pos < len(reading) and reading[r_pos] == hira_ch:
            blocks.append((ch, None))
            r_pos += 1
        else:
            blocks.append((ch, None))

    if kanji_buf:
        blocks.append((''.join(kanji_buf), reading[r_pos:]))

    return blocks


def _dp_split_partial(
    surface: str, reading: str
) -> Optional[list[tuple[str, str]]]:
    """
    双向保守部分 DP 切分。

    字符 i 的确认条件：
      - 正向 DP 推进到 i+1（从左可达）
      - 反向 DP 推进到 i（从右可达）
      - 左邻也可达或 i 为左边界
      - 右邻也可达或 i 为右边界

    实现：正向找最远可达 i_fwd，保守确认前 i_fwd-1 字；
    反向找最左可达 i_bwd，保守确认 i_bwd+1 之后各字；
    中间未确认部分整块保留。
    """
    n, r = len(surface), len(reading)
    if n <= 1:
        return None

    # ── 正向 DP ──────────────────────────────────────────────────
    fwd = [[False] * (r + 1) for _ in range(n + 1)]
    fb  = [[None]  * (r + 1) for _ in range(n + 1)]
    fwd[0][0] = True
    for i in range(n):
        ch    = surface[i]
        cands = _lookup_readings_with_voiced(ch)
        is_noma = ch == _NOMA
        is_oov  = not cands and not is_noma
        for j in range(r + 1):
            if not fwd[i][j]:
                continue
            for k in range(1, min(r - j, 8) + 1):
                seg = reading[j:j + k]
                ok  = k <= 4 if is_noma else True if is_oov else seg in cands
                if ok and not fwd[i + 1][j + k]:
                    fwd[i + 1][j + k] = True
                    fb[i + 1][j + k]  = (i, j)

    if fwd[n][r]:
        return None  # 完全成功，交 _dp_split 处理

    # ── 反向 DP ──────────────────────────────────────────────────
    bwd = [[False] * (r + 1) for _ in range(n + 1)]
    bwd[n][r] = True
    for i in range(n - 1, -1, -1):
        ch    = surface[i]
        cands = _lookup_readings_with_voiced(ch)
        is_noma = ch == _NOMA
        is_oov  = not cands and not is_noma
        for j1 in range(r + 1):
            if not bwd[i + 1][j1]:
                continue
            for k in range(1, min(j1, 8) + 1):
                seg = reading[j1 - k: j1]
                ok  = k <= 4 if is_noma else True if is_oov else seg in cands
                if ok and not bwd[i][j1 - k]:
                    bwd[i][j1 - k] = True

    # ── 正向最远可达 i_fwd（至少 2 步才能确认左边第 1 字）──────────
    i_fwd, j_fwd = 0, 0
    for i in range(n, 0, -1):
        for j in range(r, -1, -1):
            if fwd[i][j]:
                i_fwd, j_fwd = i, j
                break
        if i_fwd:
            break

    # ── 反向最左可达 i_bwd（至少 2 步才能确认右边最后 1 字）─────────
    i_bwd = n  # 默认：无反向进展
    for i in range(0, n):
        if any(bwd[i][j] for j in range(r + 1)):
            i_bwd = i
            break

    # 保守边界
    left_end    = max(0, i_fwd - 1)   # 左前缀字符数（排他上界）
    right_start = min(n, i_bwd + 1)   # 右后缀起始（包含）

    if left_end == 0 and right_start == n:
        return None  # 两侧均无可确认字符

    # 两侧重叠时取覆盖更多的一侧
    if left_end >= right_start:
        if i_fwd >= n - i_bwd:
            right_start = n
        else:
            left_end = 0

    # ── 求 j_left：正向 DP 在 left_end 处消耗的读音偏移 ──────────
    j_left = 0
    if left_end > 0:
        ci, cj = i_fwd, j_fwd
        while ci > left_end:
            entry = fb[ci][cj]
            if entry is None:
                break
            ci, cj = entry
        j_left = cj

    # ── 求 j_right：反向 DP 在 right_start 处的读音偏移 ──────────
    j_right = r
    if right_start < n:
        found = next(
            (j for j in range(j_left, r + 1) if bwd[right_start][j]),
            None
        )
        if found is None:
            right_start = n  # 无法对齐，放弃右侧
        else:
            j_right = found

    # ── 组建结果 ─────────────────────────────────────────────────
    result: list[tuple[str, str]] = []

    # 左前缀（逐字回溯）
    if left_end > 0:
        prefix: list[tuple[str, str]] = []
        ci, cj = left_end, j_left
        while ci > 0:
            entry = fb[ci][cj]
            if entry is None:
                break
            pi, pj = entry
            prefix.append((surface[pi], reading[pj:cj]))
            ci, cj = pi, pj
        prefix.reverse()
        result.extend(prefix)

    # 中间块（未能确认的部分整块保留）
    if right_start > left_end:
        result.append((surface[left_end:right_start], reading[j_left:j_right]))

    # 右后缀（尝试 DP 逐字拆分）
    if right_start < n:
        suf_s = surface[right_start:]
        suf_r = reading[j_right:]
        suf   = _dp_split(suf_s, suf_r)
        result.extend(suf if suf else [(suf_s, suf_r)])

    return result if len(result) >= 2 else None


def _split_kanji_block(block_surface: str, block_reading: str) -> list[CharAnnotation]:
    if len(block_surface) == 1:
        return [(block_surface, block_reading if block_reading else None)]

    # ── 々 专用：等长约束组级 DP，失败则整块输出 ─────────────────────
    if _NOMA in block_surface:
        result = _try_noma_split(block_surface, block_reading)
        if result is not None:
            return result
        return [(block_surface, block_reading if block_reading else None)]

    # ── 策略1：fugashi 重新切块 ────────────────────────────────────
    # 1a: 每个 token 恰好 1 字且读音拼合匹配 → 直接采用
    # 1b: 存在多字 token 但读音拼合仍匹配 → 递归拆分各子 token
    #     （处理如 行方不明：fugashi 给出 行方[ゆくえ]+不明[ふめい]，
    #       方→え 不在 KANJIDIC2 导致 DP 失败，但子段 不明 可以继续拆）
    sub_tokens: list[tuple[str, str]] = []
    try:
        for w in _tagger(block_surface):
            sub_surf = w.surface
            sub_read = _kata2hira(_get_reading(w))
            sub_tokens.append((sub_surf, sub_read))

        if sub_tokens:
            joined = ''.join(r for _, r in sub_tokens if r)
            if joined == block_reading:
                all_single = all(len(s) == 1 for s, _ in sub_tokens)
                if all_single:
                    # 1a: 全单字，直接输出
                    return [
                        (s, r if (_is_target(s) and r) else None)
                        for s, r in sub_tokens
                    ]
                elif len(sub_tokens) >= 2:
                    # 1b: 含多字子 token，递归拆分每段
                    result: list[CharAnnotation] = []
                    for s, r in sub_tokens:
                        result.extend(_split_kanji_block(s, r))
                    return result
    except Exception:
        pass

    # ── 策略2：DP 对齐 ────────────────────────────────────────────
    dp_result = _dp_split(block_surface, block_reading)
    if dp_result is not None:
        return [(ch, rd) for ch, rd in dp_result]

    # ── 策略2.5：jamdict 标准读音兜底 ────────────────────────────
    # 处理 UniDic 口语化/缩略读音导致 DP 失败的情况（如 本当→ホント 而非 ホントウ）
    jmd_read = _jmd_reading(block_surface)
    if jmd_read is not None:
        jmd_hira = _kata2hira(jmd_read)
        if jmd_hira != block_reading:
            dp2 = _dp_split(block_surface, jmd_hira)
            if dp2 is not None:
                return [(ch, rd) for ch, rd in dp2]

    # ── 策略2.7：保守部分 DP ─────────────────────────────────────
    # DP 推进到 i_max 后卡住：只确认前 i_max-1 个字符，其余整块保留。
    # 如赤提灯：DP 推到"提"后在"灯"卡住 → 只确认"赤"，"提灯"整块。
    partial = _dp_split_partial(block_surface, block_reading)
    if partial is not None:
        out: list[CharAnnotation] = []
        for s, r in partial:
            out.extend(_split_kanji_block(s, r))
        return out

    # ── 策略3：整块 ───────────────────────────────────────────────
    return [(block_surface, block_reading if block_reading else None)]


def _fallback_whole(surface: str, reading: str) -> list[CharAnnotation]:
    all_target = all(_is_target(c) for c in surface)
    if all_target:
        dp = _dp_split(surface, reading)
        if dp:
            return [(ch, rd) for ch, rd in dp]
        return [(surface, reading)]

    result: list[CharAnnotation] = []
    i = 0
    r_pos = 0
    while i < len(surface):
        ch = surface[i]
        if not _is_target(ch):
            result.append((ch, None))
            hira = _kata2hira(ch)
            if r_pos < len(reading) and reading[r_pos] == hira:
                r_pos += 1
            i += 1
            continue
        j = i
        while j < len(surface) and _is_target(surface[j]):
            j += 1
        kanji_seg = surface[i:j]
        remaining = reading[r_pos:]
        if j < len(surface):
            next_hira = _kata2hira(surface[j])
            anchor    = remaining.find(next_hira)
            if anchor != -1:
                seg_read = remaining[:anchor]
                r_pos   += anchor
            else:
                seg_read = remaining
                r_pos    = len(reading)
        else:
            seg_read = remaining
            r_pos    = len(reading)

        result.extend(_split_kanji_block(kanji_seg, seg_read))
        i = j

    return result


def _apply_user_entry(surface: str, entry: UserEntry) -> list[CharAnnotation]:
    """将用户词典条目应用到 surface，返回逐字（或成组）标注列表。"""
    reading = entry.reading

    # ── 无切分规格：走 DP 对齐，事后按 k 标志决定是否转回片假名 ──
    if entry.seg is None:
        anns = _process_morpheme(surface, reading)
        if ''.join(a[0] for a in anns) != surface:
            anns = [(ch, None) for ch in surface]
        if entry.katakana:
            anns = [(ch, _hira2kata(rd) if rd else None) for ch, rd in anns]
        return anns

    # ── 有切分规格：前置校验，冲突则整体成组 ──
    def _seg_fallback() -> list[CharAnnotation]:
        rd = reading if entry.katakana else _kata2hira(reading)
        return [(surface, rd if rd else None)]

    def _part_len(p: str) -> int:
        """seg 片段消耗的读音字符数：纯数字直接解析，假名/汉字串取字符串长度。"""
        try:
            return int(p)
        except ValueError:
            return len(p)

    try:
        has_g = any(p.lower() == "g" for p in entry.seg)
        non_g_parts = [p for p in entry.seg if p.lower() != "g"]
        part_counts = [_part_len(p) for p in non_g_parts]
        # 无 g 时：字段数必须等于表层字符数，且读音字符数之和必须等于读音长度
        if not has_g:
            if len(part_counts) != len(surface):
                return _seg_fallback()
            if sum(part_counts) != len(reading):
                return _seg_fallback()
        # 有 g 时：g 之前的字段数 + 1（g 本身）不超过表层字符数，数字之和不超过读音长度
        else:
            g_idx = next(i for i, p in enumerate(entry.seg) if p.lower() == "g")
            pre_counts = [_part_len(p) for p in entry.seg[:g_idx]]
            if len(pre_counts) >= len(surface):
                return _seg_fallback()
            if sum(pre_counts) >= len(reading):
                return _seg_fallback()
    except StopIteration:
        return _seg_fallback()

    # ── 按规格逐段分配读音 ──
    result: list[CharAnnotation] = []
    s_pos = 0   # 当前处理到 surface 的位置
    r_pos = 0   # 当前处理到 reading 的位置

    for part in entry.seg:
        if s_pos >= len(surface):
            break
        if part.lower() == "g":
            # 将剩余所有表层字符整体成组，读音取剩余全部
            surf_chunk = surface[s_pos:]
            read_chunk = reading[r_pos:]
            rd = read_chunk if entry.katakana else _kata2hira(read_chunk)
            result.append((surf_chunk, rd if rd else None))
            s_pos = len(surface)
            r_pos = len(reading)
            break
        else:
            n = _part_len(part)
            char = surface[s_pos]
            read_chunk = reading[r_pos:r_pos + n]
            rd = read_chunk if entry.katakana else _kata2hira(read_chunk)
            # 假名表层字符不加标注（无论 seg 如何指定）
            if not _is_target(char):
                result.append((char, None))
            else:
                result.append((char, rd if rd else None))
            s_pos += 1
            r_pos += n

    # 规格未覆盖的剩余部分（规格偏短时兜底）
    if s_pos < len(surface):
        surf_chunk = surface[s_pos:]
        read_chunk = reading[r_pos:]
        rd = read_chunk if entry.katakana else _kata2hira(read_chunk)
        result.append((surf_chunk, rd if rd else None))

    return result


def _split_by_user_dict(text: str) -> list[tuple[str, UserEntry | None]]:
    """
    按用户词典最长优先扫描文本，返回片段列表。
    每项为 (surface, entry)：entry 为 None 时交由 fugashi 处理。
    """
    if not _USER_ENTRIES:
        return [(text, None)]
    max_len = max(len(k) for k in _USER_ENTRIES)
    result: list[tuple[str, UserEntry | None]] = []
    i = 0
    n = len(text)
    buf_start = 0
    while i < n:
        matched_len = 0
        matched_entry: UserEntry | None = None
        for length in range(min(n - i, max_len), 0, -1):
            word = text[i:i + length]
            if word in _USER_ENTRIES:
                matched_len = length
                matched_entry = _USER_ENTRIES[word]
                break
        if matched_len:
            if i > buf_start:
                result.append((text[buf_start:i], None))
            result.append((text[i:i + matched_len], matched_entry))
            i += matched_len
            buf_start = i
        else:
            i += 1
    if buf_start < n:
        result.append((text[buf_start:], None))
    return result


def _annotate(text: str) -> list[CharAnnotation]:
    if not text:
        return []
    result: list[CharAnnotation] = []
    for surface, user_entry in _split_by_user_dict(text):
        if user_entry is not None:
            anns = _apply_user_entry(surface, user_entry)
            if ''.join(a[0] for a in anns) != surface:
                anns = [(ch, None) for ch in surface]
            result.extend(anns)
        else:
            # fugashi 分词 → 按词性收集连续名词串 → jamdict 最长匹配复合词
            tokens = list(_tagger(surface))
            i = 0
            while i < len(tokens):
                # 收集从 i 开始的连续名词语素
                noun_surfaces: list[str] = []
                noun_words: list  = []
                j = i
                while j < len(tokens):
                    w = tokens[j]
                    try:
                        pos1  = w.feature.pos1
                        cForm = getattr(w.feature, 'cForm', '') or ''
                    except AttributeError:
                        pos1 = cForm = ''
                    # 名詞・接頭辞（赤提灯の「赤」など色・修飾前缀）・
                    # 接尾辞（千代紙の「紙」など連浊后缀）・動詞連用形
                    is_noun   = pos1 == '名詞'
                    is_prefix = pos1 == '接頭辞'
                    is_suffix = pos1 == '接尾辞'
                    is_ren_yo = pos1 == '動詞' and cForm.startswith('連用形')
                    # 接頭辞は链首のみ許可（孤立した接頭辞で誤結合しないよう、
                    # 既に名詞/接尾辞/連用形が入っている途中には接頭辞を継続しない）
                    can_extend = is_noun or is_suffix or is_ren_yo or (
                        is_prefix and len(noun_surfaces) == 0
                    )
                    if can_extend:
                        noun_surfaces.append(w.surface)
                        noun_words.append(w)
                        j += 1
                    else:
                        break

                if len(noun_surfaces) >= 2:
                    # 对名词串做 jamdict 驱动的最长匹配切分
                    segments = _jmd_segment_nouns(noun_surfaces)
                    word_idx = 0
                    for seg_surf, seg_read in segments:
                        # 精确计算该 segment 覆盖的 token 数
                        acc, cnt = '', 0
                        for k in range(word_idx, len(noun_surfaces)):
                            acc += noun_surfaces[k]
                            cnt += 1
                            if acc == seg_surf:
                                break
                        if seg_read is not None:
                            anns = _process_morpheme(seg_surf, seg_read)
                            if ''.join(a[0] for a in anns) != seg_surf:
                                anns = [(ch, None) for ch in seg_surf]
                        else:
                            # jamdict 未命中：对该段内各 token 用 fugashi 读音
                            anns = []
                            for w in noun_words[word_idx:word_idx + cnt]:
                                ws = w.surface
                                rk = _get_reading(w)
                                wa = _process_morpheme(ws, rk)
                                if ''.join(a[0] for a in wa) != ws:
                                    wa = [(ch, None) for ch in ws]
                                anns.extend(wa)
                        result.extend(anns)
                        word_idx += cnt
                elif len(noun_surfaces) == 1:
                    # 单个名词，直接 fugashi（含前后文修正）
                    w = noun_words[0]
                    ws = w.surface
                    prev_tok = tokens[i - 1] if i > 0 else None
                    next_tok = tokens[j] if j < len(tokens) else None
                    rk = _correct_reading_by_context(w, prev_tok, next_tok)
                    anns = _process_morpheme(ws, rk)
                    if ''.join(a[0] for a in anns) != ws:
                        anns = [(ch, None) for ch in ws]
                    result.extend(anns)

                if j > i:
                    i = j  # 跳过已处理的名词串
                else:
                    # 非名词 token，直接处理
                    w = tokens[i]
                    ws = w.surface
                    rk = _get_reading(w)
                    anns = _process_morpheme(ws, rk)
                    if ''.join(a[0] for a in anns) != ws:
                        anns = [(ch, None) for ch in ws]
                    result.extend(anns)
                    i += 1
    return result


# ──────────────────────────────────────────────────────────────
# 公共 API
# ──────────────────────────────────────────────────────────────
def add_furigana(text: str, mode: str = "html"):
    """
    为文本添加振假名。

    Parameters
    ----------
    text : str   输入日文文本
    mode : str
        "html"  → <ruby>漢字<rt>よみ</rt></ruby>
        "anki"  → 漢字[よみ]
        "json"  → list[ [字符串, 読み] ]
    """
    annotations = _annotate(text)

    if mode == "html":
        parts = []
        for char, reading in annotations:
            if reading is None:
                parts.append(char)
            else:
                parts.append(f"<ruby>{char}<rt>{reading}</rt></ruby>")
        return ''.join(parts)

    elif mode == "anki":
        parts = []
        for char, reading in annotations:
            if reading is None:
                parts.append(char)
            else:
                parts.append(f"{char}[{reading}]")
        return ''.join(parts)

    elif mode == "json":
        return [[char, reading if reading is not None else '']
                for char, reading in annotations]

    else:
        raise ValueError(f"Unknown mode: {mode!r}")


# ──────────────────────────────────────────────────────────────
# 测试
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("基础",        "天気がいいから、散歩しましょう！"),
        ("逐字·牛乳",   "牛乳を毎日飲む。"),
        ("逐字·東京都", "東京都に住んでいる。"),
        ("Bug1·休憩",   "スーパーで牛乳と煙草を買った後、時計を見て一寸だけ休憩した。"),
        ("Bug2·五分咲", "今日は五分咲きの桜がとても綺麗で、大人の私も子供のように嬉しくなった。"),
        ("Bug3·私",     "大人の私も子供のように嬉しくなった。"),
        ("Bug4·明日",   "時々、明日のことを考える。"),
        ("のま号·生々", "先生が「生々しい話はもう止めてくれ」と言った。"),
        ("送假名",      "秋の紅葉が美しい山道を上り下りしながら昔のことを思い出した。"),
        ("综合",        "田舎から来た仲間が、土産に葡萄と眼鏡を持ってきてくれた。"),
        ("综合",        "生まれたばかりの息子が、行方不明になった父親の写真を握りしめて泣いている。"),
        ("促音便",        "毎朝、学校に行って勉強します。"),
        ("促音便",        "彼は来年結婚するそうです。"),
        ("促音便",        "切手を買って、手紙を出しました。"),
        ("语法",        "彼の言葉通り、本当に雨が降ってきた。"),
        ("语法",        "青い空に飛行機雲"),
        ("语法",        "飛行機雲"),
        ("语法",        "仕事が思い通りにならない。"),
        ("语法",        "絵本や千代紙の本を引っ張り出した"),
        ("语法",        "大将のさりげない気遣いが身に染み"),
        ("语法",        "本当にできません。"),
        ("送假名",        "茹でカボチャ入りの黄色い生地も作る。"),
        ("语法",        "その後、私は駅前の人込みを抜けて、赤提灯の誘う居酒屋へ。"),
        ("送假名",        "どんよりとした青空の下、私は雨傘を差し、長靴を履いて家路を急いでいた。"),
    ]

    print("=" * 80)
    print("gen_rubi_fugashi2 — fugashi + UniDic + KANJIDIC2 DP")
    print("=" * 80)

    for label, sent in tests:
        anki  = add_furigana(sent, "anki")
        jlist = add_furigana(sent, "json")
        reconstructed = ''.join(item[0] for item in jlist)
        print(f"\n[{label}] {sent}")
        print(f"  Anki : {anki}")
        print(f"  JSON : {json.dumps(jlist, ensure_ascii=False)}")
        print(add_furigana(sent, "html"))
        print("-" * 60)
