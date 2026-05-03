---
name: sfa-celery-task
description: Guía para crear Celery tasks en SFA. Cubre el patrón sync→async, late imports para evitar circular imports, manejo de sesión, retries y registro en beat schedule.
---

# SFA Celery Task

## Cuándo usar

Cuando una operación debe ejecutarse de forma asíncrona o periódica: ingestion, enrichment,
recalculación de scores, notificaciones, etc.

## Patrón completo

### Estructura básica: sync wrapper → async helper

```python
import asyncio

from sfa.celery_app import celery_app


# --- Sync task (entry point) ---

@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def verb_noun_task(self, param1: int, param2: str):
    """Descripción breve de la task. Thin sync → async wrapper."""
    try:
        asyncio.run(_run_verb_noun(param1, param2))
    except Exception as exc:
        raise self.retry(exc=exc)


# --- Async helper (implementación real) ---

async def _run_verb_noun(param1: int, param2: str) -> None:
    # IMPORTANTE: todos los imports van aquí (late imports)
    # Razón: el worker Celery carga el módulo antes de que la app esté lista
    from sfa.application.use_cases.verb_noun import VerbNounUseCase
    from sfa.core.config import get_settings
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.providers.some_provider import SomeProvider
    from sfa.infrastructure.repositories.entity_repository import EntityRepository

    settings = get_settings()
    provider = SomeProvider(settings.SOME_API_KEY)

    async with AsyncSessionLocal() as session:
        repo = EntityRepository(session)
        use_case = VerbNounUseCase(repo)
        result = await use_case.execute(param1, param2)
        await session.commit()

    return result
```

### Task de batch (itera múltiples items)

```python
@celery_app.task(bind=True, max_retries=1)
def process_all_task(self, season: int):
    """Procesa todos los items configurados."""
    try:
        asyncio.run(_run_process_all(season))
    except Exception as exc:
        raise self.retry(exc=exc)


async def _run_process_all(season: int) -> None:
    from sfa.application.use_cases.process_item import ProcessItemUseCase, ITEMS_CONFIG
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.repositories.entity_repository import EntityRepository

    async with AsyncSessionLocal() as session:
        repo = EntityRepository(session)
        use_case = ProcessItemUseCase(repo)
        for item in ITEMS_CONFIG:
            result = await use_case.execute(item, season)
            # Commit por item para no perder progreso si falla a mitad
            await session.commit()
```

### Registrar en `src/sfa/celery_app.py` (si es periódica)

```python
celery_app.conf.beat_schedule = {
    ...,
    "verb-noun-every-8h": {
        "task": "sfa.tasks.module_tasks.verb_noun_task",
        "schedule": crontab(hour="*/8"),
        "args": (2024,),  # argumentos fijos de la schedule
    },
}
```

---

## Parámetros de retry recomendados

| Tipo de task | max_retries | default_retry_delay |
|---|---|---|
| Ingestion (API externa) | 3 | 300s (5 min) |
| Enrichment (scraping) | 2 | 600s (10 min) |
| Batch completo | 1 | — |
| Recalculación (DB only) | 2 | 300s |

---

## Reglas

- Los imports van SIEMPRE dentro del helper async — nunca en el top level del módulo
- Razón: el worker Celery importa `sfa.tasks.*` antes de que la app FastAPI esté configurada
- `session.commit()` se llama en el helper async, NO en el use case
- Para batch tasks: considerar commit por item para preservar progreso parcial
- Nunca pasar instancias de ORM models como argumentos a la task — pasar IDs
- El task sync es solo el wrapper; toda la lógica va en el helper async
- El nombre del task en `beat_schedule` debe ser el path completo: `sfa.tasks.module.task_name`

---

## Checklist de creación

- [ ] Crear o agregar en `src/sfa/tasks/module_tasks.py` el sync wrapper + async helper
- [ ] Verificar que el módulo de tasks está en `celery_app.autodiscover_tasks([...])`
  (ya está configurado para `["sfa.tasks"]` — no necesita cambio si el archivo está en tasks/)
- [ ] Si es periódica: agregar entrada en `celery_app.conf.beat_schedule`
- [ ] Si se dispara manualmente: agregar endpoint en `api/v1/admin.py`
