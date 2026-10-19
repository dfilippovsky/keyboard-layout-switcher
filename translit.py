"""Транслітерація українського тексту латиницею за офіційною системою
(постанова КМУ № 55 від 27.01.2010): «Згорани» → «Zghorany», «Знам'янка» → «Znamianka»."""

import math
import re

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



# ---------- зворотна транслітерація: латиниця → кирилиця ----------
# Латинське письмо за постановою № 55 неоднозначне: «i» — це і, ї або й, «ia» — я або ія,
# м'який знак і апостроф не передаються. Тому перебираємо варіанти: спершу шукаємо слово
# в частотному словнику (тому самому, що для автовиправлення), інакше пучковим пошуком
# беремо найбільш схожий на українське слово за триграмами, а без мовних даних —
# найпростіший. Апостроф ставиться за правописом.

_DIGRAPHS = {"shch": "щ", "zh": "ж", "kh": "х", "ts": "ц", "ch": "ч", "sh": "ш", "gh": "г"}
_IOTATED = {"ia": "я", "ie": "є", "iu": "ю"}
_INITIAL_Y = {"ye": "є", "yi": "ї", "yu": "ю", "ya": "я"}
_LETTERS = {"a": "а", "b": "б", "v": "в", "h": "г", "d": "д", "e": "е", "z": "з", "y": "и",
            "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "r": "р", "s": "с",
            "t": "т", "u": "у", "f": "ф"}
_CYR_VOWELS = "аеєиіїоуюя"
_UKRAINIAN_ONLY = frozenset("іїєґ")
_LABIALS = "бпвмф"
_SOFTENABLE = "дтзсцлнр"   # після них міг бути «ь», який латиницею не передається
_LATIN_WORD = re.compile(r"[A-Za-z]+(?:['’ʼ][A-Za-z]+)*")
_NOT_TRANSLIT = re.compile(r"[cjqwx]")
_ENGLISH_CONTRACTION = re.compile(r"['’ʼ](?:t|s|m|d|ll|re|ve)$")   # don't, I'm, it's
# Прикметники на -ський, -цький, -зький (і форми) — з «ь», який модель часто губить
_ADJ_END = r"(к(?:ий|а|е|і|ого|ому|им|их|ими|ої|ій|у|ою)?)$"
_SKYI = re.compile(r"(?<=[а-яіїєґ]{2})([сцз])" + _ADJ_END)
_TSKYI = re.compile(r"ць" + _ADJ_END)
_RUSSIAN_PENALTY = 2.5     # у словнику з субтитрів є й російські слова (мой, ней, иди)
_SPLIT_PENALTY = 0.5       # сполучення прочитати по літері («bratskyi» — т + с)
_SOFT_PENALTY = 0.4        # вставити «ь»
_PENALTY_WEIGHT = 4.0      # штраф у «натах» триграмної моделі
_DICT_PENALTY_WEIGHT = 2.0  # серед слів словника частота важить більше (день, а не ден)
_LOGP_FLOOR = -6.0
_BEAM = 12                # скільки варіантів тримати на кожній позиції
_MAX_STEPS = 3000          # стеля перебору словника на одне слово


def _options(word, i, prev):
    """[(скільки латинських літер, кирилиця, штраф)] для позиції i слова малими
    літерами; prev — попередня літера кирилицею ("" на початку слова)."""
    out = []
    if word.startswith("shch", i):
        out.append((4, "щ", 0))
    two = word[i:i + 2]
    if two in _DIGRAPHS:
        out.append((2, _DIGRAPHS[two], 0))
    if not prev and two in _INITIAL_Y:
        out.append((2, _INITIAL_Y[two], 0))
    elif two in _IOTATED:
        out.append((2, _IOTATED[two], 0))
    split = _SPLIT_PENALTY if out else 0
    one, nxt = word[i], word[i + 1:i + 2]
    if one == "i":
        if prev in tuple(_CYR_VOWELS):
            # -ii, -ai в кінці — ій, ай; між голосною й приголосною — найчастіше ї (Україна),
            # а після «и» — майже завжди (Київ)
            if not nxt:
                letters = [("й", 0), ("ї", 0.6), ("і", 0.6)]
            elif prev == "и":
                letters = [("ї", 0), ("й", 0.8), ("і", 1.2)]
            else:
                letters = [("ї", 0), ("й", 0.4), ("і", 0.5)]
        else:
            letters = [("і", 0), ("й", 1.2), ("ї", 1.2)]
    elif one == "y" and not prev:
        letters = [("й", 0), ("и", 0.6)]  # на «и» українські слова майже не починаються (йди, йти)
    elif one == "g":
        letters = [("ґ", 0), ("г", 0.5)]
    elif one in _LETTERS:
        letters = [(_LETTERS[one], 0)]
    else:
        letters = []
    out += [(1, cyr, pen + split) for cyr, pen in letters]
    return out


def _steps(word, i, cyr):
    """Варіанти продовження: [(нова позиція, додана кирилиця, штраф)], зокрема з «ь» —
    лише перед приголосною, «o» або в кінці слова (ьо, але не ья, ьі, ьа)."""
    if word[i] in "'’ʼ":
        return [(i + 1, "", 0)]
    out = []
    for n, part, pen in _options(word, i, cyr[-1:]):
        out.append((i + n, part, pen))
        if part[-1] in _SOFTENABLE and word[i + n:i + n + 1] not in tuple("aeiuy"):
            out.append((i + n, part + "ь", pen + _SOFT_PENALTY))
    return out


