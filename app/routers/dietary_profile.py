from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Header
from typing import Optional

from app.schemas.dietary_profile import (
    DietaryProfileUpdateRequest,
    DietaryProfileResponse
)
from app.services.supabase_service import supabase

router = APIRouter(
    prefix="/api/user",
    tags=["Perfil Dietario"]
)

# Helper para identificar al usuario actual (desde header, token JWT o fallback)
def get_current_user_id(x_user_id: Optional[str] = Header(None, alias="X-User-Id")) -> str:
    # Si ya tienes autenticación por Bearer Token o dependencias de auth.py, úsala aquí.
    if x_user_id:
        return x_user_id
    return "1"  # ID por defecto para pruebas si no viene header


@router.put("/dietary-profile", response_model=DietaryProfileResponse, status_code=status.HTTP_200_OK)
def update_dietary_profile(
    body: DietaryProfileUpdateRequest,
    user_id: str = Header("1", alias="X-User-Id")
):
    """
    Guarda o actualiza el perfil dietario del usuario.
    Si consent no es true, Pydantic rechaza automáticamente con 422.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    payload = {
        "user_id": user_id,
        "diet_type": body.diet_type,
        "allergies": body.allergies,
        "consent": True,
        "consent_at": now,
        "updated_at": now
    }

    try:
        # Upsert: crea o actualiza según user_id
        res = supabase.table("user_dietary_profiles").upsert(payload).execute()
        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo guardar el perfil dietario."
            )
        data = res.data[0]
        return DietaryProfileResponse(
            diet_type=data["diet_type"],
            allergies=data["allergies"],
            consent_at=data["consent_at"],
            updated_at=data["updated_at"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al interactuar con la base de datos: {str(e)}"
        )


@router.get("/dietary-profile", response_model=DietaryProfileResponse)
def get_dietary_profile(user_id: str = Header("1", alias="X-User-Id")):
    """
    Retorna el perfil dietario del usuario con sus marcas de tiempo.
    """
    try:
        res = supabase.table("user_dietary_profiles")\
            .select("diet_type, allergies, consent_at, updated_at")\
            .eq("user_id", user_id)\
            .execute()

        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Perfil dietario no encontrado para este usuario."
            )

        row = res.data[0]
        return DietaryProfileResponse(
            diet_type=row["diet_type"],
            allergies=row["allergies"],
            consent_at=row["consent_at"],
            updated_at=row["updated_at"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar el perfil: {str(e)}"
        )


@router.delete("/dietary-profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_dietary_profile(user_id: str = Header("1", alias="X-User-Id")):
    """
    Elimina por completo el perfil dietario y el consentimiento del usuario (204 No Content).
    """
    try:
        supabase.table("user_dietary_profiles").delete().eq("user_id", user_id).execute()
        return None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar el perfil: {str(e)}"
        )