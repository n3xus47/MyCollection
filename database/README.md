# Hot Wheels Data Download

Skrypt do pobierania wszystkich modeli Hot Wheels z MediaWiki API (hotwheels.fandom.com).

## Instalacja

```bash
cd database
pip install -r requirements.txt
```

## Użycie

```bash
python download_hotwheels.py
```

lub

```bash
./download_hotwheels.py
```

## Co robi skrypt?

1. **Pobiera listę stron** z kategorii Hot Wheels na wiki Fandom
2. **Ekstrahuje dane z infobox** każdej strony
3. **Normalizuje dane** do spójnego formatu
4. **Zapisuje wyniki** do pliku `hotwheels_models.json`

## Format danych

Każdy model zawiera następujące pola:

### Podstawowa tożsamość
- `model_name` - Pełna nazwa modelu
- `release_year` - Rok wydania
- `toy_number` - Numer zabawki/SKU
- `collector_number` - Numer kolekcjonerski

### Seria i przynależność
- `series_name` - Nazwa serii
- `series_number` - Numer w serii
- `sub_series` - Podseria (Mainline, Premium, etc.)

### Wygląd i specyfikacja
- `body_color` - Kolor nadwozia
- `tampo` - Grafiki/naklejki
- `wheel_type` - Typ kół
- `base_color` - Kolor podwozia
- `base_material` - Materiał podwozia
- `window_color` - Kolor szyb
- `interior_color` - Kolor wnętrza

### Status specjalny
- `treasure_hunt` - Czy to Treasure Hunt (boolean)
- `super_treasure_hunt` - Czy to Super Treasure Hunt (boolean)
- `exclusive` - Sieć ekskluzywna (np. Walmart, Target)

### Dodatkowe
- `page_title` - Tytuł strony na wiki
- `raw_infobox` - Surowe dane z infobox (dla debugowania)

## Funkcje

- **Automatyczne wznowienie**: Jeśli skrypt zostanie przerwany, można go uruchomić ponownie - pominie już przetworzone strony
- **Zapisywanie postępu**: Co 50 stron dane są zapisywane do pliku
- **Obsługa błędów**: Skrypt kontynuuje pracę nawet jeśli niektóre strony nie mogą być pobrane
- **Szacunek dla API**: Opóźnienia między requestami, aby nie przeciążać serwera

## Uwagi

- Pobieranie wszystkich modeli może zająć dużo czasu (może być kilka tysięcy stron)
- Niektóre strony mogą nie mieć infobox - w takim przypadku zapisywane są tylko podstawowe informacje (tytuł strony)
- Skrypt automatycznie usuwa duplikaty stron z różnych kategorii
