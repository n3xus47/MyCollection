from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select, desc
from typing import List, Optional
from uuid import UUID
import os
import google.generativeai as genai
from PIL import Image
import io
from dotenv import load_dotenv
from app.models import (
    get_db,
    create_db_and_tables,
    Car,
    Variant,
    UserCollection,
    IdentifyResponse,
    CarSchema,
    VariantSchema,
    AddToCollectionRequest,
    CollectionItemSchema,
    GeminiOCRResponse
)

# Load environment variables
load_dotenv()

# Configure Gemini API
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)

# Create tables
create_db_and_tables()

app = FastAPI(title="MyCollection API")

# CORS middleware for Flutter app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your Flutter app's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def normalize_toy_number(toy_number: str) -> str:
    """
    Normalizuj toy_number - spójna normalizacja używana w całym systemie.
    Format: uppercase + strip + remove spaces
    """
    if not toy_number:
        return ""
    return str(toy_number).strip().upper().replace(' ', '')

def parse_release_year(year_value) -> Optional[int]:
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
    """
    if not series_name:
        return None
    
    import re
    # Usuń końcowe cyfry i formaty ułamkowe (np. "4/5", "24/100")
    cleaned = re.sub(r'\d+/\d+$', '', series_name)  # Usuń "24/100" na końcu
    cleaned = re.sub(r'\d+$', '', cleaned)  # Usuń końcowe cyfry (np. "4" w "Turtles4")
    cleaned = cleaned.strip()
    
    return cleaned if cleaned else series_name  # Zwróć oryginał jeśli wszystko zostało usunięte

def parse_series_number(series_number_str: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """
    Parsuj series_number z formatu "238/250" do (series_position, series_total).
    Zwraca (None, None) jeśli nie można sparsować.
    """
    if not series_number_str:
        return (None, None)
    
    if '/' not in str(series_number_str):
        return (None, None)
    
    try:
        parts = str(series_number_str).split('/')
        if len(parts) == 2:
            position = int(parts[0].strip())
            total = int(parts[1].strip())
            return (position, total)
    except (ValueError, IndexError):
        pass
    
    return (None, None)

def match_variant_by_features(variants, year, series, color, series_position=None, series_total=None):
    """
    Dopasuj wariant po cechach z OCR.
    
    Args:
        variants: Lista wariantów do dopasowania
        year: release_year z OCR
        series: series_name z OCR
        color: body_color z OCR
        series_position: Pozycja w serii z OCR (z series_number)
        series_total: Całkowita liczba w serii z OCR (z series_number)
    """
    if not variants:
        return None
    
    best_match = None
    best_score = 0
    
    for variant in variants:
        score = 0
        matches = 0
        
        # Dopasowanie po roku (ważność: 30%)
        if year is not None and variant.release_year is not None:
            if year == variant.release_year:
                score += 0.3
                matches += 1
        
        # Dopasowanie po serii (ważność: 25%)
        if series and variant.series_name:
            # Czyść series_name przed porównaniem
            series_cleaned = clean_series_name(series)
            variant_series_cleaned = clean_series_name(variant.series_name)
            if series_cleaned and variant_series_cleaned:
                series_lower = series_cleaned.lower().strip()
                variant_series_lower = variant_series_cleaned.lower().strip()
                if series_lower in variant_series_lower or variant_series_lower in series_lower:
                    score += 0.25
                    matches += 1
        
        # Dopasowanie po kolorze (ważność: 20%)
        if color and variant.body_color:
            color_lower = color.lower().strip()
            variant_color_lower = variant.body_color.lower().strip()
            if color_lower in variant_color_lower or variant_color_lower in color_lower:
                score += 0.2
                matches += 1
        
        # Dopasowanie po pozycji w serii (ważność: 25%) - bardzo precyzyjne
        if series_position is not None and series_total is not None:
            if (variant.series_position == series_position and 
                variant.series_total == series_total):
                score += 0.25
                matches += 1
        
        if score > best_score:
            best_score = score
            best_match = {'variant': variant, 'score': score, 'matches': matches}
    
    return best_match


@app.get("/identify/{code}", response_model=IdentifyResponse)
async def identify_car(
    code: str,
    db: Session = Depends(get_db),
    year: Optional[int] = None,
    series: Optional[str] = None,
    color: Optional[str] = None,
    series_number: Optional[str] = None
):
    """
    Identify car by toy_number with optional variant matching.
    
    Query params (from OCR):
    - year: release_year (int)
    - series: series_name
    - color: body_color
    - series_number: series_number w formacie "238/250" (pozycja/całkowita)
    """
    # Normalize code using consistent normalization
    code_normalized = normalize_toy_number(code)
    
    # If code contains dash, extract first part (toy_number)
    if '-' in code_normalized:
        code_normalized = code_normalized.split('-')[0]
    
    # 1. Find all variants with this toy_number
    statement = select(Variant).where(Variant.toy_number == code_normalized)
    variants = db.exec(statement).all()
    
    if not variants:
        raise HTTPException(status_code=404, detail=f"Car with toy_number '{code_normalized}' not found")
    
    # Helper function to build response with car and all its variants
    def build_car_response(car_id: UUID) -> IdentifyResponse:
        """Build IdentifyResponse with car and all its variants."""
        car_stmt = select(Car).where(Car.id == car_id)
        car = db.exec(car_stmt).first()
        if not car:
            raise HTTPException(status_code=404, detail="Car not found")
        
        # Load all variants for this car in one query
        car_variants_stmt = select(Variant).where(Variant.car_id == car_id)
        car_variants = db.exec(car_variants_stmt).all()
        
        car_data = car.model_dump()
        car_data['variants'] = [VariantSchema.model_validate(v.model_dump()) for v in car_variants]
        return IdentifyResponse(car=CarSchema.model_validate(car_data))
    
    # 2. If only 1 variant → return it
    if len(variants) == 1:
        return build_car_response(variants[0].car_id)
    
    # 3. If many variants → match by features
    # Parsuj series_number jeśli jest dostępne
    series_position = None
    series_total = None
    if series_number:
        series_position, series_total = parse_series_number(series_number)
    
    best_match = match_variant_by_features(
        variants, year, series, color, series_position, series_total
    )
    
    # If we have a good match (>80%), return only that variant's car
    if best_match and best_match['score'] > 0.8:
        return build_car_response(best_match['variant'].car_id)
    
    # Return all variants for user to choose
    # Group variants by car_id to find unique cars
    unique_car_ids = {v.car_id for v in variants}
    
    if len(unique_car_ids) == 1:
        # All variants belong to same car
        return build_car_response(list(unique_car_ids)[0])
    else:
        # Variants belong to different cars - return first car with all its variants
        # This is edge case, should not happen often
        return build_car_response(variants[0].car_id)

@app.post("/collection", response_model=CollectionItemSchema)
async def add_to_collection(
    request: AddToCollectionRequest,
    db: Session = Depends(get_db)
):
    """
    Add a variant to the user's collection.
    Sprawdza czy użytkownik już ma ten wariant (zapobiega duplikatom).
    """
    # Check if variant exists
    statement = select(Variant).where(Variant.id == request.variant_id)
    variant = db.exec(statement).first()
    
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    
    # Sprawdź czy użytkownik już ma ten wariant w kolekcji (zapobieganie duplikatom)
    existing_collection = select(UserCollection).where(
        UserCollection.variant_id == request.variant_id
    )
    existing_item = db.exec(existing_collection).first()
    
    if existing_item:
        # Użytkownik już ma ten wariant - zwróć istniejący element
        db.refresh(existing_item.variant)
        db.refresh(existing_item.variant.car)
        
        return CollectionItemSchema(
            id=existing_item.id,
            variant_id=existing_item.variant_id,
            added_at=existing_item.added_at,
            variant=VariantSchema.model_validate(existing_item.variant.model_dump()),
            car=CarSchema.model_validate(existing_item.variant.car.model_dump())
        )
    
    # Create new collection item (tylko jeśli nie istnieje)
    collection_item = UserCollection(variant_id=request.variant_id)
    db.add(collection_item)
    db.commit()
    db.refresh(collection_item)
    
    # Load variant relationship
    db.refresh(collection_item.variant)
    db.refresh(collection_item.variant.car)
    
    # Build response with car info
    result = CollectionItemSchema(
        id=collection_item.id,
        variant_id=collection_item.variant_id,
        added_at=collection_item.added_at,
        variant=VariantSchema.model_validate(collection_item.variant.model_dump()),
        car=CarSchema.model_validate(collection_item.variant.car.model_dump())
    )
    
    return result

@app.get("/collection", response_model=List[CollectionItemSchema])
async def get_collection(db: Session = Depends(get_db)):
    """
    Get all items in the user's collection.
    """
    statement = select(UserCollection).order_by(desc(UserCollection.added_at))
    collection_items = db.exec(statement).all()
    
    # Load variants and cars in bulk to avoid N+1 queries
    variant_ids = [item.variant_id for item in collection_items]
    variants_stmt = select(Variant).where(Variant.id.in_(variant_ids))
    variants_dict = {v.id: v for v in db.exec(variants_stmt).all()}
    
    car_ids = [v.car_id for v in variants_dict.values()]
    cars_stmt = select(Car).where(Car.id.in_(car_ids))
    cars_dict = {c.id: c for c in db.exec(cars_stmt).all()}
    
    result = []
    for item in collection_items:
        variant = variants_dict.get(item.variant_id)
        if not variant:
            continue
        car = cars_dict.get(variant.car_id)
        
        result.append(CollectionItemSchema(
            id=item.id,
            variant_id=item.variant_id,
            added_at=item.added_at,
            variant=VariantSchema.model_validate(variant.model_dump()),
            car=CarSchema.model_validate(car.model_dump()) if car else None
        ))
    
    return result

@app.post("/ocr/gemini", response_model=GeminiOCRResponse)
async def extract_model_code_with_gemini(file: UploadFile = File(...)):
    """
    Extract Hot Wheels toy_number and variant features from image using Gemini API.
    """
    if not gemini_api_key:
        raise HTTPException(
            status_code=500, 
            detail="GEMINI_API_KEY not configured. Please set it in environment variables."
        )
    
    try:
        # Read image file
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes))
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Create prompt for Gemini with explicit JSON format instruction
        prompt = """Analizuj zdjęcie tyłu opakowania Hot Wheels.
