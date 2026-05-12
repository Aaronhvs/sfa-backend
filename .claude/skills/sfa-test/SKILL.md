---
name: sfa-test
description: Guía de testing para SFA. Cubre el patrón Fake para Protocols, estructura de tests de use cases con pytest-anyio, y reglas innegociables.
---

# SFA Test

## Reglas innegociables

1. **Antes de escribir tests nuevos:** correr `pytest tests/` y documentar qué tests ya
   fallaban. Los tests nuevos no deben enmascarar fallos previos.
2. **Tests obligatorios:** todo use case nuevo requiere tests. No se hace merge sin coverage
   de la funcionalidad nueva.
3. **Fakes, no Mocks:** usar clases Fake que implementen el Protocol completo.
   Nunca `MagicMock`, nunca `patch`.
4. **Marker async:** `@pytest.mark.anyio` en todos los tests async.
5. **No DB real en unit tests:** los tests de use cases usan solo Fakes, nunca AsyncSession.

---

## Patrón completo

### Archivo: `tests/use_cases/test_verb_noun.py`

```python
import pytest

from sfa.application.use_cases.verb_noun import VerbNounResult, VerbNounUseCase
from sfa.domain.ports import EntityDTO, EntityRepositoryProtocol


# --- Fake del Protocol ---

class FakeEntityRepository(EntityRepositoryProtocol):
    """
    Implementa TODOS los métodos del Protocol.
    El estado interno simula la BD — sin SQLAlchemy, sin async I/O real.
    """

    def __init__(
        self,
        entities: list[EntityDTO] | None = None,
        season: str | None = "2024-25",
    ):
        self._entities = entities or []
        self._season = season

    async def get_by_id(self, entity_id: int) -> EntityDTO | None:
        return next((e for e in self._entities if e.id == entity_id), None)

    async def get_all(self, season: str | None = None) -> list[EntityDTO]:
        if season is not None:
            return [e for e in self._entities if e.season == season]
        return self._entities

    # Implementar TODOS los métodos del Protocol, aunque no se usen en este test
    async def upsert(self, name: str, value: float) -> int:
        return 1


# --- Helper builders ---

def _make_entity(entity_id: int = 1, name: str = "Entity A") -> EntityDTO:
    return EntityDTO(id=entity_id, name=name, value=100.0)


# --- Tests ---

class TestVerbNounUseCase:

    @pytest.mark.anyio
    async def test_returns_result_with_valid_input(self):
        entities = [_make_entity(1), _make_entity(2, "Entity B")]
        repo = FakeEntityRepository(entities=entities, season="2024-25")
        uc = VerbNounUseCase(repo)

        result = await uc.execute(season="2024-25")

        assert isinstance(result, VerbNounResult)
        assert result.total == 2

    @pytest.mark.anyio
    async def test_returns_empty_when_no_data(self):
        repo = FakeEntityRepository(entities=[])
        uc = VerbNounUseCase(repo)

        result = await uc.execute(season="2024-25")

        assert result.total == 0
        assert result.items == []

    @pytest.mark.anyio
    async def test_resolves_latest_season_when_none_provided(self):
        repo = FakeEntityRepository(entities=[_make_entity()], season="2023-24")
        uc = VerbNounUseCase(repo)

        result = await uc.execute(season=None)

        assert result.season == "2023-24"

    @pytest.mark.anyio
    async def test_raises_value_error_for_invalid_input(self):
        repo = FakeEntityRepository()
        uc = VerbNounUseCase(repo)

        with pytest.raises(ValueError, match="invalid"):
            await uc.execute(season="bad-format")
```

---

## Cómo implementar el Fake correctamente

El Fake debe implementar **todos** los métodos del Protocol, no solo los que usa el use case
bajo test. Esto garantiza que el Fake sigue siendo válido cuando el Protocol evoluciona.

```python
# Si el Protocol tiene 5 métodos, el Fake implementa los 5
# Los métodos no usados pueden retornar valores vacíos/neutros
async def unused_method(self, param: int) -> list[SomeDTO]:
    return []
```

Verificar que el Fake satisface el Protocol:

```python
assert isinstance(FakeEntityRepository(), EntityRepositoryProtocol)
# Funciona porque el Protocol tiene @runtime_checkable
```

---

## Mínimo de tests por use case

| Escenario | Test obligatorio |
|---|---|
| Happy path con datos | `test_returns_result_with_valid_data` |
| Resultado vacío | `test_returns_empty_when_no_data` |
| Not found / None | `test_returns_none_or_empty_when_not_found` |
| Resolución automática (ej: latest season) | `test_resolves_latest_season` |
| Validación de dominio | `test_raises_error_for_invalid_input` |

No todos aplican a todos los use cases. Agregar los que tengan sentido para la lógica implementada.

---

## Tests de health / integración

`tests/test_health.py` — prueba el endpoint `/api/v1/health` con `httpx.AsyncClient`.
No usar este patrón para unit tests de use cases.

---

## Checklist

- [ ] Correr `pytest tests/` antes de escribir tests nuevos
- [ ] Crear `tests/use_cases/test_verb_noun.py`
- [ ] Implementar `FakeEntityRepository` con todos los métodos del Protocol
- [ ] Escribir mínimo: happy path + vacío + error
- [ ] Verificar que `pytest tests/` pasa al finalizar
- [ ] Verificar coverage: `coverage run -m pytest tests/ && coverage report`
