import { createContext, useContext, useState, useCallback } from 'react';

// Lightweight i18n. Scope: navigation, the Setup screen, and main action labels.
// Anything not translated falls back to English, then to the key itself.

export const LANGS = [
  { code: 'en', label: 'EN' },
  { code: 'cs', label: 'CZ' },
  { code: 'sk', label: 'SK' },
];

const STRINGS = {
  en: {
    'nav.swipe': 'Swipe', 'nav.compare': 'Compare', 'nav.liked': 'Liked',
    'nav.profile': 'Profile', 'nav.setup': 'Setup',

    'setup.title': 'Scraper settings',
    'setup.save': 'Save', 'setup.saving': 'Saving…',
    'setup.savechanges': 'Save changes', 'setup.unsaved': 'Unsaved changes',

    'sec.appearance': 'Appearance', 'sec.scraper': 'Scraper',
    'sec.model': 'Model', 'sec.urls': 'Search URLs',

    'row.theme': 'Theme', 'row.theme.desc': 'Switch between dark and light',
    'opt.dark': 'Dark', 'opt.light': 'Light',
    'row.language': 'Language', 'row.language.desc': 'Interface language',

    'row.polish': 'Filter Polish sellers',
    'row.polish.desc': 'Skip items where seller is located in Poland',
    'row.maxpages': 'Max pages per URL',
    'row.maxpages.desc': 'Catalog pages fetched per search URL (more = slower)',
    'row.workers': 'Concurrent workers',
    'row.workers.desc': 'Parallel item-page fetches (lower = safer, less likely to get blocked)',
    'row.ratelimit': 'Rate-limit pause (s)',
    'row.ratelimit.desc': 'Seconds to wait when Vinted blocks you',
    'row.imagemode': 'Image mode',
    'row.imagemode.catalog': 'Thumbnail from search page — fast',
    'row.imagemode.item': 'Full image from item page — slower but higher quality',
    'opt.catalog': 'Catalog', 'opt.itempage': 'Item page',
    'row.alpha': 'FashionCLIP weight',

    'urls.help.title': 'How to get a URL',
    'urls.help.1': 'Open vinted.cz, set your filters (size, category, price…)',
    'urls.help.2': 'Copy the URL from the address bar',
    'urls.help.3': 'Paste it below — expired params are stripped automatically',
    'urls.add': '+ Add URL',
    'urls.placeholder': 'Paste vinted.cz URL…',
    'urls.labelph': 'Label (optional, e.g. XL jackets)',
    'btn.add': 'Add', 'btn.cancel': 'Cancel',

    'profile.title': 'Profile',
    'sec.stats': 'Stats', 'sec.pipeline': 'Pipeline', 'sec.scoredist': 'Score distribution',
    'act.scrape': 'Scrape now', 'act.scrape.desc': 'Fetch new items from your search URLs, then embed them',
    'act.retrain': 'Retrain + rescore', 'act.retrain.desc': 'Train the model on your swipes, then re-rank everything',
    'act.score': 'Rescore items', 'act.score.desc': 'Re-rank all items with the current model',
    'act.sold': 'Check sold', 'act.sold.desc': 'Mark items no longer available on Vinted',
    'act.blocklist': 'Build blocklist', 'act.blocklist.desc': 'Update the Polish-seller filter word list',
  },
  cs: {
    'nav.swipe': 'Swipe', 'nav.compare': 'Porovnat', 'nav.liked': 'Oblíbené',
    'nav.profile': 'Profil', 'nav.setup': 'Nastavení',

    'setup.title': 'Nastavení scraperu',
    'setup.save': 'Uložit', 'setup.saving': 'Ukládám…',
    'setup.savechanges': 'Uložit změny', 'setup.unsaved': 'Neuložené změny',

    'sec.appearance': 'Vzhled', 'sec.scraper': 'Scraper',
    'sec.model': 'Model', 'sec.urls': 'Vyhledávací URL',

    'row.theme': 'Motiv', 'row.theme.desc': 'Přepnout světlý / tmavý režim',
    'opt.dark': 'Tmavý', 'opt.light': 'Světlý',
    'row.language': 'Jazyk', 'row.language.desc': 'Jazyk rozhraní',

    'row.polish': 'Filtrovat polské prodejce',
    'row.polish.desc': 'Přeskočit zboží, kde je prodejce z Polska',
    'row.maxpages': 'Max. stránek na URL',
    'row.maxpages.desc': 'Kolik stránek katalogu načíst na URL (více = pomalejší)',
    'row.workers': 'Souběžní pracovníci',
    'row.workers.desc': 'Paralelní načítání stránek (méně = bezpečnější, menší riziko blokace)',
    'row.ratelimit': 'Pauza při limitu (s)',
    'row.ratelimit.desc': 'Počet sekund čekání, když Vinted zablokuje',
    'row.imagemode': 'Režim obrázků',
    'row.imagemode.catalog': 'Náhled z výsledků hledání — rychlé',
    'row.imagemode.item': 'Plný obrázek ze stránky zboží — pomalejší, ale kvalitnější',
    'opt.catalog': 'Katalog', 'opt.itempage': 'Stránka zboží',
    'row.alpha': 'Váha FashionCLIP',

    'urls.help.title': 'Jak získat URL',
    'urls.help.1': 'Otevři vinted.cz, nastav filtry (velikost, kategorie, cena…)',
    'urls.help.2': 'Zkopíruj URL z adresního řádku',
    'urls.help.3': 'Vlož ji níže — expirované parametry se odstraní automaticky',
    'urls.add': '+ Přidat URL',
    'urls.placeholder': 'Vlož URL z vinted.cz…',
    'urls.labelph': 'Popisek (volitelně, např. XL bundy)',
    'btn.add': 'Přidat', 'btn.cancel': 'Zrušit',

    'profile.title': 'Profil',
    'sec.stats': 'Statistiky', 'sec.pipeline': 'Akce', 'sec.scoredist': 'Rozložení skóre',
    'act.scrape': 'Stáhnout teď', 'act.scrape.desc': 'Stáhne nové zboží z tvých URL a vytvoří embeddingy',
    'act.retrain': 'Přetrénovat + přeskórovat', 'act.retrain.desc': 'Natrénuje model na tvých swipech a přeřadí vše',
    'act.score': 'Přeskórovat', 'act.score.desc': 'Přeřadí všechno zboží aktuálním modelem',
    'act.sold': 'Zkontrolovat prodané', 'act.sold.desc': 'Označí zboží, které už není dostupné',
    'act.blocklist': 'Vytvořit blocklist', 'act.blocklist.desc': 'Aktualizuje seznam slov polského filtru',
  },
  sk: {
    'nav.swipe': 'Swipe', 'nav.compare': 'Porovnať', 'nav.liked': 'Obľúbené',
    'nav.profile': 'Profil', 'nav.setup': 'Nastavenia',

    'setup.title': 'Nastavenia scrapera',
    'setup.save': 'Uložiť', 'setup.saving': 'Ukladám…',
    'setup.savechanges': 'Uložiť zmeny', 'setup.unsaved': 'Neuložené zmeny',

    'sec.appearance': 'Vzhľad', 'sec.scraper': 'Scraper',
    'sec.model': 'Model', 'sec.urls': 'Vyhľadávacie URL',

    'row.theme': 'Motív', 'row.theme.desc': 'Prepnúť svetlý / tmavý režim',
    'opt.dark': 'Tmavý', 'opt.light': 'Svetlý',
    'row.language': 'Jazyk', 'row.language.desc': 'Jazyk rozhrania',

    'row.polish': 'Filtrovať poľských predajcov',
    'row.polish.desc': 'Preskočiť tovar, kde je predajca z Poľska',
    'row.maxpages': 'Max. stránok na URL',
    'row.maxpages.desc': 'Koľko stránok katalógu načítať na URL (viac = pomalšie)',
    'row.workers': 'Súbežní pracovníci',
    'row.workers.desc': 'Paralelné načítanie stránok (menej = bezpečnejšie, menšie riziko blokácie)',
    'row.ratelimit': 'Pauza pri limite (s)',
    'row.ratelimit.desc': 'Počet sekúnd čakania, keď Vinted zablokuje',
    'row.imagemode': 'Režim obrázkov',
    'row.imagemode.catalog': 'Náhľad z výsledkov hľadania — rýchle',
    'row.imagemode.item': 'Plný obrázok zo stránky tovaru — pomalšie, ale kvalitnejšie',
    'opt.catalog': 'Katalóg', 'opt.itempage': 'Stránka tovaru',
    'row.alpha': 'Váha FashionCLIP',

    'urls.help.title': 'Ako získať URL',
    'urls.help.1': 'Otvor vinted.cz, nastav filtre (veľkosť, kategória, cena…)',
    'urls.help.2': 'Skopíruj URL z adresného riadku',
    'urls.help.3': 'Vlož ju nižšie — expirované parametre sa odstránia automaticky',
    'urls.add': '+ Pridať URL',
    'urls.placeholder': 'Vlož URL z vinted.cz…',
    'urls.labelph': 'Popis (voliteľné, napr. XL bundy)',
    'btn.add': 'Pridať', 'btn.cancel': 'Zrušiť',

    'profile.title': 'Profil',
    'sec.stats': 'Štatistiky', 'sec.pipeline': 'Akcie', 'sec.scoredist': 'Rozloženie skóre',
    'act.scrape': 'Stiahnuť teraz', 'act.scrape.desc': 'Stiahne nový tovar z tvojich URL a vytvorí embeddingy',
    'act.retrain': 'Pretrénovať + preskórovať', 'act.retrain.desc': 'Natrénuje model na tvojich swipoch a preradí všetko',
    'act.score': 'Preskórovať', 'act.score.desc': 'Preradí všetok tovar aktuálnym modelom',
    'act.sold': 'Skontrolovať predané', 'act.sold.desc': 'Označí tovar, ktorý už nie je dostupný',
    'act.blocklist': 'Vytvoriť blocklist', 'act.blocklist.desc': 'Aktualizuje zoznam slov poľského filtra',
  },
};

const LangContext = createContext({ lang: 'en', setLang: () => {}, t: (k) => k });

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(() => localStorage.getItem('vinted_lang') || 'en');
  const setLang = useCallback((l) => {
    localStorage.setItem('vinted_lang', l);
    setLangState(l);
  }, []);
  const t = useCallback(
    (key) => STRINGS[lang]?.[key] ?? STRINGS.en[key] ?? key,
    [lang],
  );
  return <LangContext.Provider value={{ lang, setLang, t }}>{children}</LangContext.Provider>;
}

export function useLang() {
  return useContext(LangContext);
}
