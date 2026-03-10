"""Heuristic scoring for Chinese/Taiwanese-affiliated company detection."""

import re

# ── Common Chinese surnames (romanized, uppercase) ──────────────────────────
# Top ~100 most common Chinese surnames plus alternate romanizations.
CHINESE_SURNAMES = {
    # Pinyin
    "WANG", "LI", "ZHANG", "LIU", "CHEN", "YANG", "ZHAO", "HUANG", "ZHOU",
    "WU", "XU", "SUN", "ZHU", "MA", "HU", "GUO", "LIN", "HE", "GAO",
    "LIANG", "ZHENG", "LUO", "SONG", "XIE", "TANG", "HAN", "CAO", "DENG",
    "FENG", "XIAO", "CHENG", "YUAN", "SHEN", "PENG", "LU", "PAN", "SU",
    "JIANG", "CAI", "JIA", "WEI", "XUE", "YAN", "YE", "YU", "DU", "DAI",
    "XIA", "ZHONG", "TIAN", "FAN", "FANG", "SHI", "YAO", "TAN", "LIAO",
    "ZOU", "XIONG", "JIN", "DUAN", "LEI", "HOU", "LONG", "HAO", "KONG",
    "BAI", "CUI", "KANG", "MAO", "QIU", "QIN", "CHANG", "QIAN",
    "GU", "WAN", "YIN", "GENG", "MIAO", "ZAN", "JI", "GONG",
    "SHAO", "QI", "BI", "DING", "ZUO", "NIU", "LIAN", "WEN", "XING",
    "FU", "REN", "NING", "ZHU", "LANG", "LENG", "SHAN",
    # Two-syllable
    "OUYANG", "SHANGGUAN", "SIMA", "ZHUGE", "DONGFANG", "HUANGFU",
    # Wade-Giles / Cantonese / Taiwanese romanizations
    "WONG", "CHAN", "CHIANG", "CHOU", "TSAI", "TSENG",
    "HSIEH", "HSU", "HSIAO", "CHAO", "TENG", "KUNG", "PAI", "SHIH",
    "CHIOU", "TUNG", "LAI", "TING", "KUO",
    "CHIEN", "CHUANG", "HUNG", "TSOU", "CHEUNG", "LEUNG", "KWONG",
    "TAM", "NG", "CHOW", "FONG", "MOY", "YEE", "HOM", "TOY",
    "SETO", "CHIN", "CHIU", "KWOK", "TSE", "YIP", "LAM", "TAO",
    "CHING", "CHUNG", "YUNG", "WAI", "SIU", "YEUNG",
}

# Surnames that are also common English words — require stricter matching
AMBIGUOUS_SURNAMES = {
    "SUN", "MA", "HE", "LONG", "FAN", "DU", "DAI", "SHI", "AI",
    "CHANG", "LEE", "KONG", "JIN", "WAN", "QI", "CHIN", "CHUNG",
    "FONG", "LAM", "NG", "YEE", "FU", "REN", "WEN",
}

# Professional suffixes that indicate a surname-based firm
FIRM_SUFFIXES = {
    "& ASSOCIATES", "& ASSOC", "LAW", "LAW FIRM", "LAW GROUP",
    "LAW OFFICE", "LAW OFFICES", "PLLC", "P.C.", "PC", "CPA",
    "CONSULTING", "MEDICAL", "DENTAL", "CLINIC", "STUDIO",
    "TECH", "TECHNOLOGY", "ENGINEERING", "ARCHITECTS",
    "GROUP", "ENTERPRISE", "ENTERPRISES", "TRADING",
    "IMPORT", "EXPORT", "RESTAURANT", "KITCHEN", "FOOD",
}

# ── Known Chinese/Taiwanese business hub cities ────────────────────────────
CHINESE_HUB_CITIES = {
    # NYC area
    "FLUSHING", "CHINATOWN", "SUNSET PARK", "ELMHURST", "WOODSIDE",
    "BAYSIDE", "FRESH MEADOWS", "WHITESTONE",
    # LA / San Gabriel Valley
    "MONTEREY PARK", "ALHAMBRA", "ARCADIA", "SAN GABRIEL", "ROWLAND HEIGHTS",
    "TEMPLE CITY", "ROSEMEAD", "EL MONTE", "HACIENDA HEIGHTS", "WALNUT",
    "DIAMOND BAR", "WEST COVINA", "INDUSTRY", "CITY OF INDUSTRY",
    # SF Bay Area
    "CUPERTINO", "MILPITAS", "FREMONT", "SUNNYVALE", "SANTA CLARA",
    # Houston
    "BELLAIRE", "SUGAR LAND", "KATY",
    # NJ
    "EDISON", "FORT LEE", "PALISADES PARK", "PARSIPPANY",
    # Other
    "IRVINE",  # Orange County — large Chinese community
}

