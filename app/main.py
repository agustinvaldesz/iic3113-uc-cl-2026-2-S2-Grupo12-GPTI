import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, SessionLocal
from app.models_db import Base
from app.routers import preferences, auth, recommendations, basket, menu, admin_recipes
from app.services.catalog_service import seed_catalog_if_empty
from app.services.recipe_repository import seed_recipes_if_empty

# Crea las tablas en la base de datos si no existen
Base.metadata.create_all(bind=engine)

# Carga el catálogo semilla de Lider si la tabla de productos está vacía
with SessionLocal() as _db:
    seed_catalog_if_empty(_db)
    seed_recipes_if_empty(_db)  # Recetas base aprobadas si la tabla está vacía

app = FastAPI(
    title="NutriCart Backend",
    description="API oficial para recomendación de recetas y cotización en Lider",
    version="1.0.0"
)

# Orígenes permitidos para CORS (lista separada por comas)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(preferences.router)
app.include_router(recommendations.router)
app.include_router(basket.router)
app.include_router(menu.router)
app.include_router(admin_recipes.router)

@app.get("/")
def read_root():
    return {"message": "Bienvenido al backend de NutriCart - Base de datos operativa"}
