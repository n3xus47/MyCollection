# Przewodnik Szybkiego Startu

## Wymagania

- Python 3.8+
- PostgreSQL
- Flutter SDK
- Android Studio / Xcode (do rozwoju mobilnego)

## Konfiguracja Backendu (5 minut)

```bash
cd backend

# Utwórz środowisko wirtualne
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Zainstaluj zależności
pip install -r requirements.txt

# Utwórz bazę danych
createdb diecast_db

# Skonfiguruj środowisko
cp .env.example .env
# Edytuj .env z danymi dostępowymi do bazy danych

# Zainicjalizuj bazę danych przykładowymi danymi
python init_db.py

# Uruchom serwer
uvicorn app.main:app --reload
```

Serwer będzie działał na `http://localhost:8000`

## Konfiguracja Frontendu (5 minut)

```bash
cd frontend

# Zainstaluj zależności
flutter pub get

# Zaktualizuj URL API w lib/services/api_service.dart jeśli potrzeba
# Domyślnie: http://localhost:8000

# Uruchom na urządzeniu/emulatorze
flutter run
```

## Testowanie Aplikacji

1. **Test Backend API**:
   ```bash
   curl http://localhost:8000/identify/ABC12
   ```

2. **Aplikacja Flutter**:
   - Otwórz aplikację
   - Przejdź do zakładki "Scan"
   - Skieruj kamerę na kod numeru zabawki (format: 5 znaków alfanumerycznych)
   - Jeśli istnieje wiele wariantów, wybierz jeden z dolnego panelu
   - Zobacz swoją kolekcję w zakładce "Collection"

## Przykładowe Dane

Skrypt `init_db.py` tworzy:
- Samochód: `ABC12` - Hot Wheels Mainline (Mattel) z 3 wariantami
- Samochód: `XYZ99` - Matchbox Classic (Mattel) z 1 wariantem

## Rozwiązywanie Problemów

**Problemy z Backendem**:
- Upewnij się, że PostgreSQL działa
- Sprawdź DATABASE_URL w pliku .env
- Zweryfikuj, że baza danych istnieje: `psql -l | grep diecast_db`

**Problemy z Flutterem**:
- Nadaj uprawnienia do kamery, gdy zostaniesz poproszony
- Dla Androida: Sprawdź uprawnienia w AndroidManifest.xml
- Dla iOS: Sprawdź uprawnienia w Info.plist
- Upewnij się, że backend działa przed testowaniem skanera

**Problemy z Siecią**:
- Jeśli używasz emulatora, użyj `10.0.2.2` zamiast `localhost` dla Androida
- Jeśli używasz fizycznego urządzenia, użyj adresu IP swojego komputera
