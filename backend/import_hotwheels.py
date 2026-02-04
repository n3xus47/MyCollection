#!/usr/bin/env python3
"""
Skrypt do importu danych Hot Wheels z hotwheels_models_new.json do bazy danych PostgreSQL.
Każdy wpis JSON = casting (Car), warianty pochodzą z raw_infobox.versions.
Używa bulk inserts dla lepszej wydajności.
"""
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Iterable
from sqlmodel import Session, select
from app.models import Car, Variant, engine, create_db_and_tables
import uuid
from collections import defaultdict

# Ścieżka do pliku JSON
JSON_FILE = Path(__file__).parent.parent / "database" / "hotwheels_models_new.json"

def load_json_data():
    """Wczytaj dane z pliku JSON."""
    if not JSON_FILE.exists():
        print(f"Błąd: Plik {JSON_FILE} nie istnieje!")
        sys.exit(1)
    
    print(f"Wczytuję dane z {JSON_FILE}...")
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Wczytano {len(data)} modeli z pliku JSON")
    return data

def normalize_toy_number(toy_number):
    """Normalizuj numer zabawki - usuń spacje, konwertuj na uppercase."""
    if toy_number:
        return str(toy_number).strip().upper().replace(' ', '')
    return None

def parse_release_year(year_value):
    """
    Parsuj release_year z różnych formatów do int.
    Obsługuje: int, string z liczbą, zakresy (np. "2021 - present" -> 2021)
    """
    if year_value is None:
        return None
    
    # Jeśli już jest int, zwróć
    if isinstance(year_value, int):
        return year_value
    
    # Konwertuj na string
    year_str = str(year_value).strip()
    if not year_str:
        return None
    
    # Jeśli zawiera zakres (np. "2021 - present", "2005 - 2020")
    import re
    if ' - ' in year_str or '–' in year_str or ' to ' in year_str.lower():
        # Wyciągnij pierwszy rok z zakresu
        year_match = re.search(r'(\d{4})', year_str)
        if year_match:
            try:
                return int(year_match.group(1))
            except (ValueError, TypeError):
                return None
    
    # Spróbuj skonwertować bezpośrednio na int
    try:
        return int(year_str)
    except (ValueError, TypeError):
        return None

def clean_series_name(series_name: Optional[str]) -> Optional[str]:
    """
    Czyści series_name z końcowych cyfr i znaków typu "4/5", "24/100".
    Przykłady:
    - "Hot Wheels Monster Trucks: Teenage Mutant Ninja Turtles4/5" -> "Hot Wheels Monster Trucks: Teenage Mutant Ninja Turtles"
    - "2004 First Editions24/100" -> "2004 First Editions"
    - "Final Run6/12" -> "Final Run"
    """
    if not series_name:
        return None
    
    import re
    # Usuń końcowe cyfry i formaty ułamkowe (np. "4/5", "24/100")
    # Szukamy wzorców typu: cyfry/cyfry na końcu lub cyfry bezpośrednio przed końcem
    cleaned = re.sub(r'\d+/\d+$', '', series_name)  # Usuń "24/100" na końcu
    cleaned = re.sub(r'\d+$', '', cleaned)  # Usuń końcowe cyfry (np. "4" w "Turtles4")
    cleaned = cleaned.strip()
    
    return cleaned if cleaned else series_name  # Zwróć oryginał jeśli wszystko zostało usunięte

def create_variant_description(model):
    """Tworzy opis wariantu dla użytkownika."""
    parts = []
    
    if model.get('body_color'):
        parts.append(model['body_color'])
    if model.get('tampo'):
        parts.append(f"Tampo: {model['tampo']}")
    if model.get('wheel_type'):
        parts.append(f"Wheels: {model['wheel_type']}")
    
    # Dodaj informacje o treasure hunt
    if model.get('super_treasure_hunt'):
        parts.append("Super Treasure Hunt")
    elif model.get('treasure_hunt'):
        parts.append("Treasure Hunt")
    
    if model.get('exclusive'):
        parts.append(f"Exclusive: {model['exclusive']}")
    
    if not parts:
        return "Standard Edition"
    
    return " - ".join(parts)