Wyodrębnij następujące informacje:

1. TOY_NUMBER (NAJWAŻNIEJSZE!) - kod modelu (np. HYW54, GTK21, N2098)
   Format: 3-10 znaków alfanumerycznych, zwykle 5 znaków
   Szukaj kodu na opakowaniu, często w formacie: "Toy #" lub "No."
   
2. RELEASE_YEAR - rok wydania (np. 2025, 2021, 2008)

3. SERIES_NAME - nazwa serii (np. "Hot Wheels Boulevard", "Wild Widebody", "Mainline")

4. BODY_COLOR - kolor nadwozia (np. "Chrome", "Red", "Blue", "Yellow")

5. SERIES_NUMBER - numer w kolekcji (np. "238/250", "46/250")

WAŻNE: Zwróć WYŁĄCZNIE czysty JSON bez żadnych dodatkowych znaków, markdown, czy komentarzy.
Format odpowiedzi:
{"toy_number": "HYW54", "release_year": 2025, "series_name": "Wild Widebody", "body_color": "Chrome", "series_number": "238/250", "confidence": 0.95}

Jeśli nie możesz znaleźć toy_number, ustaw toy_number na null i confidence na 0.0.
Jeśli jesteś pewien wyniku, ustaw confidence na 0.9-1.0.
Jeśli nie jesteś pewien, ustaw confidence na 0.5-0.8.
Pola release_year, series_name, body_color są opcjonalne - jeśli nie możesz ich znaleźć, ustaw na null."""

        # Generate content with Gemini
        response = model.generate_content([prompt, image])
        
        # Parse response - uproszczone czyszczenie markdownu
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present (uproszczone)
        import re
        response_text = re.sub(r'^```(?:json)?\s*', '', response_text, flags=re.MULTILINE)
        response_text = re.sub(r'\s*```$', '', response_text, flags=re.MULTILINE)
        response_text = response_text.strip()
        
        # Try to parse as JSON
        import json
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract toy_number using regex
            import re
            # Look for toy_number pattern: 3-10 alphanumeric characters
            toy_number_match = re.search(r'\b([A-Z0-9]{3,10})\b', response_text.upper())
            if toy_number_match:
                # Normalize the matched toy_number
                normalized_tn = normalize_toy_number(toy_number_match.group(1))
                return GeminiOCRResponse(
                    toy_number=normalized_tn if normalized_tn else None,
                    confidence=0.7
                )
            else:
                return GeminiOCRResponse(
                    toy_number=None,
                    confidence=0.0
                )
        
        # Extract toy_number (most important field)
        toy_number = data.get("toy_number")
        if toy_number:
            # Normalize using consistent function
            toy_number = normalize_toy_number(str(toy_number))
            # Validate format: 3-10 alphanumeric characters
            import re
            if not re.match(r'^[A-Z0-9]{3,10}$', toy_number):
                toy_number = None
        
        # Extract other fields
        release_year = parse_release_year(data.get("release_year"))
        
        series_name = data.get("series_name")
        if series_name:
            series_name = clean_series_name(str(series_name).strip())
        
        body_color = data.get("body_color")
        if body_color:
            body_color = str(body_color).strip()
        
        return GeminiOCRResponse(
            toy_number=toy_number,
            release_year=release_year,
            series_name=series_name,
            body_color=body_color,
            series_number=data.get("series_number"),
            confidence=data.get("confidence", 0.5)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image with Gemini: {str(e)}")

@app.get("/toy-numbers")
async def get_all_toy_numbers(db: Session = Depends(get_db)):
    """
    Zwraca wszystkie toy_number z bazy danych.
    Używane przez frontend do budowania wzorców regex dla ML Kit OCR.
    ML Kit OCR szuka identyfikatorów modelu na podstawie tego co jest w bazie,
    a nie sztywnego wzorca regex.
    """
    from sqlalchemy import func
    # Pobierz wszystkie unikalne toy_number z bazy
    statement = select(Variant.toy_number).distinct().where(Variant.toy_number.isnot(None))
    results = db.exec(statement).all()
    toy_numbers = [row for row in results if row]
    
    # Filtruj nieprawidłowe wartości
    # UWAGA: W bazie JSON są błędne dane - wartości typu "1/5", "10/10", "028/250" 
    # to są pozycje auta w serii (np. "1/10" = pierwsze auto z serii która ma 10 aut),
    # NIE toy_number (unikalny identyfikator modelu)!
    # Prawdziwe toy_number to formaty typu: "GTK21", "N2098", "93417", "B3568"
    valid_toy_numbers = []
    for tn in toy_numbers:
        if tn and isinstance(tn, str) and len(tn) >= 3 and len(tn) <= 10:
            # Odrzuć formaty ułamkowe (np. "1/5", "10/10", "028/250") - to są pozycje w serii, nie toy_number!
            # Odrzuć też błędne wartości
            if '/' not in tn and tn not in ['//', '', 'null', 'None']:
                # Normalizuj używając spójnej funkcji
                normalized = normalize_toy_number(tn)
                if normalized:
                    valid_toy_numbers.append(normalized)
    
    # Usuń duplikaty i posortuj
    unique_toy_numbers = sorted(set(valid_toy_numbers))
    
    return {
        "toy_numbers": unique_toy_numbers,
        "count": len(unique_toy_numbers)
    }

@app.get("/")
async def root():
    return {"message": "Diecast Collector API"}
