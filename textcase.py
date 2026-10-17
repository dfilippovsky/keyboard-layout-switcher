"""Циклічна зміна регістру: lower → UPPER → Title → camelCase → snake_case → kebab-case."""
import re

# Слово: літери/цифри, апостроф усередині («it's», «м'ята»)
_WORD = r"[^\W_]+(?:['’ʼ][^\W_]+)*"
_WORD_RE = re.compile(_WORD)
# Фраза для camel/snake/kebab: слова, розділені пробілами, «_» або «-».
# Розділові знаки й переноси рядків розривають фразу й лишаються як є.
_PHRASE_RE = re.compile(_WORD + r"(?:[ _-]+" + _WORD + r")*")
_SEP_RE = re.compile(r"[ _-]+")


def _split(phrase):
    """'helloWorld_foo-bar HTTPServer' -> ['hello', 'World', 'foo', 'bar', 'HTTP', 'Server']"""
    words = []
    for part in _SEP_RE.split(phrase):
        cur = ""
        for i, ch in enumerate(part):
            if cur and ch.isupper() and (
                    cur[-1].islower() or cur[-1].isdigit() or
                    (cur[-1].isupper() and i + 1 < len(part) and part[i + 1].islower())):
                words.append(cur)
                cur = ""
            cur += ch
        if cur:
            words.append(cur)
    return words


def _cap(word):
    return word[:1].upper() + word[1:].lower()


def _phrases(text, join):
    return _PHRASE_RE.sub(lambda m: join(_split(m.group())), text)


STYLES = (
    ("lower", str.lower),
    ("UPPER", str.upper),
    ("Title", lambda t: _WORD_RE.sub(lambda m: _cap(m.group()), t)),
    ("camelCase", lambda t: _phrases(t, lambda ws: ws[0].lower() + "".join(_cap(x) for x in ws[1:]))),
    ("snake_case", lambda t: _phrases(t, lambda ws: "_".join(x.lower() for x in ws))),
    ("kebab-case", lambda t: _phrases(t, lambda ws: "-".join(x.lower() for x in ws))),
)
# У якому стилі вже записаний текст: спершу найспецифічніші («hello» — це і lower,
# і camelCase, але «hello_world» — точно snake_case, а не lower).
_DETECT_ORDER = (3, 4, 5, 2, 1, 0)
_IDENTIFIER_STYLES = (3, 4, 5)


class CaseCycler:
    """Пам'ятає останнє перетворення, щоб повторне натискання йшло далі по колу
    від початкового тексту (kebab-case → lower повертає пробіли, а не «hello-world»)."""

    def __init__(self):
        self._last = None  # (результат, індекс стилю, початковий текст)

    def next(self, text):
        if self._last and self._last[0] == text:
            _, idx, original = self._last
            start = idx + 1
        else:
            detected = next((i for i in _DETECT_ORDER if STYLES[i][1](text) == text), -1)
            start = detected + 1
            # З camelCase/snake_case/kebab-case далі по колу йдуть «звичайні» стилі —
            # для них ідентифікатор розбиваємо на слова: hello-world → hello world.
            original = _phrases(text, " ".join) if detected in _IDENTIFIER_STYLES else text
        for k in range(len(STYLES)):
            i = (start + k) % len(STYLES)
            out = STYLES[i][1](original)
            if out != text:
                self._last = (out, i, original)
                return out
        return text
