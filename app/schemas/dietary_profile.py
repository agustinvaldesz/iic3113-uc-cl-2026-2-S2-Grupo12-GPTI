from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional
from datetime import datetime

# Valores estrictos definidos por el front
DietType = Literal["con_carne", "vegetariana", "vegana"]
AllowedAllergies = Literal["gluten", "lactosa", "frutos_secos", "mariscos"]

class DietaryProfileUpdateRequest(BaseModel):
    diet_type: DietType
    allergies: List[AllowedAllergies] = Field(default=[])
    consent: bool

    @field_validator("consent")
    @classmethod
    def validate_consent_must_be_true(cls, value: bool) -> bool:
        if value is not True:
            # Lanza ValueError, lo cual Pydantic convierte automáticamente en 422 Unprocessable Entity
            raise ValueError("El consentimiento (consent) debe ser true para registrar el perfil.")
        return value

class DietaryProfileResponse(BaseModel):
    diet_type: DietType
    allergies: List[str]
    consent_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None