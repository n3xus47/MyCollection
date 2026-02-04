# Zoptymalizowane Pobieranie Danych Hot Wheels

## Optymalizacje

Skrypt `download_hotwheels.py` został zoptymalizowany dla szybszego pobierania:

### 1. Zmniejszone Opóźnienia
- **Opóźnienie między stronami**: `0.3s → 0.1s` (3x szybciej)
- **Opóźnienie między requestami allpages**: `0.5s → 0.1s` (5x szybciej)
- **Opóźnienie przy błędach**: `2s → 1s` (2x szybciej)

### 2. Zwiększone Timeouty
- **Timeout requestów**: `30s → 60s` (większa niezawodność)

### 3. Optymalizacja Zapisywania
- **Zapisywanie postępu**: co `50 stron → 100 stron` (mniej operacji I/O)
- **Usunięto logikę resume** - zawsze zaczyna od nowa (szybsze)

### 4. Lepsze Logowanie
- **Postęp co 25 stron** zamiast co 10 (mniej outputu)
- **Szacowany czas zakończenia (ETA)**
- **Tempo przetwarzania (pages/min)**
- **Statystyki wariantów**

## Szacowany Czas

**Przed optymalizacją:**
- ~16,612 stron × 0.3s = ~83 minuty + czas requestów
- **Całkowity czas: ~2-3 godziny**

**Po optymalizacji:**
- ~16,612 stron × 0.1s = ~28 minut + czas requestów
- **Całkowity czas: ~1-1.5 godziny** (2x szybciej!)

## Użycie

```bash
cd ~/Projekty/MyCollection/database
python download_hotwheels.py
```

## Co Zostanie Pobrane

✅ **Wszystkie strony** (16,612) z Hot Wheels Wiki
✅ **Wszystkie warianty** z tabel "Versions" dla każdej strony
✅ **Każdy wariant jako osobny wpis** z unikalnym `toy_number`

## Przykładowy Output

```
============================================================
Starting Hot Wheels model download (OPTIMIZED)
============================================================
Output file: hotwheels_models.json
Optimizations: Reduced delays (0.1s), batch saves (every 100 pages)

[25/16612] 0.2% | Rate: 12.5 pages/min | ETA: 1320 min | Processing: ...
[50/16612] 0.3% | Rate: 13.2 pages/min | ETA: 1250 min | Processing: ...
💾 Saved: 150 models (145 variants) | Rate: 13.5 pages/min | ETA: 1220 min
...
```

## Backup

Przed rozpoczęciem, istniejący plik `hotwheels_models.json` zostanie zbackupowany do `hotwheels_models.json.backup`.

## Monitorowanie

Możesz monitorować postęp w czasie rzeczywistym:
- Procent ukończenia
- Tempo przetwarzania (stron/minutę)
- Szacowany czas zakończenia (ETA)
- Liczba wariantów znalezionych

## Po Zakończeniu

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

## Uwagi

- ⚠️ **Nie przerywaj procesu** - postęp jest zapisywany co 100 stron
- ⚠️ **Może zająć 1-2 godziny** - uruchom w tle lub w `screen`/`tmux`
- ✅ **Bezpieczne** - stary plik jest backupowany przed rozpoczęciem
