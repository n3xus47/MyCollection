#!/usr/bin/env python3
"""
Skrypt do importu danych Hot Wheels z hotwheels_models_new.json do bazy danych PostgreSQL.
Każdy wpis JSON = osobny Variant, Car grupuje po model_name/page_title.
Używa bulk inserts dla lepszej wydajności.
"""
import json
import sys
from pathlib import Path
from typing import Optional
from sqlmodel import Session, select, or_
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

def get_brand_from_model(model):
    """Wyciąga markę z modelu - domyślnie Hot Wheels."""
    return "Hot Wheels"

def import_data(dry_run=False):
    """Importuj dane do bazy danych. Każdy wpis JSON = osobny Variant."""
    # Wczytaj dane
    models = load_json_data()
    
    # Utwórz tabele jeśli nie istnieją
    create_db_and_tables()
    
    with Session(engine) as db:
        # Grupuj modele po model_name/page_title (dla Car)
        cars_by_name = defaultdict(list)
        
        # Najpierw przejdź przez wszystkie modele i pogrupuj po model_name/page_title
        for model in models:
            model_name = model.get('model_name') or model.get('page_title', 'Unknown')
            page_title = model.get('page_title')
            
            # Użyj model_name jako klucza, page_title jako dodatkowej informacji
            key = (model_name, page_title)
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
        
        for (model_name, page_title), models_list in cars_by_name.items():
            # Sprawdź czy Car już istnieje
            car_key = (model_name, page_title)
            if car_key not in cars_map:
                statement = select(Car).where(Car.model_name == model_name)
                if page_title:
                    statement = statement.where(or_(Car.page_title == page_title, Car.page_title.is_(None)))
                existing_car = db.exec(statement).first()
                
                if existing_car:
                    cars_map[car_key] = existing_car.id
                else:
                    # Przygotuj nowy Car do bulk insert
                    brand = get_brand_from_model(models_list[0])
                    car_id = uuid.uuid4()
                    cars_map[car_key] = car_id
                    cars_to_insert.append({
                        'id': car_id,
                        'model_name': model_name,
                        'page_title': page_title,
                        'brand': brand
                    })
                    imported_cars += 1
            
            car_id = cars_map[car_key]
            
            # Przygotuj warianty do bulk insert
            for model in models_list:
                raw_toy_number = model.get('toy_number')
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
                    # Sprawdź czy jest series_number w modelu (z JSON)
                    series_number_str = model.get('series_number')
                    if series_number_str and '/' in str(series_number_str):
                        try:
                            parts = str(series_number_str).split('/')
                            if len(parts) == 2:
                                series_position = int(parts[0])
                                series_total = int(parts[1])
                        except (ValueError, IndexError):
                            pass
                
                # Pomiń jeśli nie ma toy_number (nie możemy identyfikować bez toy_number)
                if not toy_number:
                    skipped_variants += 1
                    continue
                
                # Parsuj release_year używając funkcji pomocniczej (obsługuje zakresy)
                release_year = parse_release_year(model.get('release_year'))
                
                # Sprawdź czy wariant już istnieje (po toy_number + cechach)
                statement = select(Variant).where(
                    Variant.car_id == car_id,
                    Variant.toy_number == toy_number,
                    Variant.release_year == release_year,
                    Variant.series_name == model.get('series_name'),
                    Variant.body_color == model.get('body_color')
                )
                existing_variant = db.exec(statement).first()
                
                if existing_variant:
                    skipped_variants += 1
                    continue
                
                variant_desc = create_variant_description(model)
                is_chase = bool(model.get('super_treasure_hunt') or model.get('treasure_hunt'))
                treasure_hunt = bool(model.get('treasure_hunt'))
                super_treasure_hunt = bool(model.get('super_treasure_hunt'))
                
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
                        'series_name': clean_series_name(model.get('series_name')),
                        'series_position': series_position,
                        'series_total': series_total,
                        'body_color': model.get('body_color'),
                        'tampo': model.get('tampo'),
                        'wheel_type': model.get('wheel_type'),
                        'base_color': model.get('base_color'),
                        'window_color': model.get('window_color'),
                        'interior_color': model.get('interior_color')
                    })
                    imported_variants += 1
        
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
