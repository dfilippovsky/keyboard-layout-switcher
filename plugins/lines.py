"""Дії з рядками виділеного тексту — лише з меню трею «Дії» (без гарячих клавіш;
їх можна призначити в налаштуваннях)."""


def _lines(func):
    """transform для text_action: func(список рядків) -> список рядків. Перенос у кінці
    виділення і стиль переносів (\\r\\n чи \\n) зберігаються."""
    def transform(text):
        nl = "\r\n" if "\r\n" in text else "\n"
        body = text.replace("\r\n", "\n")
        ending = "\n" if body.endswith("\n") else ""
        lines = func(body[:len(body) - len(ending)].split("\n"))
        return ("\n".join(lines) + ending).replace("\n", nl)
    return transform


def _sort(lines):
    return sorted(lines, key=str.casefold)


def _unique(lines):
    return list(dict.fromkeys(lines))


def _number(lines):
    return ["%d. %s" % (i, line) for i, line in enumerate(lines, 1)]


def register(api):
    api.text_action("sort", "Рядки: впорядкувати за абеткою", _lines(_sort))
    api.text_action("unique", "Рядки: прибрати повтори", _lines(_unique))
    api.text_action("reverse", "Рядки: у зворотному порядку", _lines(lambda lines: lines[::-1]))
    api.text_action("number", "Рядки: пронумерувати", _lines(_number))
