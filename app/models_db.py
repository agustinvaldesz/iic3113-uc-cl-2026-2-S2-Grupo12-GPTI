from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON
from datetime import datetime
from app.database import Base

class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    # Preferencias del usuario para NutriCart (RF-01)
    dietary_preference = Column(String, default="balance")  # "ahorro", "saludable", "balance"
    budget_limit = Column(Float, nullable=True)             # Presupuesto semanal estimado
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class RecipeDB(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    intent_category = Column(String)  # "ahorro", "saludable", "balance"
    prep_time = Column(String)
    instructions = Column(String)

class ProductCacheDB(Base):
    __tablename__ = "products_cache"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    last_updated = Column(DateTime, default=datetime.utcnow)

class UserDietaryProfileDB(Base):
    __tablename__ = "user_dietary_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    diet_type = Column(String, nullable=False, default="con_carne")  # "con_carne" o "vegetariana"
    allergies = Column(JSON, nullable=False, default=list)           # "mani"
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)