from fastapi import APIRouter, HTTPException
from app.models import UserPreferences

router = APIRouter(prefix="/api/user", tags=["Preferencias de Usuario"])

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