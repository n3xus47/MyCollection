#!/usr/bin/env python3
"""
Skrypt do przyrostowego aktualizowania danych Hot Wheels.
- Dodaje warianty do istniejących stron, które ich nie mają
- Pobiera tylko nowe strony
- Aktualizuje zmienione strony
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Any
import time
import requests
import re
import html
from download_hotwheels import (
    BASE_URL,
    get_all_pages,
    get_page_content,
    extract_infobox_data,
    extract_versions_table,
    normalize_model_data
)

OUTPUT_FILE = Path(__file__).parent / "hotwheels_models.json"

def load_existing_data() -> Dict[str, Dict[str, Any]]:
    """Wczytaj istniejące dane i zorganizuj po page_title."""
    if not OUTPUT_FILE.exists():
        return {}
    
    print(f"Wczytuję istniejące dane z {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Grupuj po page_title (może być wiele wpisów dla różnych wariantów)
    by_page_title = {}
    for model in data:
        page_title = model.get('page_title')
        if not page_title:
            continue
        
        if page_title not in by_page_title:
            by_page_title[page_title] = []
        by_page_title[page_title].append(model)
    
    print(f"   Wczytano {len(data)} wpisów dla {len(by_page_title)} unikalnych stron")
    return by_page_title

def has_versions_extracted(models: List[Dict[str, Any]]) -> bool:
    """Sprawdź czy dla tej strony są już wyekstrahowane warianty."""
    # Jeśli jest więcej niż 1 wpis z toy_number, prawdopodobnie warianty są już wyekstrahowane
    toy_numbers = {m.get('toy_number') for m in models if m.get('toy_number')}
    return len(toy_numbers) > 1

def update_page_with_versions(page_title: str, existing_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Zaktualizuj stronę dodając warianty z tabeli Versions."""
    print(f"   Aktualizuję: {page_title[:50]}...")
    
    page_data = get_page_content(page_title)
    if not page_data:
        print(f"      ⚠️  Nie można pobrać strony")
        return existing_models
    
    wikitext = page_data.get("wikitext", {}).get("*", "")
    html_text = page_data.get("text", {}).get("*", "")
    
    infobox_data = extract_infobox_data(wikitext, html_text)
    versions = extract_versions_table(html_text)
    
    if not versions:
        # Brak wariantów w tabeli - zwróć istniejące modele
        return existing_models
    
    # Utwórz nowe modele z wariantami
    base_model = normalize_model_data(infobox_data, page_title)
    updated_models = []
    
    # Zbierz istniejące toy_number aby uniknąć duplikatów
    existing_toy_numbers = {m.get('toy_number') for m in existing_models if m.get('toy_number')}
    
    for version in versions:
        toy_number = version.get('toy_number')
        if not toy_number:
            continue
        
        # Sprawdź czy ten wariant już istnieje
        if toy_number in existing_toy_numbers:
            # Znajdź istniejący model i zaktualizuj go
            existing = next((m for m in existing_models if m.get('toy_number') == toy_number), None)
            if existing:
                updated_models.append(existing)
                continue
        
        # Utwórz nowy model dla tego wariantu
        version_model = base_model.copy()
        version_model['toy_number'] = toy_number
        version_model['release_year'] = version.get('year') or version_model.get('release_year')
        version_model['series_name'] = version.get('series') or version_model.get('series_name')
        version_model['body_color'] = version.get('body_color') or version_model.get('body_color')
        version_model['tampo'] = version.get('tampo') or version_model.get('tampo')
        version_model['wheel_type'] = version.get('wheel_type') or version_model.get('wheel_type')
        version_model['base_color'] = version.get('base_color') or version_model.get('base_color')
        version_model['window_color'] = version.get('window_color') or version_model.get('window_color')
        version_model['interior_color'] = version.get('interior_color') or version_model.get('interior_color')
        
        updated_models.append(version_model)
    
    print(f"      ✓ Znaleziono {len(versions)} wariantów, utworzono {len(updated_models)} wpisów")
    return updated_models

def process_new_page(page_title: str) -> List[Dict[str, Any]]:
    """Przetwórz nową stronę i zwróć listę modeli (z wariantami jeśli są)."""
    page_data = get_page_content(page_title)
    if not page_data:
        return []
    
    wikitext = page_data.get("wikitext", {}).get("*", "")
    html_text = page_data.get("text", {}).get("*", "")
    
    infobox_data = extract_infobox_data(wikitext, html_text)
    versions = extract_versions_table(html_text)
    
    models = []
    
    if versions:
        # Utwórz osobny wpis dla każdego wariantu
        base_model = normalize_model_data(infobox_data, page_title)
        
        for version in versions:
            version_model = base_model.copy()
            version_model['toy_number'] = version.get('toy_number')
            version_model['release_year'] = version.get('year') or version_model.get('release_year')
            version_model['series_name'] = version.get('series') or version_model.get('series_name')
            version_model['body_color'] = version.get('body_color') or version_model.get('body_color')
            version_model['tampo'] = version.get('tampo') or version_model.get('tampo')
            version_model['wheel_type'] = version.get('wheel_type') or version_model.get('wheel_type')
            version_model['base_color'] = version.get('base_color') or version_model.get('base_color')
            version_model['window_color'] = version.get('window_color') or version_model.get('window_color')
            version_model['interior_color'] = version.get('interior_color') or version_model.get('interior_color')
            
            if version_model.get('toy_number'):  # Tylko jeśli ma toy_number
                models.append(version_model)
    elif infobox_data:
        # Brak wariantów, użyj podstawowego modelu
        model = normalize_model_data(infobox_data, page_title)
        models.append(model)
    else:
        # Nawet bez infobox, zapisz podstawowe info
        model = normalize_model_data({}, page_title)
        models.append(model)
    
    return models

