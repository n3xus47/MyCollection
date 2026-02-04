from sqlmodel import SQLModel, Field, Relationship, create_engine, Session
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


def create_db_and_tables():
    """Utwórz tabele w bazie danych."""
    SQLModel.metadata.create_all(engine)
