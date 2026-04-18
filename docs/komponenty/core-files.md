# core/files — baza plików

## Odpowiedzialność

- Projekty (foldery), kategorie, wersjonowanie, pliki poza projektami.
- Metadane: nazwa, typ, format, projekt, wersja, tagi, status.
- Operacje: zapis blobów, lista, pobranie, duplikacja, archiwizacja, eksport ZIP.

## Zależności zewnętrzne

- **PostgreSQL** — metadane, relacje, uprawnienia.
- **S3 / R2 / GCS** — treść plików (blob). Dev: dysk lokalny.

## Powiązania

- **core/file-context** — indeksowanie i wyszukiwanie korzystają z metadanych i ścieżek storage.
- Moduły generowania — po zakończeniu zapisują nowy `FileAsset` (nowa wersja przy edycji).

## Zasady

- Ścisła izolacja danych per konto użytkownika.
- Wersje nie nadpisują historii — nowa wersja = nowy rekord lub łańcuch wersji.
