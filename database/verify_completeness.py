#!/usr/bin/env python3
"""
Skrypt do weryfikacji czy wszystkie strony zostały pobrane.
Porównuje listę pobranych stron z API allpages.
"""
import requests
import json
from pathlib import Path
from typing import Set

BASE_URL = "https://hotwheels.fandom.com/api.php"
JSON_FILE = Path(__file__).parent / "hotwheels_models.json"

def get_all_pages_from_api() -> Set[str]:
    """Pobierz wszystkie strony z API allpages."""
    print("Pobieranie wszystkich stron z API...")
    all_pages = set()
    continue_token = None
    request_count = 0
    
    params = {
        "action": "query",
        "format": "json",
        "list": "allpages",
        "aplimit": "max",
        "apnamespace": "0",
    }
    
    while True:
        if continue_token:
            params["apcontinue"] = continue_token
        
        try:
            request_count += 1
            response = requests.get(BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if "query" in data and "allpages" in data["query"]:
                pages = data["query"]["allpages"]
                new_pages = {page["title"] for page in pages}
                all_pages.update(new_pages)
                
                print(f"[{request_count}] Pobrano {len(new_pages)} stron (łącznie: {len(all_pages)})")
                
                if "continue" in data and "apcontinue" in data["continue"]:
                    continue_token = data["continue"]["apcontinue"]
                else:
                    break
            else:
                break
        except Exception as e:
            print(f"Błąd: {e}")
            break
    
    return all_pages

def get_pages_from_json() -> Set[str]:
    """Pobierz listę stron z pliku JSON."""
    if not JSON_FILE.exists():
        return set()
    
    print(f"Wczytuję strony z {JSON_FILE}...")
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    pages = {model.get("page_title") for model in data if model.get("page_title")}
    return pages

def main():
    print("=" * 60)
    print("Weryfikacja Kompletności Pobranych Danych")
    print("=" * 60)
    print()
    
    # Pobierz strony z API
    api_pages = get_all_pages_from_api()
    print(f"\n✅ Z API pobrano: {len(api_pages)} stron")
    
    # Pobierz strony z JSON
    json_pages = get_pages_from_json()
    print(f"✅ Z JSON wczytano: {len(json_pages)} stron")
    
    # Porównaj
    print("\n" + "=" * 60)
    print("Porównanie:")
    print("=" * 60)
    
    missing_in_json = api_pages - json_pages
    extra_in_json = json_pages - api_pages
    
    print(f"\n📊 Statystyki:")
    print(f"   Stron w API: {len(api_pages)}")
    print(f"   Stron w JSON: {len(json_pages)}")
    print(f"   Brakujących w JSON: {len(missing_in_json)}")
    print(f"   Dodatkowych w JSON: {len(extra_in_json)}")
    
    if missing_in_json:
        print(f"\n⚠️  Brakujące strony w JSON ({len(missing_in_json)}):")
        for page in sorted(list(missing_in_json))[:20]:
            print(f"   - {page}")
        if len(missing_in_json) > 20:
            print(f"   ... i {len(missing_in_json) - 20} więcej")
    else:
        print(f"\n✅ Wszystkie strony z API są w JSON!")
    
    if extra_in_json:
        print(f"\nℹ️  Dodatkowe strony w JSON ({len(extra_in_json)}) - mogą być z kategorii:")
        for page in sorted(list(extra_in_json))[:10]:
            print(f"   - {page}")
        if len(extra_in_json) > 10:
            print(f"   ... i {len(extra_in_json) - 10} więcej")
    
    # Oblicz procent kompletności
    if api_pages:
        completeness = (len(json_pages & api_pages) / len(api_pages)) * 100
        print(f"\n📈 Kompletność: {completeness:.1f}%")
        
        if completeness >= 99.5:
            print("   ✅ Doskonała kompletność!")
        elif completeness >= 95:
            print("   ✅ Dobra kompletność")
        elif completeness >= 90:
            print("   ⚠️  Kompletność poniżej oczekiwań")
        else:
            print("   ❌ Niska kompletność - należy ponownie pobrać dane")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
