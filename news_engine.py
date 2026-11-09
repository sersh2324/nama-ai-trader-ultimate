POSITIVE = {"beat", "growth", "record", "upgrade", "profit", "surge", "approval",
            "يتجاوز", "نمو", "أرباح", "ارتفاع", "ترقية", "موافقة"}
NEGATIVE = {"miss", "loss", "downgrade", "investigation", "lawsuit", "decline",
            "هبوط", "خسائر", "تراجع", "تحقيق", "دعوى"}
def classify_headline(title: str) -> str:
    text = (title or "").lower()
    pos = sum(1 for w in POSITIVE if w in text)
    neg = sum(1 for w in NEGATIVE if w in text)
    if pos > neg: return "إيجابي مبدئي"
    if neg > pos: return "سلبي مبدئي"
    return "محايد / غير محسوم"
