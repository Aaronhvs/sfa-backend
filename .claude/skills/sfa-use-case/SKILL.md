---
name: sfa-use-case
description: Guía para crear un use case nuevo en SFA. Cubre el patrón de clase, Protocol, Result, wiring en dependencies.py y tests obligatorios con Fake.
---

# SFA Use Case

## Cuándo usar

Cada nueva operación de negocio (lectura o escritura) que no sea simplemente acceder a un
dato ya existente con un filtro diferente. Si hay lógica, hay use case.

## Patrón completo

### 1. Archivo: `src/sfa/application/use_cases/verb_noun.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from sfa.domain.ports import EntityRepositoryProtocol  # o el port específico


# --- Result DTO ---

@dataclass(frozen=True)
class VerbNounResult:
    field1: str
    field2: int
    # Solo datos que el caller necesita — no exponer internos


# --- Protocol del use case ---

class VerbNounUseCaseProtocol:
    async def execute(self, param1: str, param2: int | None = None) -> VerbNounResult: ...


# --- Implementación ---

class VerbNounUseCase(VerbNounUseCaseProtocol):
    def __init__(self, repo: EntityRepositoryProtocol) -> None:
        self._repo = repo

    async def execute(
        self,
        param1: str,
        param2: int | None = None,
    ) -> VerbNounResult:
        # Toda la lógica de negocio aquí
        # Nunca importar SQLAlchemy, nunca acceder a la DB directamente
        data = await self._repo.get_something(param1)

        if data is None:
            return VerbNounResult(field1="", field2=0)

        return VerbNounResult(
            field1=data.name,
            field2=data.count,
        )
```

### 2. Wiring en `src/sfa/core/dependencies.py`

```python
# Agregar el import del use case
from sfa.application.use_cases.verb_noun import VerbNounUseCase

# Agregar la factory (al final de la sección de Use Cases)
async def get_verb_noun_use_case(
    repo: Annotated[EntityRepository, Depends(get_entity_repository)],
) -> VerbNounUseCase:
    return VerbNounUseCase(repo)
```

---

## Reglas

- El use case depende SOLO de Protocols de `domain/` — nunca de clases concretas de infra
- El `__init__` solo recibe ports (Protocols), nunca `AsyncSession` ni providers directamente
- `execute()` siempre es `async`
- El Result es un `@dataclass(frozen=True)` definido en el mismo archivo
- El Protocol del use case se define en el mismo archivo, antes de la clase
- Nunca llamar a `session.commit()` desde el use case — solo desde tasks o routers
- Errores de dominio: lanzar `ValueError` o excepciones específicas, no atraparlos aquí

---

## Tests obligatorios

Ver skill `/sfa-test` para el patrón completo de Fake + test.

Todo use case nuevo requiere mínimo:
- Happy path con datos válidos
- Edge case de resultado vacío / not found
- Un error esperado si hay validaciones de negocio

---

## Checklist de creación

- [ ] Crear `src/sfa/application/use_cases/verb_noun.py` con Protocol + clase + Result
- [ ] Agregar factory en `core/dependencies.py`
- [ ] Crear `tests/use_cases/test_verb_noun.py` con Fake y tests
- [ ] Si hay router nuevo → usar skill `/sfa-router`
