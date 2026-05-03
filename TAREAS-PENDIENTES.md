# TAREAS PENDIENTES — SFA Backend

---

## 1. Auditoría de Variables Hardcodeadas

Rastrear todas las variables con valores fijos en el código y evaluar cada una:
- `KNOWN_POSITIONS` (`domain/position_mapping.py`) — lista manual de jugadores
- `BASE_POINTS_TABLE` (`domain/scoring/services.py`) — tabla de puntos por posición/acción
- `LEAGUES` (`_archive/api_football_ingest_v5.py`, `use_cases/ingest_competition.py`) — lista de ligas con IDs y factores
- `ROUND_TO_STAGE` — mapeo de rondas de Champions a instancias SFA
- Factores de competición (`comp_factor`, `stage_factor`)

Para cada variable determinar:
- [ ] ¿Tiene sentido hardcodeada? (cambia poco, es config de negocio)
- [ ] ¿Mejora con BD? (cambia frecuentemente, depende de datos externos)
- [ ] ¿Es peligrosa hardcodeada? (puede causar errores silenciosos o scoring incorrecto)

RECOMENDACION: Usar un LLM o alguna herramienta de busqueda para indagar o clasificar la posicion de ciertos jugadores
o usar tavily search
---

## 2. Guía de Ejecución y Entendimiento de la App

Crear un documento técnico que cubra:
- Cómo levantar la app (local y con Docker)
- Qué hace cada endpoint (con inputs, outputs y ejemplos)
- Qué hace cada Celery task (`ingestion_tasks.py`)
- Cómo leer el flujo completo: API → Use Case → Domain → Infrastructure
- Qué tiene y qué le falta al sistema hoy

---

## 3. Documento: Legacy vs. Estado Actual

Crear un documento que explique:
- Cómo estaba estructurado el sistema legacy (`_archive/`)
- Qué cambió y por qué (arquitectura hexagonal, separación de capas)
- Mapa comparativo: archivo viejo → equivalente actual
- Qué decisiones de diseño se tomaron y con qué razonamiento

---

## 4. Documentación de Endpoints

Documentar todos los endpoints del API:
- `GET /v1/players`
- `GET /v1/players/{id}`
- `GET /v1/ranking`
- `GET /v1/compare`
- `GET /v1/competitions`
- `GET /v1/status`
- `GET /v1/health`
- `POST /v1/admin/*` (ingestión)

Para cada uno: descripción, parámetros, respuesta esperada, errores posibles.

---

## 5. Implementar Swagger / OpenAPI

- Configurar FastAPI para generar documentación OpenAPI automática
- Añadir `response_model`, descripciones y ejemplos en cada endpoint
- Validar que los schemas en `api/v1/schemas/` estén completos
- Exponer `/docs` y `/redoc` en entorno de desarrollo

---

## 6. Ecosistema con IA (Skills + Agents)

Montar infraestructura de desarrollo asistido por IA:
- Definir y documentar skills de GitHub Copilot para el proyecto
- Configurar Claude agents para tareas recurrentes (ingestión, scoring, debug)
- Integrar subagents en VSCode con sus herramientas equivalentes
- Documentar cómo usar cada agente/skill en el flujo de desarrollo

---

## 7. UI en React (post-optimización backend)

Una vez el backend esté estable y optimizado:
- Scaffoldear proyecto React (Vite)
- Implementar vistas: Ranking, Detalle de jugador, Comparador
- Conectar con la API del backend
- Deploy coordinado con Docker Compose
