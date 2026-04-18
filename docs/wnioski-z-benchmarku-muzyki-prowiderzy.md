# Wnioski z benchmarku dostawców muzyki (materiały edukacyjne)

**Kontekst:** wewnętrzny projekt badawczy `research/music-provider-benchmark` — równoległe wywołania API przy tym samym wejściu (tytuł, styl, tekst, długość docelowa), audyt żądań (`trace`) oraz porównanie kosztów i jakości słuchowej.  
**Zakres:** **KIE (Suno)** — m.in. **V4_5ALL**, **V5**; **WaveSpeed AI (MiniMax Music 2.6)**; **OpenRouter (Lyria 3 Pro / Seedance 1.5 Pro)**; opcjonalnie **ElevenLabs Eleven Music** (ścieżka API w projekcie benchmark przy aktywnym kluczu). **Lyria Clip** został **usunięty z listy modeli w UI** benchmarku; nadal można go wywołać poza tym UI przez API OpenRouter.  
**Uwaga metodologiczna:** ocena jakości dźwięku ma **charakter subiektywny** (odsłuchy, ten sam scenariusz wejściowy); nie zastępuje niezależnego benchmarku MOS ani testów A/B na reprezentatywnej próbie odbiorców.

Szczegóły cenowe z dokumentacji publicznej: [Analiza modeli i cen: muzyka](./analiza-cen-modeli-muzyki.md).

---

## Wniosek 1 — ElevenLabs: wysoki koszt eksperymentów przy generowaniu muzyki przez API

**Uzasadnienie biznesowe i produktowe**

