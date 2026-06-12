#!/usr/bin/env python3
"""
kanjidic_full.py  - 修正版
KANJIDIC2 完整信息提取器
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Dict


@dataclass
class KanjiEntry:
    literal: str
    on_readings: List[str] = field(default_factory=list)
    kun_readings: List[str] = field(default_factory=list)
    meanings: List[str] = field(default_factory=list)
    stroke_count: Optional[int] = None
    radical: Optional[str] = None
    frequency: Optional[int] = None
    jlpt: Optional[int] = None


class KanjidicFull:
    def __init__(self, xml_path: str = "kanjidic2.xml"):
        self.xml_path = Path(xml_path)
        self.entries: Dict[str, KanjiEntry] = {}
        self._load()

    def _load(self):
        if not self.xml_path.exists():
            raise FileNotFoundError(f"找不到文件: {self.xml_path}")

        print(f"[Kanjidic] 正在加载完整词典 {self.xml_path} ...")
        tree = ET.parse(self.xml_path)
        root = tree.getroot()

        for char in root.findall("character"):
            literal_elem = char.find("literal")
            if literal_elem is None or not literal_elem.text:
                continue

            literal = literal_elem.text
            entry = KanjiEntry(literal=literal)

            # === 读音 + 意思（正确路径）===
            rm = char.find("reading_meaning")
            if rm is not None:
                rmgroup = rm.find("rmgroup")
                if rmgroup is not None:
                    for r in rmgroup.findall("reading"):
                        r_type = r.get("r_type")
                        if r.text:
                            if r_type == "ja_on":
                                entry.on_readings.append(r.text)
                            elif r_type == "ja_kun":
                                entry.kun_readings.append(r.text)

                    for m in rmgroup.findall("meaning"):
                        if m.get("m_lang") in (None, "en") and m.text:
                            entry.meanings.append(m.text)

            # === 笔画数、常用度 ===
            misc = char.find("misc")
            if misc is not None:
                sc = misc.findtext("stroke_count")
                if sc:
                    entry.stroke_count = int(sc)
                freq = misc.findtext("freq")
                if freq:
                    entry.frequency = int(freq)

            # === 部首 ===
            radical = char.find("radical")
            if radical is not None:
                val = radical.findtext("value")
                if val:
                    entry.radical = val

            # === JLPT ===
            jlpt = char.findtext("jlpt")
            if jlpt:
                entry.jlpt = int(jlpt)

            self.entries[literal] = entry

        print(f"[Kanjidic] 加载完成，共 {len(self.entries)} 个汉字")

    @lru_cache(maxsize=8192)
    def lookup(self, kanji: str) -> Optional[KanjiEntry]:
        return self.entries.get(kanji)

    def get_readings(self, kanji: str) -> Dict[str, List[str]]:
        entry = self.lookup(kanji)
        if not entry:
            return {"on": [], "kun": []}
        return {"on": entry.on_readings, "kun": entry.kun_readings}


# 全局单例
_kanjidic = None

def get_kanjidic(xml_path: str = "kanjidic2.xml") -> KanjidicFull:
    global _kanjidic
    if _kanjidic is None:
        _kanjidic = KanjidicFull(xml_path)
    return _kanjidic


if __name__ == "__main__":
    kd = get_kanjidic("kanjidic2.xml")

    test_chars = ["日", "本", "咲", "一", "寸", "子", "供", "桜", "大", "人", "分","赤","提","灯"]
    for k in test_chars:
        entry = kd.lookup(k)
        if entry:
            print(f"{k}:")
            print(f"  音读: {entry.on_readings}")
            print(f"  训读: {entry.kun_readings}")
            print(f"  意思: {entry.meanings[:3]}")
            print(f"  笔画: {entry.stroke_count}")
            print("-" * 50)