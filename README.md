# gen_rubi_fugashi2 — 振假名标注器

为日文文本自动添加振假名（ふりがな）。分词由 **fugashi + UniDic** 完成，汉字逐字对齐由 **KANJIDIC2 驱动的动态规划**完成，复合词连浊修正由 **jamdict** 补充。

[![GitHub release](https://img.shields.io/github/v/release/BeyondWillJ/furigana-generator?color=7ac1eb&label=version)](https://github.com/BeyondWillJ/furigana-generator/releases/latest)
[![GitHub all releases](https://img.shields.io/github/downloads/BeyondWillJ/furigana-generator/total?color=95a5a6&label=downloads)](https://github.com/BeyondWillJ/furigana-generator/releases)

---

## 依赖安装

```bash
pip install fugashi unidic-lite   # 或 unidic（完整版）
pip install jamdict               # 可选，用于名词复合词连浊修正
```

运行前需在脚本同目录放置 `kanjidic2.xml`（KANJIDIC2 数据库）。

---

## 快速使用

```python
from gen_rubi_fugashi2 import add_furigana

add_furigana("東京都に住んでいる。", mode="html")
# <ruby>東<rt>とう</rt></ruby><ruby>京<rt>きょう</rt></ruby><ruby>都<rt>と</rt></ruby>に住んでいる。

add_furigana("東京都に住んでいる。", mode="anki")
# 東[とう]京[きょう]都[と]に住んでいる。

add_furigana("東京都に住んでいる。", mode="json")
# [["東","とう"], ["京","きょう"], ["都","と"], ["に",""], ...]
```

---

## `add_furigana()` 原理与流程

### 总览

```
输入文本
  │
  ▼
① 用户词典最长优先扫描（_split_by_user_dict）
  │  命中 → ② 用户词典标注（_apply_user_entry）
  │  未命中 → ③ fugashi 分词 → 名词串聚合 → jamdict 复合词分段
  │                           → _process_morpheme（单 token 处理）
  ▼
④ 逐字标注列表 CharAnnotation[]  [(字符, 读音|None), ...]
  │
  ▼
⑤ 格式化输出（html / anki / json）
```

---

### 第一步：用户词典扫描

`_split_by_user_dict(text)` 对输入文本执行**最长优先匹配**扫描：

- 词典条目来自 `rubi_dict.csv`，启动时由 `_load_user_dict()` 一次性加载为 `dict[surface, UserEntry]`。
- 从左到右扫描，每个位置从最长候选向短尝试，命中则切出一段并附带对应 `UserEntry`，未命中的区间标记为 `None`（交给 fugashi）。

#### 用户词典格式（rubi_dict.csv）

```
表层形式,片假名读音[,k][,切分规格]
```

- `k / K`：振假名保持片假名输出（不转为平假名）
- 切分规格（`|` 分隔）：
  - 数字 `n`：该表层字符对应读音中消耗 `n` 个假名字符
  - `g / G`：将剩余所有表层字符整体成组，读音取剩余全部
  - 假名切分写法 `ソ|ノ|アト`：每段直接是对应字符的读音（假名表层字符自动不标注）
- 示例：`東京都,トウキョウト,,2|g` → 東[トウ] 京都[キョウト]

---

### 第二步：用户词典条目标注

`_apply_user_entry(surface, entry)` 将命中条目转换为逐字标注：

- **无切分规格**：调用与 fugashi 路径相同的 `_process_morpheme()`，再按 `k` 标志决定是否还原为片假名。
- **有切分规格**：先做前置校验（字段数/读音字符数之和必须吻合），不符则整块输出兜底；校验通过后按规格逐字或分组分配读音。

---

### 第三步：fugashi 分词与名词串处理

对用户词典未命中的文本片段，`_annotate()` 调用 fugashi tagger 进行分词，然后：

1. **收集连续名词串**：收集词性为 `名詞`、`接尾辞`、`動詞連用形` 的连续 token，组成名词串。
2. **jamdict 复合词分段**（`_jmd_segment_nouns`）：
   - **全量扫描**：对串内所有 `(i, j)` 位置组合（长度 ≥ 2）拼合表层字符并查 jamdict，记录所有命中的复合词读音。不提前停止，确保更长的复合词也被发现。
   - **DP 最优分段**：在所有命中中找覆盖 token 数最多的非重叠分段方案（最大化被复合词整体覆盖的 token 数）。jamdict 未命中的单 token 保留 `reading=None`，回退到 fugashi 读音。
   - 目的：利用 jamdict 的标准读音修正 UniDic 在复合词连浊（如「千代紙→ちよがみ」）上的偏差。
3. **单 token 或分段后的每个段落** 送入 `_process_morpheme()` 进行逐字对齐。

---

### 第四步：单形态素逐字对齐（`_process_morpheme`）

这是核心对齐层，将一个形态素的表层字符串与其读音逐字拆分。

#### 4-1 读音提取（`_get_reading`）

从 fugashi Word 对象同时取 `kana`（字典形读音）和 `pron`（发音形）：
- 两者等长时优先用 `kana`（含正字法「ヅ/ヂ」，且已反映连浊）；
- 长度不同时（口语缩略等）用 `pron`；
- 片假名→平假名转换（`_kata2hira`）后进入后续流程。

#### 4-2 假名锚点切块（`_segment_by_kana_anchors`）

将形态素按**假名字符**切分为若干块：

- 扫描 surface，遇到假名字符时在 reading 中从当前指针 `r_pos` 向后查找该假名，找到位置即为"锚点"。
- `r_pos` 到锚点之间的读音片段归属于前方积累的汉字块；锚点之后继续处理下一段。
- 结果为 `[(block_surface, block_reading), ...]`，假名块 reading 为 `None`，汉字块带读音。

**已知边界问题及修复**：当汉字读音的**首个假名**与紧随其后的送假名相同时（例如「良い」读音 "いい"、「言い」读音 "いい"），`reading.find('い', r_pos)` 会返回 `r_pos` 本身，导致漢字读音片段为空字符串，振假名丢失。

修复方式：在 `find` 后增加判断——若 `found == r_pos` 且 `kanji_buf` 非空（漢字将得到 0 个读音字符，不合理），从 `r_pos + 1` 重新搜索，强制漢字至少消耗 1 个读音字符：

```python
if found == r_pos and kanji_buf:
    found = reading.find(hira_ch, r_pos + 1)
```

> **注**：汉字读音"中间"含送假名字符的情况（如读音 "aいb" 且后续送假名也是 "い"）理论上也存在歧义，但在现实日语词汇中极少触发，且下游 `_split_kanji_block` 的 DP 层可部分纠正。

#### 4-3 汉字块逐字拆分（`_split_kanji_block`）

对每个汉字块，依次尝试以下策略：

**单字块**：直接标注，无需拆分。

**含々的块**（`_try_noma_split`）：
- 将「漢字 + 々...」视为一个"组"，组内每个成员分配**等长**读音片段。
- 例：`生々/なまなま` → 生[なま] 々[なま]；`人々/ひとびと` → 人[ひと] 々[びと]（连浊）。
- 用组级 DP 枚举每组的读音长度 `k`，约束：`k` 对应的片段必须在该字的 KANJIDIC2 读音候选集内（OOV 字放宽约束）。
- 失败则整块输出。

**策略1：fugashi 重切块**：
- 对汉字块单独调用 fugashi 重新分词，得到子 token 列表。
- 若所有子 token 读音拼合后等于块级读音：
  - 1a：全为单字 token → 直接逐字输出。
  - 1b：含多字子 token → 递归调用 `_split_kanji_block` 拆分各子段。

**策略2：KANJIDIC2 驱动的 DP 对齐**（`_dp_split`）：
- 状态：`reachable[i][j]` = 前 `i` 个字符消耗了 `j` 个读音字符是否可达。
- 转移：枚举当前字符 `surface[i]` 消耗 1～8 个读音字符的片段 `reading[j:j+k]`；
  - 若该片段在 KANJIDIC2 中是该字的合法读音（含浊化/半浊化/促音便变体），则允许转移。
  - OOV 字（KANJIDIC2 无记录）放宽为任意长度均可。
  - 々 字最多消耗 4 个假名字符。
- 回溯得到逐字对齐结果。

**策略2.5：jamdict 标准读音兜底**：
- 当 UniDic 给出口语化读音（如「本当→ホント」而非「ホントウ」）导致 DP 失败时，从 jamdict 查标准读音再试一次 DP。

**策略3：整块输出**：所有策略均失败则将整个汉字块作为一个单元，整体标注读音。

#### KANJIDIC2 读音候选集（`_lookup_readings`）

- 音读（on）：直接纳入（片假名→平假名）。
- 训读（kun）：取点号 `.` 前的词干部分；无点号则去掉前后缀标记符 `-`。
- 扩展变体（`_lookup_readings_with_voiced`）：自动生成每个基础读音的**浊化/半浊化**变体（か→が 等）和**促音便**变体（末尾きくちつひふ→っ），覆盖连浊和促音变音现象。

---

### 第五步：格式化输出

`add_furigana()` 将 `_annotate()` 返回的 `[(字符, 读音|None), ...]` 列表格式化：

| mode | 格式 | 示例 |
|------|------|------|
| `html` | `<ruby>字<rt>よみ</rt></ruby>` | `<ruby>東<rt>とう</rt></ruby>` |
| `anki` | `字[よみ]` | `東[とう]` |
| `json` | `[[字, よみ], ...]` | `[["東","とう"],...]` |

reading 为 `None` 的字符（假名、标点等）原样输出，不加标注。

---

## 文件结构

```
test_rubi/
├── gen_rubi_fugashi2.py   # 主程序
├── get_xml.py             # KANJIDIC2 XML 解析器（KanjidicFull 类）
├── kanjidic2.xml          # KANJIDIC2 数据库（需自行下载）
├── rubi_dict.csv          # 用户自定义词典
└── html2png_rubi.py       # HTML 振假名渲染为 PNG（辅助工具）
```

---

## 用户词典自定义

编辑 `rubi_dict.csv` 可覆盖任意词条的读音或切分方式，对程序内部的 fugashi / KANJIDIC2 推断结果具有最高优先级：

```csv
# 人称
私,ワタシ

# 特殊日期词
明日,アシタ

# 外国地名（片假名输出 + 数字切分规格）
太原,タイユアン,k,2|3
東京都,トウキョウト,,2|g
```
