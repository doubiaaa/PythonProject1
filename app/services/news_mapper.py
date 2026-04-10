# -*- coding: utf-8 -*-
"""
要闻与盘面关联映射：将外部要闻与潜在受益板块做自动匹配
"""

from typing import List, Dict, Any, Optional
import re

# 关键词映射规则
NEWS_KEYWORD_MAPPINGS = {
    # 航天/卫星
    "NASA": ["卫星通信", "航天军工", "商业航天"],
    "发射": ["卫星通信", "航天军工", "商业航天"],
    "卫星": ["卫星通信", "航天军工", "北斗导航"],
    "航天": ["航天军工", "商业航天", "卫星通信"],
    "火箭": ["航天军工", "商业航天"],
    
    # 货币政策
    "加息": ["银行", "保险", "高股息", "防御性板块"],
    "降息": ["房地产", "券商", "科技成长", "高负债"],
    "降准": ["银行", "房地产", "券商"],
    "美联储": ["银行", "保险", "外贸", "汇率敏感"],
    "货币政策": ["银行", "券商", "房地产"],
    
    # 汇率/外贸
    "贬值": ["出口", "外贸", "纺织", "电子", "汽车零部件"],
    "升值": ["进口", "航空", "造纸", "外债"],
    "汇率": ["外贸", "出口", "进口"],
    "韩元": ["中韩贸易", "电子", "汽车零部件", "化妆品"],
    "日元": ["中日贸易", "汽车零部件", "电子", "机械"],
    "美元": ["外贸", "出口", "汇率敏感"],
    
    # 能源
    "原油": ["石油", "化工", "交通运输", "航空"],
    "石油": ["石油开采", "石油化工", "油服"],
    "天然气": ["燃气", "能源", "化工"],
    "新能源": ["光伏", "风电", "储能", "锂电池"],
    "碳中和": ["光伏", "风电", "储能", "环保", "新能源汽车"],
    
    # 科技
    "AI": ["人工智能", "算力", "芯片", "应用端"],
    "人工智能": ["AI", "算力", "芯片", "应用端"],
    "芯片": ["半导体", "集成电路", "光刻机", "国产替代"],
    "半导体": ["芯片", "集成电路", "国产替代"],
    "5G": ["通信", "基站", "光模块", "运营商"],
    "6G": ["通信", "卫星通信", "太赫兹"],
    
    # 政策/会议
    "两会": ["政策受益", "基建", "民生", "环保"],
    "政策": ["政策受益", "基建", "地产", "科技"],
    "基建": ["建筑", "建材", "工程机械", "钢铁"],
    "房地产": ["地产", "建材", "家电", "银行"],
    
    # 消费
    "消费": ["食品饮料", "家电", "汽车", "零售"],
    "促销费": ["零售", "汽车", "家电", "文旅"],
    "旅游": ["文旅", "酒店", "航空", "餐饮"],
    "节假日": ["文旅", "零售", "餐饮", "交通"],
    
    # 医药
    "疫情": ["医药", "疫苗", "医疗器械", "防护用品"],
    "病毒": ["医药", "疫苗", "检测", "防护用品"],
    "医保": ["医药", "医疗器械", "创新药"],
    
    # 资源
    "黄金": ["贵金属", "有色", "避险"],
    "铜": ["有色", "工业金属", "电力"],
    "锂": ["锂电池", "新能源", "有色"],
    "稀土": ["稀土永磁", "有色", "战略资源"],
    
    # 军工
    "军事": ["军工", "国防", "武器装备"],
    "冲突": ["军工", "黄金", "石油", "避险"],
    "战争": ["军工", "黄金", "石油", "粮食", "避险"],
    "地缘政治": ["军工", "黄金", "石油", "粮食"],
}


def map_news_to_sectors(news_text: str) -> List[Dict[str, Any]]:
    """
    将新闻文本映射到潜在受益板块
    
    Args:
        news_text: 新闻文本内容
        
    Returns:
        匹配结果列表，每项包含关键词和对应板块
    """
    if not news_text:
        return []
    
    results = []
    matched_keywords = set()
    
    for keyword, sectors in NEWS_KEYWORD_MAPPINGS.items():
        # 使用正则表达式匹配关键词（忽略大小写）
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        if pattern.search(news_text):
            if keyword not in matched_keywords:
                matched_keywords.add(keyword)
                results.append({
                    'keyword': keyword,
                    'sectors': sectors,
                    'context': _extract_context(news_text, keyword)
                })
    
    return results


