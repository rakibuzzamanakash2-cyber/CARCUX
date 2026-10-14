"""Which language a text is in: Bangla script, Banglish (Romanized Bangla), English, or
a mix (the dataset's `language` values).

Bangla script is unambiguous. Banglish and English share an alphabet, so Banglish is
recognised by common Romanized Bangla words; English by common English words. Short
texts with neither are called English (the safer default for search and display).
"""

import re
import unicodedata

BANGLA = re.compile(r"[ঀ-৿]")
LATIN_WORD = re.compile(r"[A-Za-z]+")

# Frequent Banglish words, in the spellings people actually use.
BANGLISH = frozenset(
    """
    ache achhe asche ase ashe amra amader apni apnara ar baro bari barite bhai bhoy
    bondho bondo bristi brishti dhoke dibe dilo dorkar ekhane ekhono ekhon eto gese geche
    gelo hobe hocche hoise hoyeche hoye hoy hoyni hoy-ni jon jonno kaj kamon kemon keu
    kichu koto kore korche korse korte kotha manush mara moddhe na nai nei niye onek pani
    para porjonto rasta sathe shob sob shokal shokale theke tader tara tobe ufff upor
    agun jam jot dube dubay dubse dhoshe dhose bhenge venge nihoto ahoto khotigrosto
    gujob gujab mittha shotti sotti biddut current kawran pashe kache samne pichone
    lagse lagche legeche boro choto beshi kom komche barche bariye jacche jasse
    karone karon jonno mor komor hatu gorali bhari tana nise nilo niye ahoto koyekjon
    e te er ke re o ki keno kintu tobe ekhane okhane gari rastay rastai pore porche
    """.split()
)
ENGLISH = frozenset(
    """
    the a an and or of in on at to from is are was were has have had been be will
    would after before near since still people water fire road flood rain dead killed
    injured affected police said says reported report about over under this that with
    """.split()
)


def detect_language(text: str) -> str:
    """bn, bn-Latn, en or mixed."""
    text = unicodedata.normalize("NFC", text)
    words = [w.lower() for w in LATIN_WORD.findall(text)]
    banglish = sum(w in BANGLISH for w in words)
    english = sum(w in ENGLISH for w in words)
    if BANGLA.search(text):
        # Bangla script with a real Latin phrase in it, not just a name or a unit: two
        # known words, or two longer Latin words.
        longer = sum(len(w) >= 4 for w in words)
        return "mixed" if english >= 2 or banglish >= 2 or longer >= 3 else "bn"
    if banglish >= 2 and banglish >= english:
        return "mixed" if english >= 3 else "bn-Latn"
    if banglish >= 2:
        return "mixed"
    return "en"
