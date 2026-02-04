from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select, desc
from typing import List, Optional, Set
from uuid import UUID
import os
import re
from difflib import SequenceMatcher
from google import genai  # type: ignore[import-not-found]
from google.genai import types  # type: ignore[import-not-found]
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
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

load_dotenv()

# Configure Gemini only when API key is present to keep local dev working.
gemini_api_key = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None

# Ensure schema exists before handling any requests.
create_db_and_tables()

app = FastAPI(title="MyCollection API")

# Allow the Flutter client to call the API from any origin in dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    
    # Fast path for already-normalized values.
    if isinstance(year_value, int):
        return year_value
    
    # Coerce to string to handle ranges and other formats.
    year_str = str(year_value).strip()
    if not year_str:
        return None
    
    # Extract the first year from a range like "2021 - present".
    import re
    if ' - ' in year_str or '–' in year_str or ' to ' in year_str.lower():
        year_match = re.search(r'(\d{4})', year_str)
        if year_match:
            try:
                return int(year_match.group(1))
            except (ValueError, TypeError):
                return None
    
    # Fallback to direct integer parsing.
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
    # Strip trailing series position fragments (e.g. "24/100", "4").
    cleaned = re.sub(r'\d+/\d+$', '', series_name)
    cleaned = re.sub(r'\d+$', '', cleaned)
    cleaned = cleaned.strip()
    
    return cleaned if cleaned else series_name

def normalize_color_tokens(color: str) -> Set[str]:
    """
    Normalize color names to a small base palette for fuzzy matching.
    """
    if not color:
        return set()
    
    text = re.sub(r'[^a-z0-9]+', ' ', color.lower()).strip()
    tokens = text.split()
    tokens = ["gray" if t == "grey" else t for t in tokens]
    
    base_colors = {
        "black", "white", "red", "blue", "green", "yellow", "orange",
        "purple", "pink", "gold", "silver", "gray", "brown", "tan",
        "bronze", "chrome"
    }
    return {t for t in tokens if t in base_colors}

def fuzzy_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()