def _extract_context(text: str, keyword: str, context_length: int = 30) -> str:
    """提取关键词周围的上下文"""
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    match = pattern.search(text)
    if match:
        start = max(0, match.start() - context_length)
        end = min(len(text), match.end() + context_length)
        return text[start:end].strip()
    return ""


def format_news_mapping_markdown(mappings: List[Dict[str, Any]]) -> str:
    """
    将新闻映射结果格式化为 Markdown
    
    Args:
        mappings: map_news_to_sectors 的返回结果
        
    Returns:
        Markdown 格式的字符串
    """
    if not mappings:
        return ""
    
    lines = ["\n### 【要闻映射】\n"]
    lines.append("基于关键词匹配，外部要闻与潜在受益板块关联如下：\n")
    
    for item in mappings:
        keyword = item['keyword']
        sectors = "、".join(item['sectors'])
        lines.append(f"- **{keyword}** → 关注板块：{sectors}\n")
    
    lines.append("\n> *注：以上映射基于关键词规则匹配，仅供参考，不构成投资建议。*\n")

    return "".join(lines)


def _norm_code6(c: object) -> str:
    return re.sub(r"[^0-9]", "", str(c))[:6].zfill(6)


def format_pool_news_hits_markdown(
    news_list: List[str],
    top_pool: Optional[List[Dict[str, Any]]],
) -> str:
    """快讯正文中字面命中「次日竞价」程序龙头池代码/名称时单列，便于短线对照。"""
    if not news_list or not top_pool:
        return ""
    codes = {_norm_code6(p.get("code")) for p in top_pool if p.get("code")}
    codes.discard("000000")
    names = sorted(
        {str(p.get("name") or "").strip() for p in top_pool if p.get("name")},
        key=len,
        reverse=True,
    )
    lines_out: list[str] = []
    seen_snip: set[str] = set()
    for news in news_list:
        text = str(news or "")
        if not text.strip():
            continue
        hit_keys: list[str] = []
        for c in codes:
            if len(c) == 6 and c in text:
                hit_keys.append(c)
        for nm in names:
            if len(nm) >= 2 and nm in text:
                hit_keys.append(nm)
        if not hit_keys:
            continue
        dedup: list[str] = []
        for h in hit_keys:
            if h not in dedup:
                dedup.append(h)
        snip = text.strip()[:160].replace("\n", " ")
        if snip in seen_snip:
            continue
        seen_snip.add(snip)
        lines_out.append(
            f"- **命中** {' / '.join(dedup[:6])}：{snip}{'…' if len(text) > 160 else ''}\n"
        )
        if len(lines_out) >= 14:
            break
    if not lines_out:
        return ""
    return (
        "\n### 【要闻·命中程序龙头池】\n"
        "> 以下为快讯摘要与 **程序龙头池** 代码/名称的 **字面匹配**；"
        "同名或片段重合可能误判，须结合正文。\n\n"
        + "".join(lines_out)
        + "\n"
    )


def analyze_finance_news(
    news_list: List[str],
    top_pool: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    分析财经新闻列表，生成板块映射报告；可选叠加龙头池字面命中。
    """
    if not news_list:
        return ""

    all_mappings = []
    for news in news_list:
        mappings = map_news_to_sectors(news)
        all_mappings.extend(mappings)

    seen_keywords = set()
    unique_mappings = []
    for mapping in all_mappings:
        if mapping["keyword"] not in seen_keywords:
            seen_keywords.add(mapping["keyword"])
            unique_mappings.append(mapping)

    base = format_news_mapping_markdown(unique_mappings)
    return base + format_pool_news_hits_markdown(news_list, top_pool)


# 手动填写区域模板
MANUAL_NEWS_MAPPING_TEMPLATE = """
### 【要闻映射】

**自动匹配结果**：{auto_result}

**手动补充区域**（若自动匹配不完整，可在此补充）：
- 新闻要点：__________
- 关注板块：__________
- 逻辑说明：__________

> *提示：关键词匹配规则包括：NASA/发射/卫星→航天军工；加息/降息→银行/地产；贬值→出口；AI/芯片→科技成长等。*
"""
