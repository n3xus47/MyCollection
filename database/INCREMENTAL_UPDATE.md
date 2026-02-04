# Przyrostowa Aktualizacja Danych Hot Wheels

## Problem

Obecne dane JSON (16,596 stron) nie zawierają wariantów z tabel "Versions". Pełne ponowne pobieranie wszystkich 16,612 stron zajęłoby kilka godzin.

## Rozwiązanie

Skrypt `incremental_update.py` wykonuje przyrostową aktualizację:

1. **Wczytuje istniejące dane** z `hotwheels_models.json`
2. **Sprawdza które strony już są** w JSON
3. **Dla istniejących stron bez wariantów** - ekstrahuje warianty z tabeli "Versions"
4. **Dla nowych stron** - pobiera je normalnie (z wariantami)
5. **Zapisuje zaktualizowane dane** z powrotem do JSON

## Korzyści

- ⚡ **Szybciej** - nie pobiera wszystkich stron od nowa
- 🎯 **Skupia się na wariantach** - dodaje warianty do istniejących stron
- 🔄 **Przyrostowe** - można uruchamiać wielokrotnie
- ✅ **Bezpieczne** - tryb `--dry-run` do testowania

## Użycie

### Test (dry run)

```bash
cd ~/Projekty/MyCollection/database
python incremental_update.py --dry-run
```

To pokaże:
- Ile stron ma warianty do dodania
- Ile nowych stron jest do pobrania
- Bez faktycznych zmian w pliku

### Rzeczywista aktualizacja

```bash
cd ~/Projekty/MyCollection/database
python incremental_update.py
```

To:
- Zaktualizuje istniejące strony dodając warianty
- Pobierze nowe strony
- Zapisze zaktualizowane dane

## Przykład

**Przed aktualizacją:**
```json
{
  "page_title": "Custom '70 Chevy Nova",
  "toy_number": "GRM04",
  ...
}
```

**Po aktualizacji:**
```json
[
  {
    "page_title": "Custom '70 Chevy Nova",
    "toy_number": "GRM04",
    "release_year": "2021",
    "series_name": "Hot Wheels Boulevard",
    ...
  },
  {
    "page_title": "Custom '70 Chevy Nova",
    "toy_number": "HHL50",
    "release_year": "2022",
    "series_name": "Car Culture: Team Transport",
    ...
  },
  // ... pozostałe warianty
]
```

## Czas Wykonania

- **Dry run**: ~1-2 minuty (tylko sprawdza)
- **Aktualizacja 100 stron**: ~5-10 minut
- **Aktualizacja wszystkich**: ~2-4 godziny (zależnie od liczby stron z wariantami)

## Uwagi

- Skrypt przetwarza strony w porcjach (domyślnie 100 dla testu)
- Można uruchomić wielokrotnie - nie tworzy duplikatów
- Sprawdza czy wariant już istnieje przed dodaniem
- Zachowuje istniejące dane dla stron które już mają warianty

## Następne Kroki

Po aktualizacji:

1. **Sprawdź statystyki:**
   ```bash
   python -c "import json; data=json.load(open('hotwheels_models.json')); print(f'Modeli: {len(data)}'); toy_nums = {m.get('toy_number') for m in data if m.get('toy_number')}; print(f'Unikalnych kodów: {len(toy_nums)}')"
   ```

2. **Zaimportuj do bazy:**
   ```bash
   cd ../backend
   source venv/bin/activate
   python import_hotwheels.py
   ```

3. **Sprawdź czy działa:**
   ```bash
   python test_import.py
   ```
