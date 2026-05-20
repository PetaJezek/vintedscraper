"""
Build a Polish word blocklist from items you flagged as Polish in the viewer.

Usage:
    source .venv/bin/activate
    python build_polish_blocklist.py

Reads  : polish_removed.json   (flagged via the 🇵🇱 button in vinted_viewer.html)
Writes : polish_blocklist.json (loaded automatically by vinted_scraper.py)

Run this whenever you've flagged a batch of new Polish items. The scraper
picks up the updated blocklist on the next run — no restart needed.
"""

import json
import re
from pathlib import Path
from collections import defaultdict

INPUT_FILE  = "polish_removed.json"
OUTPUT_FILE = "polish_blocklist.json"

MIN_WORD_LEN  = 4    # ignore short words
MIN_ITEM_FREQ = 2    # word must appear in ≥ N flagged items to be included

# ── Seed list ────────────────────────────────────────────────────────────────
# Common Polish words found in Vinted listings. These are included regardless
# of whether they appear in your flagged items.
POLISH_SEED: set[str] = {
    # selling / transaction
    "sprzedam", "kupie", "zamienie", "wysylka", "wysyłka", "odbior", "odbiór",
    "przesylka", "przesyłka", "paczkomat", "kurierem",
    # condition / description
    "uzywany", "używany", "nówka", "idealny", "idealna", "noszony", "noszona",
    "zakupiony", "zakupiona", "oryginalny", "oryginalna",
    # clothing terms (Polish-specific forms)
    "rozmiar", "kurtka", "bluza", "bluzka", "spodnie", "koszula", "koszulka",
    "sukienka", "spodnica", "spódnica", "sweter", "marynarka", "garnitur",
    "czapka", "szalik", "buty", "sandaly", "sandały", "trampki",
    # common Polish words
    "bardzo", "prosze", "proszę", "dziekuje", "dziękuję", "polecam",
    "okazja", "przecena", "tanio", "tanie", "gratis", "najtaniej",
    "damski", "damska", "meska", "męska", "meski", "meski",
    "zdjecia", "zdjęcia", "dodatkowe", "pytania",
    # Polish city/region names that slip past keyword filter
    "warszawa", "krakow", "kraków", "wroclaw", "wrocław", "gdansk", "gdańsk",
    "poznan", "poznań", "lodz", "łódź", "katowice", "lublin", "bialystok",
    "białystok", "rzeszow", "rzeszów", "opole", "szczecin", "torun", "toruń",
}

# ── Czech stop words to exclude ───────────────────────────────────────────────
# Prevent common Czech words from ending up in the blocklist.
CZECH_STOP: set[str] = {
    "novy", "nova", "nove", "prodám", "prodám", "velikost", "stav", "cena",
    "levne", "dobry", "krasny", "pekny", "dobra", "dobre", "koupit",
    "prodej", "nabidka", "damsky", "pansky", "pouzite", "nepouzite",
    "posilam", "doruceni", "zasilkovna", "osobni", "odber", "zasilka",
    "obleceni", "oblečení", "znacka", "značka", "stav",
}


def extract_words(text: str) -> list[str]:
    return [
        w for w in re.findall(r"\b[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]{%d,}\b" % MIN_WORD_LEN, text.lower())
        if w not in CZECH_STOP
    ]


def main() -> None:
    path = Path(INPUT_FILE)
    if not path.exists():
        print(f"  {INPUT_FILE} not found.")
        print("  Flag Polish items with the 🇵🇱 button in vinted_viewer.html first.")
        print(f"  Writing seed-only blocklist to {OUTPUT_FILE}…")
        out = sorted(POLISH_SEED)
        Path(OUTPUT_FILE).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  {len(out)} seed words written.")
        return

    with open(path, encoding="utf-8") as f:
        items = json.load(f)

    print(f"  Processing {len(items)} flagged items…")

    # word → set of item IDs that contain it
    word_items: dict[str, set] = defaultdict(set)
    for item in items:
        item_id = str(item.get("id", ""))
        text = " ".join(filter(None, [
            item.get("title", ""),
            item.get("description", ""),
            item.get("location", ""),
        ]))
        for word in extract_words(text):
            word_items[word].add(item_id)

    learned = {w for w, ids in word_items.items() if len(ids) >= MIN_ITEM_FREQ}
    all_words = sorted(POLISH_SEED | learned)

    Path(OUTPUT_FILE).write_text(
        json.dumps(all_words, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"  Seed words   : {len(POLISH_SEED)}")
    print(f"  Learned words: {len(learned)}  (appear in ≥{MIN_ITEM_FREQ} flagged items)")
    print(f"  Total written: {len(all_words)}  →  {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
