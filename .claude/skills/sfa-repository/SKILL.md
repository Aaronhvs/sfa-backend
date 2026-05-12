---
name: sfa-repository
description: Guía para crear un repository nuevo en SFA. Cubre implementación del Protocol, queries SQLAlchemy 2.0 async, retorno de DTOs de dominio y registro en el módulo.
---

# SFA Repository

## Cuándo usar

Cada vez que se necesita un nuevo adaptador de base de datos. El repository implementa
un Protocol de `domain/` y retorna siempre DTOs de dominio (frozen dataclasses).

## Patrón completo

### 1. Definir el Protocol en `domain/`

Si el Protocol aún no existe, agregarlo al archivo correspondiente en `domain/`:

```python
# En domain/ports.py (read-side) o domain/ingestion_ports.py / enrichment_ports.py

@dataclass(frozen=True)
class EntityDTO:
    id: int
    name: str
    value: float


@runtime_checkable
class EntityRepositoryProtocol(Protocol):
    async def get_by_id(self, entity_id: int) -> EntityDTO | None: ...
    async def get_all(self, season: str | None = None) -> list[EntityDTO]: ...
    async def upsert(self, name: str, value: float) -> int: ...
```

### 2. Implementación: `src/sfa/infrastructure/repositories/entity_repository.py`

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfa.domain.ports import EntityDTO, EntityRepositoryProtocol
from sfa.infrastructure.models.entity.models import EntityModel
from sfa.infrastructure.models.other.models import OtherModel  # si hay joins


class EntityRepository(EntityRepositoryProtocol):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entity_id: int) -> EntityDTO | None:
        stmt = (
            select(EntityModel)
            .where(EntityModel.id == entity_id)
        )
        row = (await self._session.execute(stmt)).scalars().first()
        if row is None:
            return None
        return EntityDTO(id=row.id, name=row.name, value=float(row.value))

    async def get_all(self, season: str | None = None) -> list[EntityDTO]:
        stmt = select(EntityModel).order_by(EntityModel.name)
        if season is not None:
            stmt = stmt.where(EntityModel.season == season)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [EntityDTO(id=r.id, name=r.name, value=float(r.value)) for r in rows]

    async def upsert(self, name: str, value: float) -> int:
        # Usar INSERT ... ON CONFLICT para idempotencia
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = (
            pg_insert(EntityModel)
            .values(name=name, value=value)
            .on_conflict_do_update(
                index_elements=["name"],
                set_={"value": value},
            )
            .returning(EntityModel.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
```

### 3. Registrar en `src/sfa/infrastructure/repositories/__init__.py`

```python
from .entity_repository import EntityRepository

__all__ = [
    ...,
    "EntityRepository",
]
```

### 4. Agregar factory en `src/sfa/core/dependencies.py`

```python
from sfa.infrastructure.repositories import EntityRepository

async def get_entity_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EntityRepository:
    return EntityRepository(db)
```

---

## Queries SQLAlchemy 2.0 — patrones comunes

```python
# Select simple con filtro
stmt = select(Model).where(Model.field == value)
rows = (await self._session.execute(stmt)).scalars().all()

# Select con join y mappings (para proyecciones multi-tabla)
stmt = (
    select(
        Model.id,
        OtherModel.name.label("other_name"),
    )
    .join(OtherModel, Model.other_id == OtherModel.id)
    .where(Model.season == season)
)
rows = (await self._session.execute(stmt)).mappings().all()

# Count
from sqlalchemy import func
stmt = select(func.count()).select_from(Model).where(Model.active == True)
total = (await self._session.execute(stmt)).scalar_one()

# Insert idempotente (upsert)
from sqlalchemy.dialects.postgresql import insert as pg_insert
stmt = (
    pg_insert(Model)
    .values(...)
    .on_conflict_do_update(index_elements=["unique_field"], set_={...})
    .returning(Model.id)
)
result = await self._session.execute(stmt)
entity_id = result.scalar_one()
```

---

## Reglas

- El repository NUNCA importa otros repositories — solo modelos SQLAlchemy y DTOs de dominio
- Siempre retorna DTOs de dominio (frozen dataclasses), nunca instancias de ORM models
- Los upserts deben ser idempotentes (ON CONFLICT DO UPDATE)
- `session.commit()` se llama desde la capa superior (task o router), no desde el repository
- Los Numerics de PostgreSQL se castean explícitamente: `float(row.numeric_field)`
- Usar `.mappings()` para proyecciones multi-tabla, `.scalars()` para queries de un modelo

---

## Checklist de creación

- [ ] Definir Protocol y DTOs en `domain/` si no existen
- [ ] Crear `src/sfa/infrastructure/repositories/entity_repository.py`
- [ ] Registrar en `repositories/__init__.py` con `__all__`
- [ ] Agregar factory `get_entity_repository` en `core/dependencies.py`
