#!/usr/bin/env python3
"""
Script to download all Hot Wheels models from MediaWiki API.
Extracts infobox data containing model information.
"""

import requests
import json
import time
import re
import html
from typing import Dict, List, Optional, Any
from pathlib import Path

# MediaWiki API endpoint for Hot Wheels Fandom wiki
BASE_URL = "https://hotwheels.fandom.com/api.php"

# Output file - new file for fresh download, old file stays as backup
OUTPUT_FILE = Path(__file__).parent / "hotwheels_models_new1.json"
OUTPUT_FILE_NEW = Path(__file__).parent / "hotwheels_models_new2.json"

def get_wiki_statistics() -> Dict[str, int]:
    """Get wiki statistics to verify we got all pages."""
    params = {
        "action": "query",
        "format": "json",
        "meta": "siteinfo",
        "siprop": "statistics",
    }
    try:
        response = requests.get(BASE_URL, params=params, timeout=60)  # Increased timeout
        response.raise_for_status()
        data = response.json()
        if "query" in data and "statistics" in data["query"]:
            return data["query"]["statistics"]
    except Exception as e:
        print(f"Warning: Could not fetch wiki statistics: {e}")
    return {}

def get_all_pages() -> List[str]:
    """
    Get all page titles from the Hot Wheels wiki.
    Uses allpages API which is the most reliable method to get ALL pages.
    Verifies completeness by comparing with wiki statistics.
    """
    print("=" * 60)
    print("Fetching ALL page titles from Hot Wheels wiki...")
    print("=" * 60)
    
    # Get wiki statistics first
    stats = get_wiki_statistics()
    expected_pages = stats.get("articles", 0)
    if expected_pages:
        print(f"Wiki statistics: {expected_pages} articles expected")
    
    all_pages = []
    continue_token = None
    request_count = 0
    
    # Use allpages as primary method (most reliable - gets EVERYTHING)
    print("\nUsing 'allpages' API (most comprehensive method)...")
    params = {
        "action": "query",
        "format": "json",
        "list": "allpages",
        "aplimit": "max",  # 500 pages per request (maximum allowed)
        "apnamespace": "0",  # Main namespace only (excludes talk pages, categories, etc.)
        "apfilterredir": "nonredirects",
    }
    
    while True:
        if continue_token:
            params["apcontinue"] = continue_token
        
        try:
            request_count += 1
            response = requests.get(BASE_URL, params=params, timeout=60)  # Increased timeout
            response.raise_for_status()
            data = response.json()
            
            if "query" in data and "allpages" in data["query"]:
                pages = data["query"]["allpages"]
                new_pages = [page["title"] for page in pages]
                all_pages.extend(new_pages)
                
                # Remove duplicates (shouldn't happen, but just in case)
                unique_count = len(set(all_pages))
                
                print(f"[Request {request_count}] Fetched {len(new_pages)} pages (total unique: {unique_count})", end="")
                
                # Show progress percentage if we know expected count
                if expected_pages:
                    percentage = (unique_count / expected_pages) * 100
                    print(f" - {percentage:.1f}% complete")
                else:
                    print()
                
                # Check for continue token
                if "continue" in data:
                    if "apcontinue" in data["continue"]:
                        continue_token = data["continue"]["apcontinue"]
                    else:
                        # Check for new continue format
                        continue_token = data["continue"].get("apcontinue")
                        if not continue_token:
                            break
                else:
                    # No continue token means we got all pages
                    break
            else:
                # No pages in response - might be an error
                if "error" in data:
                    print(f"API Error: {data['error']}")
                break
                
        except requests.exceptions.RequestException as e:
            print(f"\n❌ Network error fetching pages: {e}")
            print(f"   Retrying in 2 seconds...")
            time.sleep(1)  # Reduced from 2 seconds
            continue
        except Exception as e:
            print(f"\n❌ Error fetching pages: {e}")
            import traceback
            traceback.print_exc()
            break
        
        time.sleep(0.1)  # Reduced delay for faster processing
    
    # Remove duplicates (final cleanup)
    all_pages = list(set(all_pages))
    
    print(f"\n" + "=" * 60)
    print(f"✅ Fetching complete!")
    print(f"   Total unique pages found: {len(all_pages)}")
    print(f"   Total API requests made: {request_count}")
    
    # Verify completeness
    if expected_pages:
        if len(all_pages) >= expected_pages * 0.95:  # Allow 5% margin (some pages might be redirects, etc.)
            print(f"   ✅ Verification: Got {len(all_pages)}/{expected_pages} pages ({len(all_pages)/expected_pages*100:.1f}%)")
            print(f"   ✅ This looks complete!")
        elif len(all_pages) < expected_pages * 0.9:
            print(f"   ⚠️  Warning: Got {len(all_pages)}/{expected_pages} pages ({len(all_pages)/expected_pages*100:.1f}%)")
            print(f"   ⚠️  This might be incomplete - check for errors above")
        else:
            print(f"   ⚠️  Got {len(all_pages)}/{expected_pages} pages ({len(all_pages)/expected_pages*100:.1f}%)")
            print(f"   ⚠️  Close to complete, but might be missing some pages")
    
    # Also try to get pages from categories (as supplement - but allpages should be enough)
    print(f"\nSupplementing with pages from categories (optional)...")
    category_pages = get_pages_from_categories()
    before_count = len(all_pages)
    all_pages.extend(category_pages)
    all_pages = list(set(all_pages))  # Remove duplicates
    added_from_categories = len(all_pages) - before_count
    
    if added_from_categories > 0:
        print(f"   Added {added_from_categories} additional pages from categories")
    else:
        print(f"   No additional pages from categories (allpages already got everything)")
    
    print(f"\n📊 Final count: {len(all_pages)} unique pages")
    print("=" * 60)
    
    return all_pages