def normalize_color_string(color: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', color.lower()).strip()

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
        
        # Year match: strict equality yields the best signal.
        if year is not None and variant.release_year is not None:
            if year == variant.release_year:
                score += 0.3
                matches += 1
        
        # Series match: compare cleaned names with substring tolerance.
        if series and variant.series_name:
            series_cleaned = clean_series_name(series)
            variant_series_cleaned = clean_series_name(variant.series_name)
            if series_cleaned and variant_series_cleaned:
                series_lower = series_cleaned.lower().strip()
                variant_series_lower = variant_series_cleaned.lower().strip()
                if series_lower in variant_series_lower or variant_series_lower in series_lower:
                    score += 0.25
                    matches += 1
        
        # Color match: tolerate partial and fuzzy matches for OCR noise.
        if color and variant.body_color:
            color_lower = color.lower().strip()
            variant_color_lower = variant.body_color.lower().strip()
            if color_lower in variant_color_lower or variant_color_lower in color_lower:
                score += 0.2
                matches += 1
            else:
                color_tokens = normalize_color_tokens(color_lower)
                variant_tokens = normalize_color_tokens(variant_color_lower)
                if color_tokens and variant_tokens and color_tokens.intersection(variant_tokens):
                    score += 0.12
                    matches += 1
                else:
                    similarity = fuzzy_ratio(
                        normalize_color_string(color_lower),
                        normalize_color_string(variant_color_lower)
                    )
                    if similarity >= 0.8:
                        score += 0.08
                        matches += 1
        
        # Series position: exact match is a strong discriminator.
        if series_position is not None and series_total is not None:
            if (variant.series_position == series_position and 
                variant.series_total == series_total):
                score += 0.25
                matches += 1
        
        if score > best_score:
            best_score = score
            best_match = {'variant': variant, 'score': score, 'matches': matches}
    
    return best_match


def build_car_response(db: Session, car_id: UUID) -> IdentifyResponse:
    """Build IdentifyResponse with car and all its variants."""
    car_stmt = select(Car).where(Car.id == car_id)
    car = db.exec(car_stmt).first()
    if not car:
        raise HTTPException(status_code=404, detail="Car not found")
    
    car_variants_stmt = select(Variant).where(Variant.car_id == car_id)
    car_variants = db.exec(car_variants_stmt).all()
    
    car_data = car.model_dump()
    car_data['variants'] = [VariantSchema.model_validate(v.model_dump()) for v in car_variants]
    return IdentifyResponse(car=CarSchema.model_validate(car_data))


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
    # Normalize and split codes like "ABC12-1" to match stored toy_number.
    code_normalized = normalize_toy_number(code)
    
    if '-' in code_normalized:
        code_normalized = code_normalized.split('-')[0]
    
    # Load all variants that share the same toy_number.
    statement = select(Variant).where(Variant.toy_number == code_normalized)
    variants = db.exec(statement).all()
    
    if not variants:
        raise HTTPException(status_code=404, detail=f"Car with toy_number '{code_normalized}' not found")
    
    # If there's only one variant, no extra matching is needed.
    if len(variants) == 1:
        return build_car_response(db, variants[0].car_id)
    
    # Use OCR features to disambiguate among multiple variants.
    series_position = None
    series_total = None
    if series_number:
        series_position, series_total = parse_series_number(series_number)
    
    best_match = match_variant_by_features(
        variants, year, series, color, series_position, series_total
    )
    
    # If the best match is confident, return that car directly.
    if best_match and best_match['score'] > 0.8:
        return build_car_response(db, best_match['variant'].car_id)
    
    # Otherwise return a single car record with its variants.
    unique_car_ids = {v.car_id for v in variants}
    
    if len(unique_car_ids) == 1:
        return build_car_response(db, list(unique_car_ids)[0])
    else:
        # Edge case: toy_number points to multiple cars; return the first.
        return build_car_response(db, variants[0].car_id)


@app.get("/identify/by-name", response_model=IdentifyResponse)
async def identify_by_name(
    model_name: str,
    db: Session = Depends(get_db),
    year: Optional[int] = None,
    series: Optional[str] = None,
    color: Optional[str] = None,
    series_number: Optional[str] = None
):
    """
    Identify a car by model_name (text search) with optional variant matching.
    """
    query = model_name.strip()
    if not query:
        raise HTTPException(status_code=400, detail="model_name must not be empty")
    
    # Load candidates by model_name or page_title.
    statement = (
        select(Car)
        .where(
            (Car.model_name.ilike(f"%{query}%")) |
            (Car.page_title.ilike(f"%{query}%"))
        )
        .options(selectinload(Car.variants))
    )
    cars = db.exec(statement).all()
    if not cars:
        raise HTTPException(status_code=404, detail="No cars match model_name")
    
    series_position = None
    series_total = None
    if series_number:
        series_position, series_total = parse_series_number(series_number)
    
    best_car_id = None
    best_score = -1.0
    
    for car in cars:
        if not car.variants:
            continue
        variant_match = match_variant_by_features(
            car.variants, year, series, color, series_position, series_total
        )
        name_score = fuzzy_ratio(query.lower(), (car.model_name or "").lower())
        score = name_score
        if variant_match:
            score += variant_match['score']
        if score > best_score:
            best_score = score
            best_car_id = car.id
    
    if not best_car_id:
        best_car_id = cars[0].id
    
    return build_car_response(db, best_car_id)

@app.get("/cars/search", response_model=List[CarSchema])
async def search_cars(
    model_name: str,
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0
):
    """
    Search cars by model_name (case-insensitive).
    """
    query = model_name.strip()
    if not query:
        raise HTTPException(status_code=400, detail="model_name must not be empty")
    
    statement = (
        select(Car)
        .where(Car.model_name.ilike(f"%{query}%"))
        .order_by(Car.model_name)
        .offset(offset)
        .limit(limit)
        .options(selectinload(Car.variants))
    )
    cars = db.exec(statement).all()
    
    result = []
    for car in cars:
        car_data = car.model_dump()
        car_data['variants'] = [VariantSchema.model_validate(v.model_dump()) for v in car.variants]
        result.append(CarSchema.model_validate(car_data))
    
    return result

@app.post("/collection", response_model=CollectionItemSchema)
async def add_to_collection(
    request: AddToCollectionRequest,
    db: Session = Depends(get_db)
):
    """
    Add a variant to the user's collection.
    Sprawdza czy użytkownik już ma ten wariant (zapobiega duplikatom).
    """
    # Validate the variant before adding it to the collection.
    statement = select(Variant).where(Variant.id == request.variant_id)
    variant = db.exec(statement).first()
    
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    
    # Prevent duplicates by returning the existing collection item.
    existing_collection = select(UserCollection).where(
        UserCollection.variant_id == request.variant_id
    ).options(
        selectinload(UserCollection.variant).selectinload(Variant.car)
    )
    existing_item = db.exec(existing_collection).first()
    
    if existing_item:
        return CollectionItemSchema(
            id=existing_item.id,
            variant_id=existing_item.variant_id,
            added_at=existing_item.added_at,
            variant=VariantSchema.model_validate(existing_item.variant.model_dump()),
            car=CarSchema.model_validate(existing_item.variant.car.model_dump())
        )
    
    # Create a new collection entry when no duplicate is found.
    collection_item = UserCollection(variant_id=request.variant_id)
    db.add(collection_item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Another request inserted the same variant concurrently.
        existing_item = db.exec(existing_collection).first()
        if existing_item:
            return CollectionItemSchema(
                id=existing_item.id,
                variant_id=existing_item.variant_id,
                added_at=existing_item.added_at,
                variant=VariantSchema.model_validate(existing_item.variant.model_dump()),
                car=CarSchema.model_validate(existing_item.variant.car.model_dump())
            )
        raise HTTPException(status_code=500, detail="Could not save collection item")
    
    # Load relationships for response payload in one query.
    created_item = db.exec(
        select(UserCollection).where(UserCollection.id == collection_item.id).options(
            selectinload(UserCollection.variant).selectinload(Variant.car)
        )
    ).first()
    if not created_item or not created_item.variant:
        raise HTTPException(status_code=500, detail="Could not load collection item")
    
    # Return the new collection entry with variant/car data.
    result = CollectionItemSchema(
        id=created_item.id,
        variant_id=created_item.variant_id,
        added_at=created_item.added_at,
        variant=VariantSchema.model_validate(created_item.variant.model_dump()),
        car=CarSchema.model_validate(created_item.variant.car.model_dump())
    )
    
    return result

@app.get("/collection", response_model=List[CollectionItemSchema])
async def get_collection(
    db: Session = Depends(get_db),
    limit: int = 200,
    offset: int = 0
):
    """
    Get all items in the user's collection.
    """
    statement = (
        select(UserCollection)
        .order_by(desc(UserCollection.added_at))
        .offset(offset)
        .limit(limit)
        .options(selectinload(UserCollection.variant).selectinload(Variant.car))
    )
    collection_items = db.exec(statement).all()
    
    result = []
    for item in collection_items:
        variant = item.variant
        if not variant:
            continue
        car = variant.car
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
    if not gemini_client:
        raise HTTPException(
            status_code=500, 
            detail="GEMINI_API_KEY not configured. Please set it in environment variables."
        )
    
    try:
        # Read the uploaded image for Gemini.
        image_bytes = await file.read()
        # Reset cursor for future reads (e.g., validation or other handlers).
        await file.seek(0)
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=file.content_type or "image/jpeg"
        )
        
        # Use the lightweight model to keep latency low.
        model_name = "gemini-2.0-flash-lite"
        
        # Use structured outputs to enforce JSON schema.
        prompt = """Analizuj zdjęcie tyłu opakowania Hot Wheels.
Wyodrębnij następujące informacje:

1. TOY_NUMBER (NAJWAŻNIEJSZE!) - kod modelu (np. HYW54, GTK21, N2098)
   Format: 3-10 znaków alfanumerycznych, zwykle 5 znaków
   Szukaj kodu na opakowaniu, często w formacie: "Toy #" lub "No."
   
2. MODEL_NAME - nazwa modelu/castingu (np. "Dodge A100", "Volkswagen ID R")
   Jeśli nie jesteś pewien, ustaw na null.
   
3. RELEASE_YEAR - rok wydania (np. 2025, 2021, 2008)

4. SERIES_NAME - nazwa serii (np. "Hot Wheels Boulevard", "Wild Widebody", "Mainline")

5. BODY_COLOR - kolor nadwozia (np. "Chrome", "Red", "Blue", "Yellow")

6. SERIES_NUMBER - numer w kolekcji (np. "238/250", "46/250")

WAŻNE: Zwróć WYŁĄCZNIE czysty JSON bez żadnych dodatkowych znaków, markdown, czy komentarzy.
Format odpowiedzi:
{"toy_number": "HYW54", "model_name": "Dodge A100", "release_year": 2025, "series_name": "Wild Widebody", "body_color": "Chrome", "series_number": "238/250", "confidence": 0.95}

Jeśli nie możesz znaleźć toy_number, ustaw toy_number na null i confidence na 0.0.
Jeśli jesteś pewien wyniku, ustaw confidence na 0.9-1.0.
Jeśli nie jesteś pewien, ustaw confidence na 0.5-0.8.
Pola model_name, release_year, series_name, body_color są opcjonalne - jeśli nie możesz ich znaleźć, ustaw na null."""

        response = gemini_client.models.generate_content(
            model=model_name,
            contents=[prompt, image_part],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiOCRResponse
            )
        )
        
        data = response.parsed
        if data is None:
            raise HTTPException(status_code=500, detail="Gemini returned an empty response")
        
        if isinstance(data, GeminiOCRResponse):
            data_dict = data.model_dump()
        elif isinstance(data, dict):
            data_dict = data
        else:
            data_dict = GeminiOCRResponse.model_validate(data).model_dump()
        
        # Extract and validate the core identifier.
        toy_number = data_dict.get("toy_number")
        if toy_number:
            toy_number = normalize_toy_number(str(toy_number))
            import re
            if not re.match(r'^[A-Z0-9]{3,10}$', toy_number):
                toy_number = None
        
        # Parse remaining fields with gentle normalization.
        model_name = data_dict.get("model_name")
        if model_name:
            model_name = str(model_name).strip()
        release_year = parse_release_year(data_dict.get("release_year"))
        
        series_name = data_dict.get("series_name")
        if series_name:
            series_name = clean_series_name(str(series_name).strip())
        
        body_color = data_dict.get("body_color")
        if body_color:
            body_color = str(body_color).strip()
        
        return GeminiOCRResponse(
            toy_number=toy_number,
            model_name=model_name,
            release_year=release_year,
            series_name=series_name,
            body_color=body_color,
            series_number=data_dict.get("series_number"),
            confidence=data_dict.get("confidence", 0.5)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image with Gemini: {str(e)}")

@app.get("/toy-numbers")
async def get_all_toy_numbers(
    db: Session = Depends(get_db),
    limit: int = 200,
    offset: int = 0
):
    """
    Zwraca wszystkie toy_number z bazy danych.
    Używane przez frontend do budowania wzorców regex dla ML Kit OCR.
    ML Kit OCR szuka identyfikatorów modelu na podstawie tego co jest w bazie,
    a nie sztywnego wzorca regex.
    """
    from sqlalchemy import func
    # Fetch all distinct toy_number values for OCR hinting.
    statement = select(Variant.toy_number).distinct().where(
        Variant.toy_number.isnot(None)
    ).offset(offset).limit(limit)
    results = db.exec(statement).all()
    toy_numbers = [row for row in results if row]
    
    # Filter out series-position formats and invalid placeholders.
    valid_toy_numbers = []
    for tn in toy_numbers:
        if tn and isinstance(tn, str) and len(tn) >= 3 and len(tn) <= 10:
            if '/' not in tn and tn not in ['//', '', 'null', 'None']:
                normalized = normalize_toy_number(tn)
                if normalized:
                    valid_toy_numbers.append(normalized)
    
    # Deduplicate and return a stable list.
    unique_toy_numbers = sorted(set(valid_toy_numbers))
    
    return {
        "toy_numbers": unique_toy_numbers,
        "count": len(unique_toy_numbers)
    }

@app.get("/")
async def root():
    return {"message": "Diecast Collector API"}
