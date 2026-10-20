from fastapi import APIRouter, Depends, HTTPException
from app.models import UserPreferences, UserResponse
from app.models_db import UserDB
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/user", tags=["Preferencias de Usuario"])

@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: UserDB = Depends(get_current_user)):
    """Devuelve los datos del usuario dueño del token."""
    return current_user

@router.post("/preferences")
def save_user_preferences(data: UserPreferences):
    """
    Recibe la intención de alimentación o la lista de compras del usuario
    y simula el almacenamiento para disparar las recetas.
    """
    if not data.intent in ["ahorro", "saludable", "balance"]:
        raise HTTPException(
            status_code=400, 
            detail="Intención inválida. Debe ser 'ahorro', 'saludable' o 'balance'."
        )
    
    # Aquí en el futuro conectarás la lógica para buscar recetas según la intención
    return {
        "status": "success",
        "message": f"Preferencias guardadas correctamente para el usuario {data.user_id}.",
        "data": {
            "intent": data.intent,
            "shopping_list_received": data.shopping_list
        }
    }