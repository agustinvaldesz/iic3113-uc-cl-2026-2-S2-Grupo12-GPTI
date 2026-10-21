from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import UserPreferences, UserResponse, DietaryProfileUpdate, DietaryProfileResponse, DIET_LABELS, ALLERGY_LABELS
from app.models_db import UserDB, UserDietaryProfileDB
from app.dependencies import get_current_user
from app.database import get_db

router = APIRouter(prefix="/api/user", tags=["Preferencias de Usuario"])

@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: UserDB = Depends(get_current_user)):
    """Devuelve los datos del usuario dueño del token."""
    return current_user

@router.post("/preferences")
def save_user_preferences(
    data: UserPreferences,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),):
    """
    Guarda la intención de alimentación y el presupuesto del usuario autenticado.
    La lista de compras se recibe, pero aún no se almacena.
    """
    current_user.dietary_preference = data.intent
    if data.budget_limit is not None:
        current_user.budget_limit = data.budget_limit

    db.commit()
    db.refresh(current_user)
    
    # Aquí en el futuro conectarás la lógica para buscar recetas según la intención
    return {
        "status": "success",
        "message": f"Preferencias guardadas correctamente para {current_user.full_name}.",
        "data": {
            "intent": current_user.dietary_preference,
            "budget_limit": current_user.budget_limit,
            "shopping_list_received": data.shopping_list,
        }
    }

def _get_profile(db: Session, user_id: int):
    return db.query(UserDietaryProfileDB).filter(UserDietaryProfileDB.user_id == user_id).first()

@router.get("/dietary-profile", response_model=DietaryProfileResponse)
def read_dietary_profile(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve el tipo de dieta y las alergias del usuario (valores por defecto si no tiene perfil)."""
    profile = _get_profile(db, current_user.id)
    if profile is None:
        return DietaryProfileResponse(diet_type="con_carne", allergies=[])
    return DietaryProfileResponse(
        diet_type=profile.diet_type, allergies=profile.allergies, updated_at=profile.updated_at
    )

@router.get("/dietary-options")
def read_dietary_options():
    """Opciones disponibles para construir los botones de dieta y alergias en el frontend."""
    return {
        "diet_types": [{"value": k, "label": v} for k, v in DIET_LABELS.items()],
        "allergies": [{"value": k, "label": v} for k, v in ALLERGY_LABELS.items()],
    }

@router.put("/dietary-profile", response_model=DietaryProfileResponse)
def update_dietary_profile(
    data: DietaryProfileUpdate,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crea o reemplaza el perfil alimentario completo del usuario."""
    profile = _get_profile(db, current_user.id)
    if profile is None:
        profile = UserDietaryProfileDB(user_id=current_user.id)
        db.add(profile)

    profile.diet_type = data.diet_type
    profile.allergies = list(dict.fromkeys(data.allergies))  # Elimina alergias repetidas
    profile.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(profile)
    return DietaryProfileResponse(
        diet_type=profile.diet_type, allergies=profile.allergies, updated_at=profile.updated_at
    )

@router.delete("/dietary-profile", status_code=204)
def delete_dietary_profile(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Elimina el perfil alimentario del usuario (dieta y alergias)."""
    profile = _get_profile(db, current_user.id)
    if profile is not None:
        db.delete(profile)
        db.commit()

