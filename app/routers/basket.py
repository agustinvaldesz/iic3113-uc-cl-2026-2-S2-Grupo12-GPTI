from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.basket import QuoteRequest, QuoteResponse
from app.services.catalog_service import quote_items
from app.services.llm_service import load_recipes

router = APIRouter(prefix="/api/basket", tags=["Cotización y Canasta"])


@router.post("/quote", response_model=QuoteResponse)
def quote_basket(data: QuoteRequest, db: Session = Depends(get_db)):
    """
    Cotiza ingredientes contra el catálogo de Lider.
    Por cada ingrediente devuelve el producto elegido, todas las opciones y, si existe,
    una alternativa más barata (SC-2). Para reemplazar un producto, el front vuelve a
    llamar a este endpoint con selections = {ingrediente: sku}; el total y el ahorro se recalculan.
    """
    items = [i.model_dump() for i in data.items]

    if data.recipe_ids:
        recipes = {r["id"]: r for r in load_recipes()}
        missing = [rid for rid in data.recipe_ids if rid not in recipes]
        if missing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Recetas no encontradas: {missing}")
        for rid in data.recipe_ids:
            items.extend({"original_name": ing} for ing in recipes[rid]["ingredients"])

    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes enviar al menos un ingrediente o una receta para cotizar.",
        )

    return quote_items(db, items, pantry=data.pantry, selections=data.selections)
