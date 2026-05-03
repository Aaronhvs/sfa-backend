# TAREAS PENDIENTES — SFA Backend

---

## 1. Implementar archivos .http faltantes y probar flujo completo

Crear `http/admin.http` con todos los endpoints de admin, y verificar que el
flujo completo de ingesta funciona end-to-end.

**Archivos .http existentes:**
- `http/ranking.http` ✓
- `http/players.http` ✓
- `http/competitions.http` ✓
- `http/compare.http` ✓
- `http/status.http` ✓

**Pendiente crear:**
- [ ] `http/admin.http` — todos los endpoints `POST /admin/*`:
  - `POST /admin/ingest/{league_id}`
  - `POST /admin/ingest-all`
  - `POST /admin/enrich-fbref/{competition_id}`
  - `POST /admin/enrich-understat/{competition_id}`
  - `POST /admin/enrich-all`
  - `POST /admin/recalculate/{competition_id}`
  - `GET /admin/ingestion-logs`

**Flujo completo a probar:**
- [ ] Levantar stack con Docker Compose
- [ ] Correr migraciones
- [ ] `POST /admin/ingest/140` (La Liga, season=2024)
- [ ] Verificar datos en `GET /ranking`
- [ ] `POST /admin/enrich-fbref/1?competition_name=La+Liga&season=2024`
- [ ] `POST /admin/enrich-understat/1?competition_name=La+Liga&season=2024&season_int=2024`
- [ ] Verificar que los scores cambiaron en `GET /players/{id}/events`

---

## 2. Implementar Swagger / OpenAPI

- Configurar FastAPI para generar documentación OpenAPI automática
- Añadir `response_model`, descripciones y ejemplos en cada endpoint
- Validar que los schemas en `api/v1/schemas/` estén completos
- Exponer `/docs` y `/redoc` en entorno de desarrollo

---

## 3. UI en React (post-optimización backend)

Una vez el backend esté estable y optimizado:
- Scaffoldear proyecto React (Vite)
- Implementar vistas: Ranking, Detalle de jugador, Comparador
- Conectar con la API del backend
- Deploy coordinado con Docker Compose

---

## 4. Auditoría de Variables Hardcodeadas

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