def get_page_content(title: str) -> Optional[Dict[str, Any]]:
    """
    Get parsed content of a page, including infobox data.
    """
    params = {
        "action": "parse",
        "format": "json",
        "page": title,
        "prop": "wikitext|text",
        "disabletoc": "1",
        "redirects": "1"
    }
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=60)  # Increased timeout
        response.raise_for_status()
        data = response.json()
        
        if "parse" in data:
            return data["parse"]
        elif "error" in data:
            # Page might not exist or be inaccessible
            return None
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page '{title}': {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching page '{title}': {e}")
        return None


def extract_infobox_data(wikitext: str, html_text: str = "") -> Dict[str, Any]:
    """
    Extract infobox data from wikitext and HTML.
    Hot Wheels uses portable infoboxes with templates like {{casting|...}} or {{Infobox Hot Wheels|...}}
    """
    infobox_data = {}
    
    # First, try to extract from HTML (more reliable for portable infoboxes)
    if html_text:
        infobox_data = extract_from_html_infobox(html_text)
        if infobox_data:
            return infobox_data
    
    # Fallback to wikitext extraction
    if wikitext:
        infobox_data = extract_from_wikitext(wikitext)
    
    return infobox_data


def extract_from_html_infobox(html_text: str) -> Dict[str, Any]:
    """
    Extract infobox data from HTML portable infobox.
    Portable infoboxes use <aside class="portable-infobox"> with data-source attributes.
    """
    infobox_data = {}
    
    # Find portable infobox (can be <aside> or <div>)
    patterns = [
        r'<aside[^>]*class="[^"]*portable-infobox[^"]*"[^>]*>(.*?)</aside>',
        r'<div[^>]*class="[^"]*portable-infobox[^"]*"[^>]*>(.*?)</div>',
        r'<table[^>]*class="[^"]*infobox[^"]*"[^>]*>(.*?)</table>',
    ]
    
    infobox_html = None
    for pattern in patterns:
        match = re.search(pattern, html_text, re.IGNORECASE | re.DOTALL)
        if match:
            infobox_html = match.group(1)
            break
    
    if not infobox_html:
        return infobox_data
    
    # Extract name from h2 with data-source="name"
    name_match = re.search(r'<h2[^>]*data-source="name"[^>]*>(.*?)</h2>', infobox_html, re.IGNORECASE | re.DOTALL)
    if name_match:
        name = re.sub(r'<[^>]+>', '', name_match.group(1)).strip()
        if name:
            infobox_data['name'] = name
    
    # Extract data items with data-source attributes
    # Format: <div class="pi-item pi-data" data-source="field_name">...</div>
    data_pattern = r'<div[^>]*class="[^"]*pi-data[^"]*"[^>]*data-source="([^"]+)"[^>]*>.*?<div[^>]*class="[^"]*pi-data-value[^"]*"[^>]*>(.*?)</div>'
    data_matches = re.findall(data_pattern, infobox_html, re.IGNORECASE | re.DOTALL)
    
    for field_name, field_value in data_matches:
        # Clean HTML from value
        value = re.sub(r'<[^>]+>', '', field_value).strip()
        # Remove links but keep text: <a href="...">text</a> -> text
        value = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', value)
        # Decode HTML entities
        value = html.unescape(value)
        # Clean up whitespace
        value = ' '.join(value.split())
        
        if value:
            # Normalize field name
            field_name = field_name.lower().strip()
            infobox_data[field_name] = value
    
    # Also try to extract label-value pairs (for older infobox format)
    if not infobox_data:
        # Pattern: <h3 class="pi-data-label">Label</h3> followed by <div class="pi-data-value">Value</div>
        label_value_pattern = r'<h3[^>]*class="[^"]*pi-data-label[^"]*"[^>]*>(.*?)</h3>.*?<div[^>]*class="[^"]*pi-data-value[^"]*"[^>]*>(.*?)</div>'
        label_matches = re.findall(label_value_pattern, infobox_html, re.IGNORECASE | re.DOTALL)
        
        for label, value in label_matches:
            label_clean = re.sub(r'<[^>]+>', '', label).strip().lower().replace(' ', '_')
            value_clean = re.sub(r'<[^>]+>', '', value).strip()
            value_clean = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', value_clean)
            # Decode HTML entities
            value_clean = html.unescape(value_clean)
            value_clean = ' '.join(value_clean.split())
            
            if label_clean and value_clean:
                infobox_data[label_clean] = value_clean
    
    return infobox_data


def extract_from_wikitext(wikitext: str) -> Dict[str, Any]:
    """
    Extract infobox data from wikitext templates.
    Handles both {{Infobox Hot Wheels|...}} and {{casting|...}} formats.
    """
    infobox_data = {}
    
    # Try different infobox template patterns
    patterns = [
        r'\{\{casting\|([^}]+)\}\}',  # {{casting|name=...|series=...}}
        r'\{\{Infobox[^|]*Hot[^}]*Wheels\|([^}]+)\}\}',  # {{Infobox Hot Wheels|...}}
        r'\{\{Infobox[^|]*\|([^}]+)\}\}',  # {{Infobox|...}}
    ]
    
    infobox_content = None
    for pattern in patterns:
        match = re.search(pattern, wikitext, re.IGNORECASE | re.DOTALL)
        if match:
            infobox_content = match.group(1)
            break
    
    if not infobox_content:
        return infobox_data
    
    # Extract key=value pairs
    # Format: key=value or |key=value
    param_pattern = r'(?:^|\|)\s*([^=]+?)\s*=\s*([^|]+?)(?=\||$)'
    params = re.findall(param_pattern, infobox_content, re.IGNORECASE | re.MULTILINE)
    
    for key, value in params:
        key = key.strip().lower().replace(' ', '_').replace('-', '_')
        value = clean_wikitext_value(value.strip())
        
        if value:
            infobox_data[key] = value
    
    return infobox_data


def clean_wikitext_value(value: str) -> str:
    """
    Clean wikitext markup from a value.
    """
    if not value:
        return ""
    
    # Decode HTML entities
    value = html.unescape(value)
    
    # Remove wikitext links [[link|text]] or [[text]]
    value = re.sub(r'\[\[([^\]]+?)(?:\|([^\]]+?))?\]\]', lambda m: m.group(2) or m.group(1), value)
    
    # Remove templates {{template|params}}
    value = re.sub(r'\{\{[^}]*\}\}', '', value)
    
    # Remove HTML tags
    value = re.sub(r'<[^>]+>', '', value)
    
    # Remove file/image links
    value = re.sub(r'\[\[(File|Image):[^\]]+\]\]', '', value, re.IGNORECASE)
    
    # Remove external links [url text]
    value = re.sub(r'\[https?://[^\s]+\s+([^\]]+)\]', r'\1', value)
    
    # Remove bold/italic markup
    value = re.sub(r"'''(.*?)'''", r'\1', value)  # Bold
    value = re.sub(r"''(.*?)''", r'\1', value)  # Italic
    
    # Clean up whitespace
    value = ' '.join(value.split())
    
    return value.strip()


def _strip_html(text: str) -> str:
    text = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    return ' '.join(text.split()).strip()


def extract_description(html_text: str) -> Optional[str]:
    """
    Extract description text from the page.
    Use the first contiguous paragraphs before the first heading.
    """
    # Prefer content area to avoid nav/infobox noise
    content_match = re.search(
        r'<div[^>]*class="[^"]*mw-parser-output[^"]*"[^>]*>(.*?)</div>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    content_html = content_match.group(1) if content_match else html_text

    # Walk through paragraphs and headings in order
    tag_pattern = r'<(p|h2|h3|h4)[^>]*>(.*?)</\1>'
    description_parts = []
    for match in re.finditer(tag_pattern, content_html, re.IGNORECASE | re.DOTALL):
        tag = match.group(1).lower()
        inner = match.group(2)
        if tag != "p":
            # Stop at first heading once we collected any description
            if description_parts:
                break
            continue

        text = _strip_html(inner)
        # Skip if too short or contains only links/images
        if len(text) <= 50 or re.match(r'^\[.*\]$', text):
            continue

        description_parts.append(text)

    if description_parts:
        return "\n\n".join(description_parts)

    return None


def _cell_text(cell_html: str, br_separator: str = " ") -> str:
    # Preserve line breaks for better splitting in base/notes columns
    cell_html = re.sub(r'<br\s*/?>', br_separator, cell_html, flags=re.IGNORECASE)
    return _strip_html(cell_html)


def extract_versions_table(html_text: str) -> List[Dict[str, Any]]:
    """
    Extract all versions/variants from the Versions table on the wiki page.
    Returns a list of version dictionaries, each with its own toy_number and details.
    """
    versions = []
    
    # First, find section containing "Versions" - can be h2, h3, or just text
    # Look for table that contains "Toy #" in header (most reliable indicator)
    # Strategy: Find all tables, then check which one has "Toy #" in header
    
    # Find all tables in HTML
    all_tables = re.findall(r'<table[^>]*>(.*?)</table>', html_text, re.IGNORECASE | re.DOTALL)
    
    table_html = None
    for table in all_tables:
        # Look for any row that contains "Toy #" in header or data cells
        for header_match in re.finditer(r'<tr[^>]*>(.*?)</tr>', table, re.IGNORECASE | re.DOTALL):
            header = header_match.group(1)
            if re.search(r'Toy\s*#|Toy&nbsp;#|Toy\s*No\.?|Model\s*#|Sku', header, re.IGNORECASE):
                table_html = table
                break
        if table_html:
            break
    
    if not table_html:
        return versions
    
    # Extract table rows
    row_pattern = r'<tr[^>]*>(.*?)</tr>'
    rows = re.findall(row_pattern, table_html, re.IGNORECASE | re.DOTALL)
    
    if len(rows) < 2:  # Need at least header + 1 data row
        return versions

    # Find header row (first row containing "Toy #")
    header_row_index = 0
    for i, row in enumerate(rows):
        if re.search(r'Toy\s*#|Toy&nbsp;#|Toy\s*No\.?|Model\s*#|Sku', row, re.IGNORECASE):
            header_row_index = i
            break

    header_row = rows[header_row_index]
    header_cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', header_row, re.IGNORECASE | re.DOTALL)
    headers = []
    for cell in header_cells:
        header_text = _cell_text(cell, br_separator=" ")
        headers.append(header_text.lower())

    def normalize_header(text: str) -> str:
        text = text.lower()
        text = text.replace("&nbsp;", " ")
        text = re.sub(r'[\s/]+', ' ', text)
        text = re.sub(r'[^a-z0-9# ]+', '', text)
        return text.strip()

    normalized_headers = [normalize_header(h) for h in headers]
    
    # Find column indices for important fields
    toy_num_idx = None
    year_idx = None
    series_idx = None
    color_idx = None
    tampo_idx = None
    wheel_idx = None
    base_idx = None
    window_idx = None
    interior_idx = None
    col_idx = None
    country_idx = None
    notes_idx = None
    photo_idx = None
    
    for i, header in enumerate(normalized_headers):
        # Check more specific headers first to avoid false matches
        if 'interior' in header:
            interior_idx = i
        elif 'window' in header:
            window_idx = i
        elif 'base' in header and 'code' not in header:
            base_idx = i
        elif ('col' in header and '#' in header) or 'collector' in header:
            col_idx = i
        elif 'country' in header:
            country_idx = i
        elif 'notes' in header:
            notes_idx = i
        elif 'photo' in header:
            photo_idx = i
        elif 'toy' in header or ('#' in header and 'col' not in header):
            toy_num_idx = i
        elif 'year' in header:
            year_idx = i
        elif 'series' in header:
            series_idx = i
        elif 'color' in header and 'base' not in header and 'window' not in header and 'interior' not in header:
            color_idx = i
        elif 'tampo' in header:
            tampo_idx = i
        elif 'wheel' in header:
            wheel_idx = i
    
    # Extract data rows
    for row in rows[header_row_index + 1:]:  # Skip header
        cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.IGNORECASE | re.DOTALL)
        if not cells:
            continue
        
        version = {}
        
        # Extract toy number (most important)
        if toy_num_idx is not None and toy_num_idx < len(cells):
            toy_num = _cell_text(cells[toy_num_idx], br_separator=" ")
            if toy_num and toy_num != '-':
                version['toy_number'] = toy_num.upper().replace(' ', '')
            else:
                continue  # Skip versions without toy number
        else:
            continue  # Must have toy number
        
        # Extract other fields
        if year_idx is not None and year_idx < len(cells):
            year = _cell_text(cells[year_idx], br_separator=" ")
            version['year'] = year
        
        if series_idx is not None and series_idx < len(cells):
            series = _cell_text(cells[series_idx], br_separator=" ")
            
            # Extract series_position and series_total from series_name (format: "Series Name5/5" or "Series Name 5/5")
            series_position = None
            series_total = None
            series_cleaned = series
            
            # Try to find pattern like "5/5" or " 5/5" at the end
            series_number_match = re.search(r'(\d+)/(\d+)\s*$', series)
            if series_number_match:
                try:
                    series_position = int(series_number_match.group(1))
                    series_total = int(series_number_match.group(2))
                    # Remove the number from series name
                    series_cleaned = re.sub(r'\d+/\d+\s*$', '', series).strip()
                except (ValueError, IndexError):
                    pass
            
            version['series'] = series_cleaned
            version['series_position'] = series_position
            version['series_total'] = series_total
        
        if color_idx is not None and color_idx < len(cells):
            color = _cell_text(cells[color_idx], br_separator=" ")
            version['body_color'] = color if color and color != '-' else None
        
        if tampo_idx is not None and tampo_idx < len(cells):
            tampo = _cell_text(cells[tampo_idx], br_separator=" ")
            version['tampo'] = tampo if tampo and tampo != '-' else None
        
        if wheel_idx is not None and wheel_idx < len(cells):
            wheel = _cell_text(cells[wheel_idx], br_separator=" ")
            version['wheel_type'] = wheel if wheel and wheel != '-' else None
        
        if base_idx is not None and base_idx < len(cells):
            base = _cell_text(cells[base_idx], br_separator=" / ")
            base_unescaped = base if base and base != '-' else None
            
            # Split "Base Color / Type" into base_color and base_material
            # Format: "Black matte / Metal" or "ZAMAC" or "Black / Metal"
            if base_unescaped:
                # Try to split by "/" or "/" with spaces
                base_parts = re.split(r'\s*/\s*', base_unescaped, maxsplit=1)
                if len(base_parts) == 2:
                    version['base_color'] = base_parts[0].strip() if base_parts[0].strip() else None
                    version['base_material'] = base_parts[1].strip() if base_parts[1].strip() else None
                else:
                    # No "/" found - assume it's just base_color
                    version['base_color'] = base_unescaped
                    version['base_material'] = None
            else:
                version['base_color'] = None
                version['base_material'] = None
        
        if window_idx is not None and window_idx < len(cells):
            window = _cell_text(cells[window_idx], br_separator=" ")
            version['window_color'] = window if window and window != '-' else None
        
        if interior_idx is not None and interior_idx < len(cells):
            interior = _cell_text(cells[interior_idx], br_separator=" ")
            version['interior_color'] = interior if interior and interior != '-' else None
        
        if col_idx is not None and col_idx < len(cells):
            col_num = _cell_text(cells[col_idx], br_separator=" ")
            version['collector_number'] = col_num if col_num and col_num != '-' else None
        
        if country_idx is not None and country_idx < len(cells):
            country = _cell_text(cells[country_idx], br_separator=" ")
            version['country'] = country if country and country != '-' else None
        
        if notes_idx is not None and notes_idx < len(cells):
            notes = _cell_text(cells[notes_idx], br_separator=" / ")
            version['notes'] = notes if notes and notes != '-' else None
            
            # Extract base_code from notes if present (format: "Base code(s): K29, K30" or "Base code(s): F13, F14, F15")
            if notes:
                # Try "Base code(s):" pattern first
                base_code_match = re.search(r'[Bb]ase\s+code[s]?\(?s\)?[:\s]+([A-Z0-9-]+(?:\s*,\s*[A-Z0-9-]+)*)', notes, re.IGNORECASE)
                if not base_code_match:
                    # Try "Production code(s):" pattern
                    base_code_match = re.search(r'[Pp]roduction\s+code[s]?\(?s\)?[:\s]+([A-Z0-9-]+(?:\s*,\s*[A-Z0-9-]+)*)', notes, re.IGNORECASE)
                
                if base_code_match:
                    base_codes = base_code_match.group(1).strip()
                    # Clean up: remove extra spaces, keep commas
                    base_codes = re.sub(r'\s+', ' ', base_codes)
                    version['base_code'] = base_codes if base_codes else None
                else:
                    version['base_code'] = None
            else:
                version['base_code'] = None
        
        if photo_idx is not None and photo_idx < len(cells):
            photo = _cell_text(cells[photo_idx], br_separator=" ")
            # Extract image URL if present
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', cells[photo_idx], re.IGNORECASE)
            if img_match:
                version['photo'] = html.unescape(img_match.group(1))
            else:
                # Try to extract link
                link_match = re.search(r'<a[^>]+href=["\']([^"\']+)["\']', cells[photo_idx], re.IGNORECASE)
                if link_match:
                    version['photo'] = html.unescape(link_match.group(1))
                else:
                    version['photo'] = html.unescape(photo) if photo and photo != '-' else None
        
        if version:
            versions.append(version)
    
    return versions


def normalize_model_data(infobox_data: Dict[str, Any], page_title: str) -> Dict[str, Any]:
    """
    Normalize and structure the infobox data into a consistent format.
    """
    model = {
        "page_title": page_title,
        "model_name": None,
        "release_year": None,
        "toy_number": None,
        "collector_number": None,
        "series_name": None,
        "series_number": None,
        "series_position": None,
        "series_total": None,
        "sub_series": None,
        "body_color": None,
        "tampo": None,
        "wheel_type": None,
        "base_color": None,
        "base_material": None,
        "window_color": None,
        "interior_color": None,
        "treasure_hunt": False,
        "super_treasure_hunt": False,
        "exclusive": None,
        "country": None,
        "notes": None,
        "base_code": None,
        "description": None,
        "raw_infobox": infobox_data
    }
    
    # Map various possible keys to standard fields
    # Note: HTML infobox uses data-source attributes like "series", "number", "years", "designer"
    key_mappings = {
        "model_name": ["name", "model_name", "casting_name", "title", "car_name"],
        "release_year": ["year", "release_year", "released", "release", "years", "produced"],
        "toy_number": ["toy_number", "toy#", "toy", "sku", "code", "model_code", "number"],
        "collector_number": ["collector_number", "collector#", "collector", "card_number", "col#"],
        "series_name": ["series", "series_name", "line", "debut_series"],
        "series_number": ["series_number", "series#", "number_in_series"],
        "sub_series": ["sub_series", "assortment", "type", "category"],
        "body_color": ["body_color", "color", "paint", "paint_color"],
        "tampo": ["tampo", "graphics", "decals", "decals_tampo"],
        "wheel_type": ["wheel_type", "wheels", "wheel", "rims"],
        "base_color": ["base_color", "base", "chassis_color"],
        "base_material": ["base_material", "chassis", "chassis_material"],
        "window_color": ["window_color", "windows", "window"],
        "interior_color": ["interior_color", "interior"],
        "exclusive": ["exclusive", "retailer", "store_exclusive"],
        "designer": ["designer", "designer_name"]  # Additional field from infobox
    }
    
    for standard_key, possible_keys in key_mappings.items():
        # Skip if already set (for fields that might be set elsewhere)
        if model.get(standard_key):
            continue
            
        for possible_key in possible_keys:
            # Try exact match
            if possible_key in infobox_data:
                value = infobox_data[possible_key]
                if value:
                    model[standard_key] = value
                    break
            
            # Try case-insensitive match
            for key in infobox_data.keys():
                if key.lower() == possible_key.lower():
                    value = infobox_data[key]
                    if value:
                        model[standard_key] = value
                        break
            # Check if we found a value
            if model.get(standard_key):
                break
    
    # Special handling for boolean fields
    th_keys = ["treasure_hunt", "th", "treasure", "is_th"]
    sth_keys = ["super_treasure_hunt", "sth", "super_th", "is_sth", "$th"]
    
    for key in th_keys:
        if key in infobox_data:
            value = str(infobox_data[key]).lower()
            if value in ["yes", "true", "1", "y"]:
                model["treasure_hunt"] = True
                break
    
    for key in sth_keys:
        if key in infobox_data:
            value = str(infobox_data[key]).lower()
            if value in ["yes", "true", "1", "y"]:
                model["super_treasure_hunt"] = True
                break
    
    # Extract year from "years" or "produced" field (e.g., "2005 - 2020" -> extract first year)
    if not model["release_year"] and ("years" in infobox_data or "produced" in infobox_data):
        years_str = infobox_data.get("years") or infobox_data.get("produced", "")
        # Extract first year from range like "2005 - 2020" or just "2005"
        year_match = re.search(r'(\d{4})', str(years_str))
        if year_match:
            model["release_year"] = year_match.group(1)
    
    # If release_year was set from "years" field, update it to extract just first year
    if model["release_year"] and (" - " in str(model["release_year"]) or "–" in str(model["release_year"])):
        year_match = re.search(r'(\d{4})', str(model["release_year"]))
        if year_match:
            model["release_year"] = year_match.group(1)
    
    # If no model_name found, use page title
    if not model["model_name"]:
        model["model_name"] = page_title
    
    return model


def download_all_models():
    """
    Main function to download all Hot Wheels models.
    Optimized for speed with reduced delays and better progress tracking.
    """
    import time as time_module
    start_total = time_module.time()
    start_time = None  # Will be set on first iteration
    
    print("=" * 60)
    print("Starting Hot Wheels model download (OPTIMIZED)")
    print("=" * 60)
    print(f"Output file (NEW): {OUTPUT_FILE_NEW}")
    if OUTPUT_FILE.exists():
        print(f"Old file (backup): {OUTPUT_FILE} (will remain untouched)")
    print(f"Optimizations: Reduced delays (0.1s), batch saves (every 100 pages)")
    print()
    
    # Get all pages
    all_pages = get_all_pages()
    
    if not all_pages:
        print("Error: Could not fetch any pages.")
        return
    
    print(f"\n{'='*60}")
    print(f"Processing {len(all_pages)} pages...")
    print(f"{'='*60}\n")
    
    models = []
    processed = 0
    errors = 0
    skipped = 0
    variants_total = 0
    
    # Start fresh - use new file, old file stays as backup
    existing_titles = set()  # Start fresh - no resume
    if OUTPUT_FILE.exists():
        print(f"ℹ️  Old file {OUTPUT_FILE.name} exists and will remain as backup")
        print(f"   New data will be saved to {OUTPUT_FILE_NEW.name}")
    else:
        print("   Starting fresh download")
    
    for i, page_title in enumerate(all_pages, 1):
        # Skip if already processed (only if resume is enabled)
        if page_title in existing_titles:
            skipped += 1
            if i % 100 == 0:
                print(f"[{i}/{len(all_pages)}] Skipped {skipped} already processed...")
            continue
        
        # Initialize start time on first iteration
        if i == 1:
            start_time = time_module.time()
        
        # Progress logging (less frequent for speed)
        if i % 25 == 0:
            elapsed = time_module.time() - start_time if 'start_time' in locals() else 0
            rate = i / (elapsed / 60) if elapsed > 0 else 0
            eta_minutes = (len(all_pages) - i) / rate if rate > 0 else 0
            print(f"[{i}/{len(all_pages)}] {i/len(all_pages)*100:.1f}% | "
                  f"Rate: {rate:.1f} pages/min | "
                  f"ETA: {eta_minutes:.0f} min | "
                  f"Processing: {page_title[:40]}...")
        
        page_data = get_page_content(page_title)
        
        if page_data:
            actual_title = page_data.get("title")
            if actual_title and actual_title != page_title:
                page_title = actual_title

            wikitext = page_data.get("wikitext", {}).get("*", "")
            html_text = page_data.get("text", {}).get("*", "")
            
            infobox_data = extract_infobox_data(wikitext, html_text)
            
            # Extract description from page text
            description = extract_description(html_text)
            
            # Extract versions/variants from the Versions table
            versions = extract_versions_table(html_text)
            
            if versions:
                # Create a separate model entry for each version
                base_model = normalize_model_data(infobox_data, page_title)
                if description:
                    base_model['description'] = description
                
                for version in versions:
                    # Create a model entry for this version
                    version_model = base_model.copy()
                    # Override with version-specific data
                    version_model['toy_number'] = version.get('toy_number')
                    version_model['release_year'] = version.get('year') or version_model.get('release_year')
                    version_model['series_name'] = version.get('series') or version_model.get('series_name')
                    version_model['series_position'] = version.get('series_position')
                    version_model['series_total'] = version.get('series_total')
                    version_model['body_color'] = version.get('body_color') or version_model.get('body_color')
                    version_model['tampo'] = version.get('tampo') or version_model.get('tampo')
                    version_model['wheel_type'] = version.get('wheel_type') or version_model.get('wheel_type')
                    version_model['base_color'] = version.get('base_color') or version_model.get('base_color')
                    version_model['base_material'] = version.get('base_material') or version_model.get('base_material')
                    version_model['window_color'] = version.get('window_color') or version_model.get('window_color')
                    version_model['interior_color'] = version.get('interior_color') or version_model.get('interior_color')
                    version_model['collector_number'] = version.get('collector_number') or version_model.get('collector_number')
                    version_model['country'] = version.get('country')
                    version_model['notes'] = version.get('notes')
                    version_model['base_code'] = version.get('base_code')
                    
                    # Add version info to raw_infobox
                    if 'versions' not in version_model['raw_infobox']:
                        version_model['raw_infobox']['versions'] = []
                    version_model['raw_infobox']['versions'].append(version)
                    
                    models.append(version_model)
                    processed += 1
            elif infobox_data:
                # No versions table, but has infobox - use single model
                model = normalize_model_data(infobox_data, page_title)
                if description:
                    model['description'] = description
                models.append(model)
                processed += 1
            else:
                # Even if no infobox, save basic info
                model = normalize_model_data({}, page_title)
                if description:
                    model['description'] = description
                models.append(model)
                errors += 1
        else:
            errors += 1
        
        # Save progress every 100 pages (optimized for speed)
        if i % 100 == 0:
            save_models(models, OUTPUT_FILE_NEW)
            elapsed = time_module.time() - start_time if 'start_time' in locals() else 0
            rate = i / (elapsed / 60) if elapsed > 0 else 0
            variants_count = sum(1 for m in models if m.get('toy_number'))
            eta_minutes = (len(all_pages) - i) / rate if rate > 0 else 0
            print(f"💾 Saved: {len(models)} models ({variants_count} variants) | "
                  f"Rate: {rate:.1f} pages/min | "
                  f"ETA: {eta_minutes:.0f} min")
        
        time.sleep(0.1)  # Reduced delay for faster processing (was 0.3)
    
    # Final save to new file
    save_models(models, OUTPUT_FILE_NEW)
    
    total_time = time_module.time() - start_total
    variants_total = sum(1 for m in models if m.get('toy_number'))
    
    print(f"\n{'='*60}")
    print(f"✅ Download complete!")
    print(f"{'='*60}")
    print(f"Total pages processed: {len(all_pages)}")
    print(f"Models with infobox data: {processed}")
    print(f"Models without infobox: {errors}")
    print(f"Skipped (already processed): {skipped}")
    print(f"Total models saved: {len(models)}")
    print(f"Total variants (with toy_number): {variants_total}")
    print(f"Total time: {total_time/60:.1f} minutes ({total_time/3600:.2f} hours)")
    print(f"Average rate: {len(all_pages)/(total_time/60):.1f} pages/minute")
    print(f"Output saved to: {OUTPUT_FILE_NEW}")
    if OUTPUT_FILE.exists():
        print(f"Old file preserved as backup: {OUTPUT_FILE}")
    print(f"{'='*60}")
    print(f"\n💡 Next steps:")
    print(f"   1. Review the new file: {OUTPUT_FILE_NEW.name}")
    print(f"   2. If everything looks good, replace old file:")
    print(f"      mv {OUTPUT_FILE.name} {OUTPUT_FILE.name}.old")
    print(f"      mv {OUTPUT_FILE_NEW.name} {OUTPUT_FILE.name}")
    print(f"{'='*60}")


def get_pages_from_categories() -> List[str]:
    """
    Get pages from specific Hot Wheels categories.
    Uses cmtype=page to get only pages (not subcategories).
    """
    categories = [
        "Category:Hot Wheels",
        "Category:Mainline",
        "Category:Premium",
        "Category:Treasure Hunt",
        "Category:Super Treasure Hunt",
        "Category:Castings",
        "Category:Hot Wheels by Year"
    ]
    
    all_pages = []
    
    for category in categories:
        continue_token = None
        category_pages = []
        
        while True:
            params = {
                "action": "query",
                "format": "json",
                "list": "categorymembers",
                "cmtitle": category,
                "cmlimit": "max",
                "cmnamespace": "0",
                "cmtype": "page"  # Only get pages, not subcategories
            }
            
            if continue_token:
                params["cmcontinue"] = continue_token
            
            try:
                response = requests.get(BASE_URL, params=params, timeout=60)  # Increased timeout
                response.raise_for_status()
                data = response.json()
                
                if "query" in data and "categorymembers" in data["query"]:
                    pages = data["query"]["categorymembers"]
                    new_pages = [page["title"] for page in pages if page.get("ns") == 0]  # Only main namespace
                    category_pages.extend(new_pages)
                    
                    if len(category_pages) > 0 and len(category_pages) % 100 == 0:
                        print(f"  {category}: {len(category_pages)} pages so far...")
                    
                    if "continue" in data and "cmcontinue" in data["continue"]:
                        continue_token = data["continue"]["cmcontinue"]
                    else:
                        break
                elif "error" in data:
                    # Category might not exist or be empty - that's OK
                    break
                else:
                    break
            except requests.exceptions.RequestException as e:
                # Network error - skip this category
                break
            except Exception as e:
                # Unexpected error - skip this category
                break
            
            time.sleep(0.1)  # Reduced delay
        
        if category_pages:
            print(f"  {category}: Found {len(category_pages)} pages")
        all_pages.extend(category_pages)
    
    # Remove duplicates
    all_pages = list(set(all_pages))
    if all_pages:
        print(f"Total unique pages from categories: {len(all_pages)}")
    return all_pages


def save_models(models: List[Dict[str, Any]], output_file: Path):
    """
    Save models to JSON file.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(models, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(models)} models to {output_file}")


if __name__ == "__main__":
    download_all_models()
