"""Збирає мовні дані для автовиправлення розкладки: langdata/<мова>.txt.gz.

Джерело — частотні словники FrequencyWords (Hermit Dave, дані — CC BY-SA 4.0,
https://github.com/hermitdave/FrequencyWords), зібрані з субтитрів OpenSubtitles.

Файл містить:
- найчастіші слова (словник: «це точно слово цієї мови»);
- зважені триграми літер (зокрема з межами слова ^ і $) для оцінки слів,
  яких у словнику немає.

Запуск:  python tools/build_langdata.py [en uk ...]
"""
import collections
import gzip
import math
import os
import sys
import urllib.request

URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/{0}/{0}_50k.txt"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "langdata")
CACHE_DIR = os.path.join(ROOT, "build", "frequencywords")

ALPHABETS = {
    "en": "abcdefghijklmnopqrstuvwxyz",
    "uk": "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя",
}
DICT_SIZE = 30000      # скільки найчастіших слів потрапляє в словник
MIN_TRIGRAM = 2        # рідші триграми (сумарна вага, ×10) відкидаються як шум


def fetch(lang):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, lang + ".txt")
    if not os.path.exists(path):
        print("downloading", URL.format(lang))
        urllib.request.urlretrieve(URL.format(lang), path)
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                yield parts[0].lower(), int(parts[1])


def build(lang):
    alphabet = set(ALPHABETS[lang])
    words = [(w, n) for w, n in fetch(lang) if w and set(w) <= alphabet]
    trigrams = collections.Counter()
    for word, n in words:
        weight = math.log(1 + n)  # частотні слова важать більше, але не на порядки
        padded = "^^" + word + "$"
        for i in range(len(padded) - 2):
            trigrams[padded[i:i + 3]] += weight
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, lang + ".txt.gz")
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as f:
        f.write("# %s: FrequencyWords (c) Hermit Dave, CC BY-SA 4.0\n" % lang)
        f.write("# alphabet %s\n" % ALPHABETS[lang])
        for word, _ in words[:DICT_SIZE]:
            f.write(word + "\n")
        f.write("\n")
        for tri, weight in sorted(trigrams.items()):
            count = round(weight * 10)
            if count >= MIN_TRIGRAM:
                f.write("%s %d\n" % (tri, count))
    print("%s: %d words, %d trigrams -> %s (%d KB)" % (
        lang, min(len(words), DICT_SIZE), len(trigrams), path, os.path.getsize(path) // 1024))


if __name__ == "__main__":
    for lang in sys.argv[1:] or sorted(ALPHABETS):
        build(lang)
