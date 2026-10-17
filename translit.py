"""Транслітерація українського тексту латиницею за офіційною системою
(постанова КМУ № 55 від 27.01.2010): «Згорани» → «Zghorany», «Знам'янка» → «Znamianka»."""

_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie",
    "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l",
    "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ь": "", "ю": "iu",
    "я": "ia",
    # Не з українського алфавіту — щоб змішаний текст не лишався кирилицею
    "ё": "io", "ы": "y", "э": "e", "ъ": "",
}
# На початку слова
_INITIAL = {"є": "ye", "ї": "yi", "й": "y", "ю": "yu", "я": "ya"}
_APOSTROPHES = "'’ʼ`"


def _is_cyr(ch):
    return ch.lower() in _MAP


def _word_start(text, i):
    return i == 0 or not (text[i - 1].isalpha() or text[i - 1] in _APOSTROPHES)


def _all_caps(text, i):
    """Велика літера в слові, набраному великими («ЄВГЕН» → «YEVHEN», а не «YeVHEN»)."""
    nxt = text[i + 1] if i + 1 < len(text) else ""
    prev = text[i - 1] if i else ""
    if nxt.isalpha():
        return nxt.isupper()
    return prev.isalpha() and prev.isupper()


def transliterate(text):
    out = []
    for i, ch in enumerate(text):
        low = ch.lower()
        if ch in _APOSTROPHES and 0 < i < len(text) - 1 and _is_cyr(text[i - 1]) and _is_cyr(text[i + 1]):
            continue  # апостроф не передається
        if low not in _MAP:
            out.append(ch)
            continue
        if low == "г" and i and text[i - 1].lower() == "з":
            lat = "gh"
        elif low in _INITIAL and _word_start(text, i):
            lat = _INITIAL[low]
        else:
            lat = _MAP[low]
        if ch != low and lat:
            lat = lat.upper() if _all_caps(text, i) else lat[0].upper() + lat[1:]
        out.append(lat)
    return "".join(out)
