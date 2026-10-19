from fastapi import FastAPI
from app.database import engine
from app.models_db import Base
from app.routers import preferences, auth

# Crea las tablas en la base de datos si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="NutriCart Backend",
    description="API oficial para recomendación de recetas y cotización en Lider",
    version="1.0.0"
)

app.include_router(auth.router)
app.include_router(preferences.router)

@app.get("/")
def read_root():
    return {"message": "Bienvenido al backend de NutriCart - Base de datos operativa"}