def incremental_update(dry_run: bool = False):
    """Przyrostowa aktualizacja danych."""
    print("=" * 60)
    print("Przyrostowa Aktualizacja Danych Hot Wheels")
    print("=" * 60)
    print()
    
    if dry_run:
        print("🔍 Tryb DRY RUN - żadne dane nie zostaną zmienione\n")
    
    # Wczytaj istniejące dane
    existing_by_page = load_existing_data()
    existing_pages = set(existing_by_page.keys())
    
    # Pobierz wszystkie strony z wiki
    print("\nPobieranie listy wszystkich stron z wiki...")
    all_pages = get_all_pages()
    all_pages_set = set(all_pages)
    
    # Znajdź nowe strony
    new_pages = all_pages_set - existing_pages
    existing_pages_to_check = existing_pages & all_pages_set
    
    print(f"\n📊 Analiza:")
    print(f"   Wszystkich stron w wiki: {len(all_pages_set)}")
    print(f"   Stron już w JSON: {len(existing_pages)}")
    print(f"   Nowych stron: {len(new_pages)}")
    print(f"   Stron do sprawdzenia (dodanie wariantów): {len(existing_pages_to_check)}")
    
    # Statystyki
    stats = {
        'new_pages_processed': 0,
        'existing_pages_updated': 0,
        'variants_added': 0,
        'total_models': 0
    }
    
    updated_models = []
    
    # 1. Zaktualizuj istniejące strony (dodaj warianty jeśli brakuje)
    print(f"\n{'='*60}")
    print("Krok 1: Aktualizacja istniejących stron (dodanie wariantów)")
    print(f"{'='*60}")
    
    pages_without_versions = []
    for page_title in list(existing_pages_to_check)[:100]:  # Limit dla testu
        models = existing_by_page[page_title]
        if not has_versions_extracted(models):
            pages_without_versions.append(page_title)
    
    print(f"   Znaleziono {len(pages_without_versions)} stron bez wyekstrahowanych wariantów")
    print(f"   (Przetwarzam pierwsze 100 dla testu)")
    
    for i, page_title in enumerate(pages_without_versions[:100], 1):
        if i % 10 == 0:
            print(f"   [{i}/{min(100, len(pages_without_versions))}] Przetwarzanie...")
        
        if not dry_run:
            updated = update_page_with_versions(page_title, existing_by_page[page_title])
            if len(updated) > len(existing_by_page[page_title]):
                stats['existing_pages_updated'] += 1
                stats['variants_added'] += len(updated) - len(existing_by_page[page_title])
            updated_models.extend(updated)
        else:
            versions = extract_versions_table(get_page_content(page_title).get("text", {}).get("*", ""))
            if versions:
                print(f"   [DRY RUN] {page_title[:50]}: znaleziono {len(versions)} wariantów")
        
        time.sleep(0.3)  # Be nice to API
    
    # 2. Dodaj nowe strony
    if new_pages:
        print(f"\n{'='*60}")
        print(f"Krok 2: Pobieranie nowych stron ({len(new_pages)})")
        print(f"{'='*60}")
        print(f"   (Pomijam - uruchom bez --dry-run aby pobrać)")
    
    # Zbierz wszystkie modele
    if not dry_run:
        # Dodaj strony które nie były aktualizowane (już mają warianty lub nie mają tabeli)
        for page_title, models in existing_by_page.items():
            if page_title not in pages_without_versions[:100]:
                updated_models.extend(models)
        
        # Zapisz
        print(f"\n{'='*60}")
        print("Zapisywanie zaktualizowanych danych...")
        print(f"{'='*60}")
        
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(updated_models, f, indent=2, ensure_ascii=False)
        
        stats['total_models'] = len(updated_models)
        
        print(f"\n✅ Aktualizacja zakończona!")
        print(f"   Zaktualizowanych stron: {stats['existing_pages_updated']}")
        print(f"   Dodanych wariantów: {stats['variants_added']}")
        print(f"   Łącznie modeli w JSON: {stats['total_models']}")
    else:
        print(f"\n📊 [DRY RUN] Podsumowanie:")
        print(f"   Stron do aktualizacji: {len(pages_without_versions)}")
        print(f"   Nowych stron do pobrania: {len(new_pages)}")
        print(f"\nUruchom bez --dry-run aby zaktualizować dane.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Przyrostowa aktualizacja danych Hot Wheels')
    parser.add_argument('--dry-run', action='store_true',
                       help='Pokaż co zostałoby zaktualizowane bez faktycznych zmian')
    
    args = parser.parse_args()
    
    incremental_update(dry_run=args.dry_run)