1. **Model rozliczeń** — wg publicznego cennika API, model **Eleven Music (`music_v1`)** rozliczany jest **proporcjonalnie do długości wygenerowanej ścieżki** (orientacyjnie **0,30 USD za minutę**; szczegóły: [ElevenLabs — cennik API](https://elevenlabs.io/pricing/api) oraz zestawienie w repozytorium). Przy wielokrotnych iteracjach (dostrajanie promptu, długości, stylu) koszt **narasta liniowo z czasem trwania audio**, a nie jest „sztywny” jak przy rozliczeniu **per utwór** u innych dostawców.

2. **Dostęp do API** — dokumentacja ElevenLabs wprost wskazuje, że **Music API jest przeznaczone dla użytkowników płatnych** („*The Eleven Music API is only available to paid users*”; m.in. [Music quickstart](https://www.elevenlabs.io/docs/eleven-api/guides/cookbooks/music), [Music streaming](https://elevenlabs.io/docs/eleven-api/guides/how-to/music/streaming)). Interfejs webowy może oferować szerszy dostęp w ramach limitów konta; **ścieżka API podlega osobnym regułom planu** — co przy próbach integracyjnych i prototypowaniu generuje dodatkową barierę kosztową i administracyjną.

3. **Porównanie z alternatywą o stałej cenie za utwór** — np. **MiniMax Music 2.6 przez WaveSpeed** deklaruje w dokumentacji **stałą stawkę per wygenerowany utwór** (w zestawieniu wewnętrznym: **0,15 USD / utwór** przy długości do ok. 5 min). Dla scenariusza „wiele prób po ~2–3 minuty audio” **łączny koszt ElevenLabs rośnie szybciej** niż przy modelu „jedna opłata za cały utwór” u konkurenta z tabeli publicznej.

**Sformułowanie do publikacji**

> Dla zastosowań typu **iteracyjne tworzenie muzyki edukacyjnej** (wiele wersji, krótki cykl feedbacku) **ElevenLabs Eleven Music przez API** — przy obecnym modelu cenowym i ograniczeniu do planów płatnych — **jest ekonomicznie wymagający** względem dostawców oferujących **rozliczenie per cały utwór** lub **niższą jednostkową stawkę** przy porównywalnym limicie długości. **Rekomendacja:** ElevenLabs warto rozważać tam, gdzie priorytetem jest **jakość produkcyjna i licencjonowanie** oraz akceptowalny jest **koszt minutowy**; **nie jako domyślny silnik do tanich eksperymentów** w pętli generuj–odsłuchaj–popraw.

---

## Wniosek 2 — WaveSpeed (MiniMax Music 2.6): atrakcyjna cena, jakość nadal za słaba względem Suno i ElevenLabs

**Uzasadnienie techniczne (subiektywna ocena słuchowa)**

W ramach tego samego benchmarku (identyczne lub zbliżone prompty: styl edukacyjny, tekst zwrotek, tytuł) **model MiniMax Music 2.6** (endpoint WaveSpeed) wypadał **słabiej od referencji**:

- w porównaniu do **Suno przez KIE** — **mniejsza spójność struktury utworu** (zwrotki, refren), **mniej przekonujące brzmienie wokalu** i ogólnie **niższy „finish” produkcyjny** przy tym samym typie zadania;
- w porównaniu do **Eleven Music** (tam, gdzie dostępny był odsłuch) — **niższa „gęstość” brzmienia i mniej naturalna aranżacja** przy podobnym poziomie złożoności promptu.

**Cena nie rekompensuje wszystkich wymagań produktowych** — przy **0,15 USD za utwór** (wg dokumentacji WaveSpeed; zob. [analiza w repozytorium](./analiza-cen-modeli-muzyki.md)) WaveSpeed pozostaje **bardzo konkurencyjny kosztowo**, lecz **nie zastępuje** w warstwie jakościowej **najlepszych modeli Suno** ani **Eleven Music** w zastosowaniach, gdzie liczy się **efekt „gotowy do publikacji”** bez dalszej obróbki.

**Uwaga subiektywna (preferencje słuchowe)** — w **bezpośrednim odsłuchu** referencyjnych generacji z WaveSpeed/MiniMax **nie podobała się nam barwa i „charakter” tych piosenek** (subiektywny gust, nie pomiar instrumentalny): mimo sensownej ceny **nie traktujemy tej linii jako docelowego brzmienia „dla siebie”**, tylko jako **tańszy wariant eksperymentalny / masowy** w zestawieniu z Suno, Lyrią czy Eleven Music.

**Sformułowanie do publikacji**

> **WaveSpeed + MiniMax Music 2.6** to w naszej ocenie **rozsądny wybór kosztowy** do **masowej generacji**, testów A/B promptów i **szkiców** materiałów dydaktycznych. **Nie jest jeszcze równorędną substytucją** dla **Suno (KIE)** ani **Eleven Music** w segmencie **najwyższej jakości percepcyjnej** — przy tych samych wejściach referencyjnych **Suno i ElevenLabs oferowały wyższy poziom odsłuchu**. Rekomendacja produktowa: **WaveSpeed jako warstwa tania / skalowalna**; **Suno (lub podobny topowy model)** tam, gdzie **jakość końcowa** ma pierwszeństwo przed ceną jednostkową.

---

## Wniosek 3 — OpenRouter Lyria 3 Pro: wysoka jakość percepcyjna; **cena w USD jawna**, porównanie z KIE wymaga pomiaru kredytów

**Jakość (subiektywnie, ten sam scenariusz wejściowy)**

W benchmarku **Lyria 3 Pro** (`google/lyria-3-pro-preview`) wypadała **bardzo dobrze** pod kątem **spójności utworu, wokalu i „gotowości” materiału** — w zestawieniu z **Suno przez KIE** była **pełnoprawną alternatywą jakościową** (nie „gorszym klonem”), przy czym styl brzmienia nadal różni się od Suno (inny silnik, inna estetyka mixu).

**Cena vs KIE — co da się powiedzieć z dokumentacji**

- **Lyria:** na karcie OpenRouter widać **0,08 USD / utwór** (*per song*) — **stała skala** do porównań z MiniMax (**0,15 USD/utwór**) czy ElevenLabs (**0,30 USD/min**).
- **KIE:** w publicznym OpenAPI **nie ma tabeli** „ile kredytów schodzi za jedno `generate`” **osobno dla V4_5ALL, V5, V4 itd.** Z dokumentacji **nie wynika**, czy **V4_5ALL** jest taniej czy drożej niż **V5** — tylko że wszystkie te modele mieszczą się w tym samym **schemacie kredytów** i limitach znaków. **Żeby ocenić, czy jedna generacja Suno jest tańsza czy droższa od 0,08 USD Lyrii**, trzeba **odczytać zużycie kredytów** na koncie KIE po jednej próbie i przeliczyć kredyt na USD wg własnego pakietu (szablon myślowy: np. **1000 kredytów ≈ 5 USD** — dokładnie tylko z cennika zakupu u KIE). Szczegóły: [Analiza modeli i cen](./analiza-cen-modeli-muzyki.md) — sekcja *V4_5ALL vs pozostałe modele KIE* oraz *Lyria vs KIE*.

**Sformułowanie do publikacji**

> **Lyria 3 Pro** to w naszej ocenie **mocna opcja produktowa** przy **przejrzystej cenie ok. 0,08 USD za pełny utwór**. **KIE / Suno** nadal wygrywa tam, gdzie liczy się **ekosystem Suno**, **callback KIE** i **dostosowanie modeli V4_5ALL / V5** — ale **nie da się** z publicznych docs jednoznacznie napisać „KIE jest X% taniej od Lyrii”, dopóki **nie zmierzy się** zużycia kredytów na **własnym** koncie. **Rekomendacja:** do decyzji budżetowej **Lyria vs KIE** zrób **jedną parę prób** (to samo wejście) i **porównaj koszt efektywny** (USD po przeliczeniu kredytów vs 0,08 USD).

---

## Podsumowanie (do skrótu na LinkedIn / GitHub)

| Obszar | Treść skrócona |
|--------|----------------|
| **ElevenLabs** | API Music **płatne** + **rozliczenie za minutę** → **drogi silnik do zabawy i wielu iteracji**; sensowniejszy przy **budżecie na jakość** i świadomym koszcie minuty. |
| **WaveSpeed / MiniMax 2.6** | **Niska cena per utwór**, ale w naszej **ocenie słuchowej** **nadal za słaby** vs **Suno** i **Eleven Music**; dodatkowo **subiektywnie** utwory WaveSpeed **nie przypadły nam do gustu** — nadal sensowny do testów i skali, nie do „ulubionej” jakości odsłuchu. |
| **OpenRouter Lyria 3 Pro** | **Jawne ~0,08 USD/utwór**; **jakość w benchmarku bardzo dobra** vs Suno/KIE — **porównanie cenowe z KIE** wymaga **pomiaru kredytów** na koncie (publiczne API KIE **nie rozdziela** ceny per model typu V4_5ALL vs V5). |

---

*Dokument można cytować z linkiem do repozytorium oraz do [analizy cenowej](./analiza-cen-modeli-muzyki.md). Aktualizacja: kwiecień 2026 (dopisek Lyria vs KIE, V4_5ALL vs inne modele w warstwie cenowej dokumentacji).*
