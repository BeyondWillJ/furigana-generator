from sudachipy import tokenizer
from sudachipy import dictionary as sudachi_dictionary
from jamdict import Jamdict

# ==================== 初始化 ====================
print("正在初始化 Sudachi 和 jamdict，请稍候...")

sudachi_dic = sudachi_dictionary.Dictionary(dict_type='full')
sudachi_tok = sudachi_dic.create()
jmd = Jamdict()          # jamdict 会自动加载数据库

print("初始化完成！\n")


def get_reading(text: str) -> str:
    """
    输入日语文本，返回复合词的正确读音（优先使用词典数据）
    """
    # 1. 使用 Sudachi 进行最长匹配分词
    mode = tokenizer.Tokenizer.SplitMode.A
    tokens = sudachi_tok.tokenize(text, mode)
    
    # 获取表层形（用于查 jamdict）
    surfaces = [token.surface() for token in tokens]
    full_surface = ''.join(surfaces)
    
    # 2. 用 jamdict 查询完整复合词
    result = jmd.lookup(full_surface)
    
    if result.entries:
        # 找到词条，使用词典里的读音（已包含正确连浊）
        entry = result.entries[0]
        if entry.kana_forms:
            # 返回第一个假名形式
            return str(entry.kana_forms[0])
        else:
            # 极少数情况词条没有假名形式
            readings = [token.reading_form() for token in tokens]
            return ''.join(readings)
    else:
        # 3. jamdict 查不到时，回退到 Sudachi 的读音拼接（不做任何手动连浊处理）
        readings = [token.reading_form() for token in tokens]
        return ''.join(readings)


# ==================== 测试 ====================
if __name__ == "__main__":
    test_words = [
        "飛行機雲",
        "手紙",
        "花火",
        "春風",
        "縄梯子",
        "言葉通り",
        "気遣い",
        "心の灯火",
        "赤提灯",
    ]
    
    for word in test_words:
        reading = get_reading(word)
        print(f"{word} → {reading}")