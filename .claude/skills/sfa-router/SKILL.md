---
name: sfa-router
description: Guía para crear un router FastAPI nuevo en SFA con sus Pydantic schemas, inyección de use case vía DI, registro en main.py y archivo .http.
---

# SFA Router

## Cuándo usar

Cada vez que se expone un nuevo endpoint. El router es el Input Adapter — su única
responsabilidad es recibir la request, delegar al use case y serializar la respuesta.

## Patrón completo

### 1. Schema: `src/sfa/api/v1/schemas/noun.py`

```python
from pydantic import BaseModel, ConfigDict


class NounItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    value: float
    optional_field: str | None


class NounResponseSchema(BaseModel):
    total: int
    items: list[NounItemSchema]
    # Para endpoints de detalle, solo el schema del item (sin wrapper)
```

### 2. Router: `src/sfa/api/v1/noun.py`

```python
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from sfa.api.v1.schemas.noun import NounItemSchema, NounResponseSchema
from sfa.application.use_cases.verb_noun import VerbNounUseCase
from sfa.core.dependencies import get_verb_noun_use_case

router = APIRouter()


@router.get("/nouns", response_model=NounResponseSchema)
async def list_nouns(
    use_case: Annotated[VerbNounUseCase, Depends(get_verb_noun_use_case)],
    season: str | None = Query(default=None, description="Temporada, ej: 2024-25"),
    limit: int = Query(default=50, ge=1, le=200),
):
    result = await use_case.execute(season=season, limit=limit)
    return NounResponseSchema(
        total=result.total,
        items=[
            NounItemSchema(
                id=item.id,
                name=item.name,
                value=item.value,
                optional_field=item.optional_field,
            )
            for item in result.items
        ],
    )


@router.get("/nouns/{noun_id}", response_model=NounItemSchema)
async def get_noun(
    noun_id: int,
    use_case: Annotated[VerbNounUseCase, Depends(get_verb_noun_use_case)],
):
    try:
        result = await use_case.execute(noun_id=noun_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return NounItemSchema(...)
```

### 3. Registro en `src/sfa/main.py`

```python
# Agregar import
from sfa.api.v1.noun import router as noun_router

# Agregar en la lista de tags_metadata
{"name": "nouns", "description": "Descripción del recurso"},

# Agregar include_router
app.include_router(noun_router, prefix="/api/v1", tags=["nouns"])
```

### 4. Archivo HTTP: `http/noun.http`

```http
### List nouns
GET http://localhost:8000/api/v1/nouns
Accept: application/json

### List nouns filtered by season
GET http://localhost:8000/api/v1/nouns?season=2024-25&limit=10
Accept: application/json

### Get noun by ID (happy path)
GET http://localhost:8000/api/v1/nouns/1
Accept: application/json

### Get noun by ID (not found)
GET http://localhost:8000/api/v1/nouns/99999
Accept: application/json
```

---

## Reglas

- El router NO contiene lógica de negocio — solo delega al use case
- Solo el router traduce excepciones de dominio a HTTP (`HTTPException`)
- Los schemas Pydantic viven en `api/v1/schemas/` — nunca inline en el router
- El router mapea explícitamente de Result → Schema (no usar `from_orm` mágico)
- Todo endpoint nuevo tiene su archivo `.http` en `http/`

---

## Checklist de creación

- [ ] Crear `src/sfa/api/v1/schemas/noun.py` con schemas de request/response
- [ ] Crear `src/sfa/api/v1/noun.py` con el router
- [ ] Agregar tag en `tags_metadata` en `main.py`
- [ ] Registrar router con `app.include_router` en `main.py`
- [ ] Crear `http/noun.http` con happy path + error cases
