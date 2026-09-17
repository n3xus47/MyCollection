from sqlmodel import SQLModel, Field, Relationship, create_engine, Session
from sqlalchemy import inspect, text
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/diecast_db")

engine = create_engine(DATABASE_URL)

def get_db():
    """Dependency do uzyskania sesji bazy danych."""
    with Session(engine) as session:
        yield session


# Base classes - wspólne pola dla modeli i schematów
class CarBase(SQLModel):
    """Bazowa klasa dla Car - wspólne pola dla modelu i schematu."""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    model_name: str = Field(index=True)
    page_title: Optional[str] = None

class Car(CarBase, table=True):
    """Model samochodu (casting) - grupuje warianty po model_name/page_title."""
    __tablename__ = "cars"
    
    variants: List["Variant"] = Relationship(back_populates="car", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class Variant(SQLModel, table=True):
    """Model wariantu samochodu (konkretny model z opakowania)."""
    __tablename__ = "variants"
    
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    car_id: UUID = Field(foreign_key="cars.id")
    toy_number: str = Field(index=True)
    desc: str
    is_chase: bool = Field(default=False)
    
    # Statusy kolekcjonerskie
    treasure_hunt: bool = Field(default=False)
    super_treasure_hunt: bool = Field(default=False)
    
    # Cechy wariantu do dopasowania
    release_year: Optional[int] = None
    series_name: Optional[str] = None
    series_position: Optional[int] = None
    series_total: Optional[int] = None
    body_color: Optional[str] = None
    tampo: Optional[str] = None
    wheel_type: Optional[str] = None
    base_color: Optional[str] = None
    window_color: Optional[str] = None
    interior_color: Optional[str] = None
    
    car: Optional[Car] = Relationship(back_populates="variants")
    user_collections: List["UserCollection"] = Relationship(back_populates="variant")


class UserCollection(SQLModel, table=True):
    """Model kolekcji użytkownika - zapisane samochody."""
    __tablename__ = "user_collection"
    
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    variant_id: UUID = Field(foreign_key="variants.id")
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    variant: Optional[Variant] = Relationship(back_populates="user_collections")


# Schematy API - używają dziedziczenia zamiast duplikacji
class VariantBase(SQLModel):
    """Bazowa klasa dla Variant - wspólne pola."""
    id: UUID
    car_id: UUID
    toy_number: str
    desc: str
    is_chase: bool
    treasure_hunt: bool
    super_treasure_hunt: bool
    release_year: Optional[int] = None
    series_name: Optional[str] = None
    series_position: Optional[int] = None
    series_total: Optional[int] = None
    body_color: Optional[str] = None
    tampo: Optional[str] = None
    wheel_type: Optional[str] = None


class VariantSchema(VariantBase):
    """Schema dla wariantu w API."""
    pass


class CarSchema(CarBase):
    """Schema dla samochodu w API."""
    id: UUID  # Override Optional z base
    variants: List[VariantSchema] = []


class IdentifyResponse(SQLModel):
    """Response dla endpointu identify."""
    # CarSchema już zawiera variants, więc nie ma potrzeby duplikować
    car: CarSchema


class AddToCollectionRequest(SQLModel):
    """Request do dodania do kolekcji."""
    variant_id: UUID


class CollectionItemSchema(SQLModel):
    """Schema dla elementu kolekcji."""
    id: UUID
    variant_id: UUID
    added_at: datetime
    variant: VariantSchema
    car: Optional[CarSchema] = None


class GeminiOCRResponse(SQLModel):
    """Response z OCR Gemini."""
    toy_number: Optional[str] = None
    model_name: Optional[str] = None
    release_year: Optional[int] = None
    series_name: Optional[str] = None
    body_color: Optional[str] = None
    series_number: Optional[str] = None
    confidence: float


def _ensure_user_collection_added_at():
    """Ensure legacy databases have the added_at column and backfill nulls."""
    inspector = inspect(engine)
    if "user_collection" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("user_collection")}
    if "added_at" not in columns:
        dialect = engine.dialect.name
        if dialect == "postgresql":
            ddl = (
                "ALTER TABLE user_collection "
                "ADD COLUMN added_at TIMESTAMP WITH TIME ZONE "
                "DEFAULT (CURRENT_TIMESTAMP)"
            )
        elif dialect == "sqlite":
            ddl = (
                "ALTER TABLE user_collection "
                "ADD COLUMN added_at DATETIME "
                "DEFAULT (CURRENT_TIMESTAMP)"
            )
        else:
            ddl = (
                "ALTER TABLE user_collection "
                "ADD COLUMN added_at TIMESTAMP "
                "DEFAULT (CURRENT_TIMESTAMP)"
            )
        with engine.begin() as conn:
            conn.execute(text(ddl))
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE user_collection "
                "SET added_at = CURRENT_TIMESTAMP "
                "WHERE added_at IS NULL"
            )
        )