def _from_dictionary(word, model):
    """Слово словника, яке дає ця латиниця, або None. Перебір обрізається за префіксами
    слів словника, тож лишається малим."""
    hits, steps = [], 0

    def walk(i, cyr, penalty):
        nonlocal steps
        steps += 1
        if steps > _MAX_STEPS:
            return
        if i == len(word):
            rank = model.word_rank(cyr)
            if rank:
                hits.append((math.log(rank) + _DICT_PENALTY_WEIGHT * penalty, cyr))
            return
        for j, part, pen in _steps(word, i, cyr):
            if not part or model.has_prefix(cyr + part):
                walk(j, cyr + part, penalty + pen)

    walk(0, "", 0.0)
    # Словник зібрано з субтитрів, і в ньому є російські слова. Якщо серед варіантів є
    # слово із суто українською літерою, варіант без жодної такої — підозрілий: мої, а не мой
    if any(_UKRAINIAN_ONLY.intersection(cyr) for _, cyr in hits):
        hits = [(key + (0 if _UKRAINIAN_ONLY.intersection(cyr) else _RUSSIAN_PENALTY), cyr)
                for key, cyr in hits]
    return min(hits)[1] if hits else None


def _gain(model, cyr, part):
    if model is None:
        return 0.0
    padded = "^^" + cyr
    total = 0.0
    for ch in part:
        # Невідома триграма (рідкісна назва: «киї» в Київ) не має переважувати правила
        total += max(_LOGP_FLOOR, model.logp(padded[-2:] + ch))
        padded += ch
    return total


def _best_guess(word, model):
    """Пучковий пошук: на кожній позиції тримаємо _BEAM найкращих варіантів за
    триграмною моделлю мінус штрафи (без моделі — лише за штрафами)."""
    states = [{} for _ in range(len(word) + 1)]
    states[0][""] = 0.0
    for i in range(len(word)):
        beam = sorted(states[i].items(), key=lambda kv: kv[1], reverse=True)[:_BEAM]
        for cyr, score in beam:
            for j, part, pen in _steps(word, i, cyr):
                value = score + _gain(model, cyr, part) - _PENALTY_WEIGHT * pen
                if value > states[j].get(cyr + part, -math.inf):
                    states[j][cyr + part] = value
    final = states[-1]
    if not final:
        return None
    return max(final, key=lambda cyr: final[cyr] + _gain(model, cyr, "$"))


def _apostrophes(cyr):
    """Апостроф за правописом: після б, п, в, м, ф перед я, ю, є, ї, якщо перед губним
    немає іншого приголосного, крім р (п'ять, сім'я, але свято); перед ї після приголосного — завжди."""
    out = []
    for i, ch in enumerate(cyr):
        if ch in "яюєї" and i:
            prev, before = cyr[i - 1], cyr[i - 2] if i > 1 else ""
            if prev not in _CYR_VOWELS + "ьй" and (
                    ch == "ї" or (prev in _LABIALS and (not before or before in _CYR_VOWELS + "р"))):
                out.append("'")
        out.append(ch)
    return "".join(out)


def _restore_case(latin, cyr):
    letters = [ch for ch in latin if ch.isalpha()]
    if len(letters) > 1 and all(ch.isupper() for ch in letters):
        return cyr.upper()
    if letters[0].isupper():
        return cyr[:1].upper() + cyr[1:]
    return cyr


def _reverse_word(latin, model):
    word = latin.lower()
    if _NOT_TRANSLIT.search(word.replace("shch", "").replace("ch", "")) or _ENGLISH_CONTRACTION.search(word):
        return latin  # c, j, q, w, x чи don't — не транслітерація, а, мабуть, англійське слово
    cyr = _from_dictionary(word, model) if model else None
    if cyr is None:
        cyr = _best_guess(word, model)
        if cyr:
            cyr = _SKYI.sub(r"\1ь\2", cyr)
            # «ts» перед -кий — це ц (німецький) або т + с (братський): вирішує основа
            m = _TSKYI.search(cyr)
            if m and model and model.word_rank(cyr[:m.start()] + "т"):
                cyr = cyr[:m.start()] + "тсь" + m.group(1)
    return _restore_case(latin, _apostrophes(cyr)) if cyr else latin


def untransliterate(text, model=None):
    """Латиниця → кирилиця: «Pryvit» → «Привіт». model — мовна модель української
    (autocorrect.LanguageModel), щоб вибирати між неоднозначними варіантами; без неї —
    лише за правилами."""
    return _LATIN_WORD.sub(lambda m: _reverse_word(m.group(), model), text)


class Transliterator:
    """Гаряча клавіша транслітерації: кирилиця → латиниця, латиниця → кирилиця.
    Повторне натискання на щойно перетвореному тексті повертає його точно таким, як
    був (з пам'яті), а не через зворотну транслітерацію, яка могла б загубити «ь».
    model — функція, що повертає мовну модель української (вантажиться лише при першому
    перетворенні латиниці, якщо автовиправлення її ще не завантажило)."""

    def __init__(self, model=None):
        self._model = model
        self._last = None  # (результат, початковий текст)

    def next(self, text):
        if self._last and self._last[0] == text:
            out = self._last[1]
        elif any(_is_cyr(ch) for ch in text):
            out = transliterate(text)
        else:
            out = untransliterate(text, self._model() if self._model else None)
        self._last = (out, text) if out != text else None
        return out
