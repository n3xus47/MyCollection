# Diecast Collector App MVP

Aplikacja MVP full-stack do zbierania i zarządzania modelami samochodów diecast przy użyciu skanowania OCR.

## Stack Technologiczny

- **Backend**: Python (FastAPI) + SQLAlchemy + PostgreSQL
- **Frontend**: Flutter + google_ml_kit (OCR) + http

## Struktura Projektu

```
MyCollection/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── main.py
│   ├── requirements.txt
│   ├── init_db.py
│   └── .env.example
└── frontend/
    └── lib/
        ├── main.dart
        ├── models/
        │   └── models.dart
        ├── services/
        │   └── api_service.dart
        └── screens/
            ├── home_screen.dart
            └── scanner_screen.dart
```

## Schema Bazy Danych

1. **cars**: id (uuid), toy_number (string, unique), name (string), brand (string)
2. **variants**: id (uuid), car_id (fk), desc (string), is_chase (bool)
3. **user_collection**: id (uuid), variant_id (fk), added_at (timestamp)

## Instrukcje Instalacji

### Konfiguracja Backendu

1. **Zainstaluj PostgreSQL** i utwórz bazę danych:
   ```bash
   createdb diecast_db
   ```

2. **Przejdź do katalogu backend**:
   ```bash
   cd backend
   ```

3. **Utwórz środowisko wirtualne**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # W Windows: venv\Scripts\activate
   ```

4. **Zainstaluj zależności**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Skonfiguruj bazę danych**:
   - Skopiuj `.env.example` do `.env`
   - Zaktualizuj `DATABASE_URL` z danymi dostępowymi do PostgreSQL:
     ```
     DATABASE_URL=postgresql://user:password@localhost:5432/diecast_db
     ```

6. **Zainicjalizuj bazę danych**:
   ```bash
   python init_db.py
   ```

7. **Uruchom serwer**:
   ```bash
   uvicorn app.main:app --reload
   ```

   API będzie dostępne pod adresem `http://localhost:8000`

### Konfiguracja Frontendu

1. **Przejdź do katalogu frontend**:
   ```bash
   cd frontend
   ```

2. **Zainstaluj zależności**:
   ```bash
   flutter pub get
   ```

3. **Zaktualizuj URL API** (jeśli potrzeba):
   - Edytuj `lib/services/api_service.dart`
   - Zmień `baseUrl` na adres Twojego backendu

4. **Uruchom aplikację**:
   ```bash
   flutter run
   ```

## Endpointy API

### GET `/identify/{code}`
Identyfikuje samochód po numerze zabawki i zwraca samochód ze wszystkimi wariantami.

**Odpowiedź:**
```json
{
  "car": {
    "id": "uuid",
    "toy_number": "ABC12",
    "name": "Hot Wheels Mainline",
    "brand": "Mattel",
    "variants": []
  },
  "variants": [
    {
      "id": "uuid",
      "car_id": "uuid",
      "desc": "Red",
      "is_chase": false
    }
  ]
}
```

### POST `/collection`
Dodaje wariant do kolekcji użytkownika.

**Żądanie:**
```json
{
  "variant_id": "uuid"
}
```

**Odpowiedź:**
```json
{
  "id": "uuid",
  "variant_id": "uuid",
  "added_at": "2024-01-01T12:00:00",
  "variant": {...},
  "car": {...}
}
```

### GET `/collection`
Zwraca wszystkie elementy w kolekcji użytkownika.

## Funkcje

- **Ekran Skanera**: 
  - Rozpoznawanie tekstu OCR w czasie rzeczywistym przy użyciu kamery
  - Dopasowywanie wzorca regex dla numerów zabawek: `[A-Z0-9]{5}`
  - Mechanizm debounce, aby zapobiec spamowaniu API
  - Dolny panel do wyboru wariantu, gdy istnieje wiele wariantów

- **Ekran Główny**:
  - Wyświetla kolekcję użytkownika
  - Funkcja pull-to-refresh
  - Pokazuje szczegóły samochodu, informacje o wariantach i wskaźniki chase

## Uwagi

- Skaner OCR przetwarza klatki co sekundę z debounce 2 sekundy
- Upewnij się, że nadajesz uprawnienia do kamery podczas uruchamiania aplikacji Flutter
- W produkcji zaktualizuj ustawienia CORS w `backend/app/main.py`, aby ograniczyć źródła
# MyCollection
# MyCollection