def _ensure_variants_columns():
    """Ensure legacy databases have all required columns on variants."""
    inspector = inspect(engine)
    if "variants" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("variants")}
    dialect = engine.dialect.name

    if dialect == "postgresql":
        type_map = {
            "toy_number": "VARCHAR",
            "desc": "TEXT",
            "is_chase": "BOOLEAN",
            "treasure_hunt": "BOOLEAN",
            "super_treasure_hunt": "BOOLEAN",
            "release_year": "INTEGER",
            "series_name": "VARCHAR",
            "series_position": "INTEGER",
            "series_total": "INTEGER",
            "body_color": "VARCHAR",
            "tampo": "VARCHAR",
            "wheel_type": "VARCHAR",
            "base_color": "VARCHAR",
            "window_color": "VARCHAR",
            "interior_color": "VARCHAR",
        }
        default_map = {
            "is_chase": "DEFAULT FALSE",
            "treasure_hunt": "DEFAULT FALSE",
            "super_treasure_hunt": "DEFAULT FALSE",
        }
    else:
        # SQLite and other dialects fall back to generic types.
        type_map = {
            "toy_number": "TEXT",
            "desc": "TEXT",
            "is_chase": "BOOLEAN",
            "treasure_hunt": "BOOLEAN",
            "super_treasure_hunt": "BOOLEAN",
            "release_year": "INTEGER",
            "series_name": "TEXT",
            "series_position": "INTEGER",
            "series_total": "INTEGER",
            "body_color": "TEXT",
            "tampo": "TEXT",
            "wheel_type": "TEXT",
            "base_color": "TEXT",
            "window_color": "TEXT",
            "interior_color": "TEXT",
        }
        default_map = {}

    missing = [name for name in type_map.keys() if name not in columns]
    if not missing:
        return

    with engine.begin() as conn:
        for name in missing:
            default_sql = f" {default_map[name]}" if name in default_map else ""
            ddl = f"ALTER TABLE variants ADD COLUMN {name} {type_map[name]}{default_sql}"
            conn.execute(text(ddl))


def _ensure_cars_columns():
    """Ensure legacy databases have required columns on cars."""
    inspector = inspect(engine)
    if "cars" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("cars")}
    dialect = engine.dialect.name

    if dialect == "postgresql":
        type_map = {
            "model_name": "VARCHAR",
            "page_title": "VARCHAR",
        }
    else:
        type_map = {
            "model_name": "TEXT",
            "page_title": "TEXT",
        }

    missing = [name for name in type_map.keys() if name not in columns]
    if not missing:
        return

    with engine.begin() as conn:
        for name in missing:
            ddl = f"ALTER TABLE cars ADD COLUMN {name} {type_map[name]}"
            conn.execute(text(ddl))


def create_db_and_tables():
    """Utwórz tabele w bazie danych."""
    SQLModel.metadata.create_all(engine)
    _ensure_user_collection_added_at()
    _ensure_variants_columns()
    _ensure_cars_columns()