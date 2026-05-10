# TAREAS PENDIENTES — SFA Backend

---

## 1. Migrar de `create_all` a Alembic

El proyecto usa `Base.metadata.create_all` en el lifespan de FastAPI. Esto no soporta
migraciones incrementales: si una tabla ya existe, no la modifica. Es deuda técnica que
bloquea tener data migrations automáticas (como las de Django).

**Tareas:**
- [ ] Instalar y configurar Alembic con el engine async de SQLAlchemy
- [ ] Generar la migración inicial a partir del schema actual (`alembic revision --autogenerate`)
- [ ] Reemplazar `Base.metadata.create_all` en `main.py` por `alembic upgrade head`
- [ ] Crear spec en `specs/refactor/` para documentar las decisiones

**Impacto directo:** el refactor `0002-league-config-and-provider-registry` necesita una
data migration para cargar los registros de `LEAGUES` → `league_configs` + `providers` +
`league_provider_mappings` automáticamente al hacer `alembic upgrade head`.

---

## 2. Implementar archivos .http faltantes y probar flujo completo

Crear `http/admin.http` con todos los endpoints de admin, y verificar que el
flujo completo de ingesta funciona end-to-end.

**Archivos .http existentes:**
- `http/ranking.http` ✓
- `http/players.http` ✓
- `http/competitions.http` ✓
- `http/compare.http` ✓
- `http/status.http` ✓

**Pendiente crear:**
- [x] `http/admin.http` — todos los endpoints `POST /admin/*`:
  - `POST /admin/ingest/{league_id}`
  - `POST /admin/ingest-all`
  - `POST /admin/enrich-fbref/{competition_id}`
  - `POST /admin/enrich-understat/{competition_id}`
  - `POST /admin/enrich-all`
  - `POST /admin/recalculate/{competition_id}`
  - `GET /admin/ingestion-logs`

**Flujo completo a probar:**
- [x] Levantar stack con Docker Compose
- [x] Correr migraciones
- [x] `POST /admin/ingest/140` (La Liga, season=2024)
- [x] Verificar datos en `GET /ranking`
- [x] `POST /admin/enrich-fbref/1?competition_name=La+Liga&season=2024`
- [x] `POST /admin/enrich-understat/1?competition_name=La+Liga&season=2024&season_int=2024`
- [x] Verificar que los scores cambiaron en `GET /players/{id}/events`

---

## 2. Implementar Swagger / OpenAPI

- Configurar FastAPI para generar documentación OpenAPI automática
- Añadir `response_model`, descripciones y ejemplos en cada endpoint
- Validar que los schemas en `api/v1/schemas/` estén completos
- Exponer `/docs` y `/redoc` en entorno de desarrollo

---

## 3. Evaluar qué endpoints requieren auth

Revisar todos los routers en `api/v1/` y determinar cuáles deben estar protegidos:
- [ ] Mapear cada endpoint con su nivel de exposición (público / interno / admin)
- [ ] Definir estrategia de autenticación (API key, JWT, OAuth2)
- [ ] Identificar endpoints de admin que deben bloquearse en producción
- [ ] Decidir si se implementa auth a nivel de router o middleware

---

## 4. UI en React (post-optimización backend)

Una vez el backend esté estable y optimizado:
- Scaffoldear proyecto React (Vite)
- Implementar vistas: Ranking, Detalle de jugador, Comparador
- Conectar con la API del backend
- Deploy coordinado con Docker Compose

---

## 5. Auditoría de Variables Hardcodeadas

Rastrear todas las variables con valores fijos en el código y evaluar cada una:
- `KNOWN_POSITIONS` (`domain/position_mapping.py`) — lista manual de jugadores
- `BASE_POINTS_TABLE` (`domain/scoring/services.py`) — tabla de puntos por posición/acción
- `LEAGUES` (`use_cases/ingest_competition.py`) — lista de ligas con IDs y factores
- `ROUND_TO_STAGE` — mapeo de rondas de Champions a instancias SFA
- Factores de competición (`comp_factor`, `stage_factor`)

Para cada variable determinar:
- [ ] ¿Tiene sentido hardcodeada? (cambia poco, es config de negocio)
- [ ] ¿Mejora con BD? (cambia frecuentemente, depende de datos externos)
- [ ] ¿Es peligrosa hardcodeada? (puede causar errores silenciosos o scoring incorrecto)

RECOMENDACION: Usar un LLM o alguna herramienta de busqueda para indagar o clasificar la posicion de ciertos jugadores
o usar tavily search