def extract_versions(model: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """
    Zwraca listę wersji z raw_infobox.versions.
    Jeśli brak wersji, zwróć pustą listę.
    """
    raw_infobox = model.get('raw_infobox') or {}
    versions = raw_infobox.get('versions')
    if isinstance(versions, list):
        return [v for v in versions if isinstance(v, dict)]
    return []

def build_variant_source(model: Dict[str, Any], version: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Zbuduj spójny słownik wariantu.
    Priorytet: dane z wersji, fallback do pól z top-level JSON.
    """
    version = version or {}
    # Mapowanie kluczy wersji na format top-level.
    mapped_version = {
        'toy_number': version.get('toy_number'),
        'release_year': version.get('year') or version.get('release_year'),
        'series_name': version.get('series') or version.get('series_name'),
        'series_position': version.get('series_position'),
        'series_total': version.get('series_total'),
        'body_color': version.get('body_color'),
        'tampo': version.get('tampo'),
        'wheel_type': version.get('wheel_type'),
        'base_color': version.get('base_color'),
        'window_color': version.get('window_color'),
        'interior_color': version.get('interior_color'),
    }
    merged = dict(model)
    merged.update({k: v for k, v in mapped_version.items() if v is not None})
    return merged

def import_data(dry_run=False):
    """Importuj dane do bazy danych. Każdy wpis JSON = casting, warianty z raw_infobox.versions."""
    # Wczytaj dane
    models = load_json_data()
    
    # Utwórz tabele jeśli nie istnieją
    create_db_and_tables()
    
    with Session(engine) as db:
        # Grupuj modele po model_name (dla Car)
        cars_by_name = defaultdict(list)
        skipped_models = 0
        
        # Najpierw przejdź przez wszystkie modele i pogrupuj po model_name
        for model in models:
            model_name = model.get('model_name')
            page_title = model.get('page_title')
            
            if not model_name and not page_title:
                skipped_models += 1
                continue
            
            if not model_name:
                model_name = page_title
            
            # Użyj model_name jako klucza, page_title jako dodatkowej informacji
            key = model_name
            cars_by_name[key].append(model)
        
        print(f"\nZnaleziono {len(cars_by_name)} unikalnych modeli (casting)")
        
        imported_cars = 0
        imported_variants = 0
        skipped_variants = 0
        
        # Mapowanie car_id dla szybkiego dostępu
        cars_map = {}  # (model_name, page_title) -> car_id
        
        # Przygotuj dane do bulk insert
        cars_to_insert = []
        variants_to_insert = []
        
        skipped_empty_models = 0
        
        for model_name, models_list in cars_by_name.items():
            # Ustal page_title z pierwszego niepustego wpisu
            page_title = next((m.get('page_title') for m in models_list if m.get('page_title')), None)
            
            # Zbierz warianty dla danego castingu zanim utworzysz Car.
            car_variant_sources = []
            for model in models_list:
                versions = list(extract_versions(model))
                if versions:
                    # Jeśli mamy wersje, ignoruj top-level (zwykle to "główny" wariant).
                    car_variant_sources.extend(
                        build_variant_source(model, version) for version in versions
                    )
                else:
                    car_variant_sources.append(build_variant_source(model, None))
            
            # Filtruj warianty bez toy_number - nie jesteśmy w stanie ich identyfikować.
            car_variant_sources = [
                v for v in car_variant_sources
                if normalize_toy_number(v.get('toy_number'))
            ]
            
            if not car_variant_sources:
                skipped_empty_models += 1
                continue
            
            # Sprawdź czy Car już istnieje
            car_key = model_name
            if car_key not in cars_map:
                statement = select(Car).where(Car.model_name == model_name)
                existing_car = db.exec(statement).first()
                
                if existing_car:
                    cars_map[car_key] = existing_car.id
                else:
                    # Przygotuj nowy Car do bulk insert
                    car_id = uuid.uuid4()
                    cars_map[car_key] = car_id
                    cars_to_insert.append({
                        'id': car_id,
                        'model_name': model_name,
                        'page_title': page_title
                    })
                    imported_cars += 1
            
            car_id = cars_map[car_key]
            
            # Przygotuj warianty do bulk insert
            for variant_source in car_variant_sources:
                    raw_toy_number = variant_source.get('toy_number')
                    toy_number = normalize_toy_number(raw_toy_number)
                    
                    # Jeśli toy_number zawiera "/" (np. "1/10"), to to jest pozycja w serii, nie toy_number!
                    # Parsuj "1/10" -> series_position=1, series_total=10
                    series_position = None
                    series_total = None
                    if toy_number and '/' in toy_number:
                        # Parsuj format "1/10" lub "028/250"
                        try:
                            parts = toy_number.split('/')
                            if len(parts) == 2:
                                series_position = int(parts[0])
                                series_total = int(parts[1])
                        except (ValueError, IndexError):
                            pass
                        toy_number = None  # Nie ma prawdziwego toy_number
                    else:
                        # Najpierw sprawdź czy są już wyekstrahowane z JSON (z download_hotwheels.py)
                        if variant_source.get('series_position') is not None and variant_source.get('series_total') is not None:
                            series_position = variant_source.get('series_position')
                            series_total = variant_source.get('series_total')
                        # Fallback: sprawdź czy jest series_number w modelu (z JSON)
                        elif variant_source.get('series_number') and '/' in str(variant_source.get('series_number')):
                            series_number_str = variant_source.get('series_number')
                            try:
                                parts = str(series_number_str).split('/')
                                if len(parts) == 2:
                                    series_position = int(parts[0])
                                    series_total = int(parts[1])
                            except (ValueError, IndexError):
                                pass
                    
                    # Parsuj release_year używając funkcji pomocniczej (obsługuje zakresy)
                    release_year = parse_release_year(variant_source.get('release_year'))
                    
                    # Sprawdź czy wariant już istnieje (po toy_number + cechach)
                    statement = select(Variant).where(
                        Variant.car_id == car_id,
                        Variant.toy_number == toy_number,
                        Variant.release_year == release_year,
                        Variant.series_name == variant_source.get('series_name'),
                        Variant.body_color == variant_source.get('body_color')
                    )
                    existing_variant = db.exec(statement).first()
                    
                    if existing_variant:
                        skipped_variants += 1
                        continue
                    
                    variant_desc = create_variant_description(variant_source)
                    is_chase = bool(variant_source.get('super_treasure_hunt') or variant_source.get('treasure_hunt'))
                    treasure_hunt = bool(variant_source.get('treasure_hunt'))
                    super_treasure_hunt = bool(variant_source.get('super_treasure_hunt'))
                    
                    if dry_run:
                        print(f"📦 [DRY RUN] Utworzyłbym wariant: {toy_number} - {variant_desc}")
                    else:
                        variants_to_insert.append({
                            'id': uuid.uuid4(),
                            'car_id': car_id,
                            'toy_number': toy_number,
                            'desc': variant_desc,
                            'is_chase': is_chase,
                            'treasure_hunt': treasure_hunt,
                            'super_treasure_hunt': super_treasure_hunt,
                            'release_year': release_year,
                            'series_name': clean_series_name(variant_source.get('series_name')),
                            'series_position': series_position,
                            'series_total': series_total,
                            'body_color': variant_source.get('body_color'),
                            'tampo': variant_source.get('tampo'),
                            'wheel_type': variant_source.get('wheel_type'),
                            'base_color': variant_source.get('base_color'),
                            'window_color': variant_source.get('window_color'),
                            'interior_color': variant_source.get('interior_color')
                        })
                        imported_variants += 1
        
        if skipped_models:
            print(f"⚠️  Pominięte modele bez model_name/page_title: {skipped_models}")
        if skipped_empty_models:
            print(f"⚠️  Pominięte modele bez wariantów z toy_number: {skipped_empty_models}")
        
        if not dry_run:
            # Bulk insert cars - użyj bulk_insert_mappings dla lepszej wydajności
            if cars_to_insert:
                db.bulk_insert_mappings(Car, cars_to_insert)
                db.commit()
                print(f"✓ Zaimportowano {imported_cars} samochodów...")
            
            # Bulk insert variants w partiach po 1000 dla lepszej wydajności
            batch_size = 1000
            for i in range(0, len(variants_to_insert), batch_size):
                batch = variants_to_insert[i:i + batch_size]
                # Użyj bulk_insert_mappings dla prawdziwego bulk insert
                db.bulk_insert_mappings(Variant, batch)
                db.commit()
                print(f"✓ Zaimportowano {min(i + batch_size, len(variants_to_insert))}/{len(variants_to_insert)} wariantów...")
            
            print(f"\n✅ Import zakończony!")
            print(f"   Samochody (casting): {imported_cars}")
            print(f"   Warianty: {imported_variants}")
            print(f"   Pominięte warianty (już istniejące): {skipped_variants}")
        else:
            print(f"\n📊 [DRY RUN] Podsumowanie:")
            print(f"   Samochody do dodania: {imported_cars}")
            print(f"   Warianty do dodania: {imported_variants}")
            print(f"\nUruchom bez --dry-run aby zaimportować dane.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Import danych Hot Wheels z JSON do bazy danych')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Pokaż co zostałoby zaimportowane bez faktycznego importu')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Import danych Hot Wheels do bazy danych")
    print("=" * 60)
    
    if args.dry_run:
        print("\n🔍 Tryb DRY RUN - żadne dane nie zostaną zmienione\n")
    
    import_data(dry_run=args.dry_run)
