"""Українська типографіка для виділеного тексту (або слова перед курсором):

- апостроф ' ’ ` між літерами -> ʼ (U+02BC, як рекомендує правопис для набору);
- "лапки" -> «лапки» (вкладені -> „лапки“);
- дефіс між пробілами -> тире з нерозривним пробілом перед ним: «слово — слово»;
- три крапки -> …;
- кілька пробілів поспіль -> один.
"""
import re

_APOSTROPHE = re.compile(r"(?<=[^\W\d_])['’`](?=[^\W\d_])")
_DASH = re.compile(r"[  ]+[-–—]{1,2}[  ]+")
_SPACES = re.compile(r"(?<=\S) {2,}(?=\S)")


def _quotes(text):
    """Прямі подвійні лапки -> «…», а всередині них -> „…“."""
    out, depth = [], 0
    for i, ch in enumerate(text):
        if ch != '"':
            out.append(ch)
            continue
        prev = text[i - 1] if i else " "
        opening = prev.isspace() or prev in "([{«„-—"
        if opening:
            out.append("«" if depth == 0 else "„")
            depth += 1
        else:
            depth = max(depth - 1, 0)
            out.append("»" if depth == 0 else "“")
    return "".join(out)


def typography(text):
    text = _APOSTROPHE.sub("ʼ", text)
    text = _quotes(text)
    text = _DASH.sub(" — ", text)
    text = text.replace("...", "…")
    return _SPACES.sub(" ", text)


def register(api):
    api.text_action("fix", {"uk": "Українська типографіка («», ʼ, —)",
                            "en": "Ukrainian typography («», ʼ, —)"}, typography, hotkey="Shift+Pause",
                    color=(0xEC, 0x48, 0x99))