# ── Keyword signals in company names ───────────────────────────────────────
CHINESE_KEYWORDS = {
    # Geographic / cultural identifiers
    "SINO", "SINOTECH", "CATHAY", "ORIENT", "ORIENTAL",
    "ASIA PACIFIC", "ASIAPAC",
    "BEIJING", "SHANGHAI", "SHENZHEN", "GUANGZHOU", "NANJING",
    "CHENGDU", "HANGZHOU", "WUHAN", "TIANJIN", "TAIPEI", "TAIWAN",
    "FORMOSA", "HONG KONG", "MACAU", "XIAMEN", "SUZHOU", "QINGDAO",
    "CHINA", "CHINESE",
    # Well-known Chinese/Taiwanese companies
    "HUAWEI", "SINOPEC", "FOXCONN", "LENOVO", "BAIDU", "ALIBABA",
    "TENCENT", "BYTEDANCE", "TIKTOK", "XIAOMI", "OPPO", "VIVO", "BYD",
    "DIDI", "MEITUAN", "PINDUODUO", "WEIBO", "DOUYIN",
    "ZTE", "HAIER", "MIDEA", "GEELY", "GREAT WALL",
    "DAHUA", "HIKVISION", "HUANENG", "CITIC", "COSCO",
    "SINOPAC", "EVERGREEN", "ASUS", "ACER", "TSMC", "MEDIATEK",
    "WISTRON", "PEGATRON", "QUANTA", "COMPAL", "INVENTEC",
    # Common Chinese business name elements
    "MINGHUA", "ZHONGHUA", "XINHUA", "HUAXIN",
}

# Weaker keywords — only add small score boost, need other signals
WEAK_KEYWORDS = {
    "GLOBAL TRADING", "ASIA", "PACIFIC", "EAST WEST", "GOLDEN",
    "INTERNATIONAL TRADING", "IMPORT EXPORT",
}


def _name_words(name: str) -> list[str]:
    """Split a company name into uppercase words, stripping punctuation."""
    return re.findall(r"[A-Z]+", name.upper())


def score_company(employer_name: str, trade_name_dba: str | None,
                  employer_city: str | None) -> int:
    """
    Score a company for Chinese/Taiwanese affiliation likelihood.

    Returns 0-100 score:
        0      — no signals
        1-24   — very weak
        25-49  — maybe (single moderate signal)
        50-100 — likely (strong signal or multiple moderate signals)
    """
    score = 0
    name_upper = (employer_name or "").upper()
    dba_upper = (trade_name_dba or "").upper()
    city_upper = (employer_city or "").upper()
    words = _name_words(name_upper)
    dba_words = _name_words(dba_upper)

    # ── Check for strong Chinese keywords in name or DBA ─────────────
    for kw in CHINESE_KEYWORDS:
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, name_upper) or re.search(pattern, dba_upper):
            score += 50
            break

    # ── Check for weak keywords ──────────────────────────────────────
    if score == 0:
        for kw in WEAK_KEYWORDS:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, name_upper) or re.search(pattern, dba_upper):
                score += 10
                break

    # ── Check for non-ASCII characters (Chinese/CJK) in DBA ─────────
    if trade_name_dba and any(ord(c) > 0x2E80 for c in trade_name_dba):
        score += 60

    # ── Surname detection ────────────────────────────────────────────
    all_words = words + dba_words
    has_firm_suffix = any(
        suffix in name_upper or suffix in dba_upper for suffix in FIRM_SUFFIXES
    )

    for word in all_words:
        if word in CHINESE_SURNAMES and word not in AMBIGUOUS_SURNAMES:
            if has_firm_suffix:
                score += 40
            else:
                score += 25
            break
        elif word in AMBIGUOUS_SURNAMES:
            if has_firm_suffix:
                score += 30
            break

    # ── Multi-surname pattern (two+ Chinese surnames in name) ────────
    surname_count = sum(1 for w in words if w in CHINESE_SURNAMES)
    if surname_count >= 2:
        score += 15

    # ── City hub bonus ───────────────────────────────────────────────
    for hub in CHINESE_HUB_CITIES:
        if hub in city_upper:
            score += 15
            break

    return min(score, 100)


def get_affiliation_label(score: int) -> str:
    """Convert a numeric score to a human-readable label."""
    if score >= 50:
        return "Likely"
    elif score >= 25:
        return "Maybe"
    else:
        return ""
