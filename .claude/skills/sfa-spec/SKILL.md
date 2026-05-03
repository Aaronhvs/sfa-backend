---
name: sfa-spec
description: Creates a new spec for SFA Backend. Invoked exclusively by the Architecture-Engineer agent at the end of the design phase. Produces decisions.md and plan.md in the correct specs/ directory. Never invoked directly by the user.
---

# SFA Spec

Crea los archivos de spec para una feature o refactor. Siempre produce dos archivos:
`decisions.md` (contexto y decisiones) y `plan.md` (checklist de implementación).

## Numeracion

1. Listar todas las carpetas en `specs/feature/` y `specs/refactor/`
2. Extraer los números de prefijo (`NNNN`)
3. El número del nuevo spec = el más alto encontrado + 1 (padding a 4 dígitos: `0003`)
4. El slug es un string corto en kebab-case que describe la feature

## Tipo de spec

- `specs/feature/NNNN-slug/` — nueva funcionalidad
- `specs/refactor/NNNN-slug/` — cambio estructural sin nueva funcionalidad

## Template: decisions.md

```markdown
# [Título del spec]

## Contexto de negocio

[Qué problema resuelve esta feature. Por qué ahora. Qué impacto tiene en el producto.]

## Restricciones

- [Restricción técnica o de negocio relevante]
- [Dependencias externas, APIs, rate limits, etc.]

## Decisiones tomadas

| Decisión | Alternativa descartada | Razón |
|---|---|---|
| [decisión elegida] | [lo que se descartó] | [por qué] |

## Domain Model (si aplica)

[Solo si la feature requiere nuevas entidades de dominio — producido por @DDD-Designer]

### Nuevas entidades

[Nombre, atributos, invariantes]

### Value objects nuevos

[Nombre, reglas de construcción, clamping]

### Ubicación propuesta en domain/

[Rutas de archivos a crear dentro de src/sfa/domain/]

## Integraciones externas

[APIs externas involucradas, autenticación, rate limits, fallbacks]
```

## Template: plan.md

```markdown
# Plan: [Título del spec]

## Archivos a crear

- [ ] `ruta/al/archivo.py` — [descripción de qué hace]
- [ ] `ruta/al/archivo2.py` — [descripción]

## Archivos a modificar

- [ ] `ruta/existente.py` — [qué cambio específico]

## Checklist de implementación

- [ ] [Paso 1 — descripción concreta y accionable]
- [ ] [Paso 2] [DDD] — si este paso requiere modelado de dominio
- [ ] [Paso 3]
- [ ] Agregar factory en `core/dependencies.py`
- [ ] Registrar router en `main.py` (si aplica)
- [ ] Crear archivo `.http` en `http/` (si hay endpoint nuevo)
- [ ] Escribir tests en `tests/use_cases/`
- [ ] Verificar `pytest tests/` pasa con coverage ≥80%
- [ ] Verificar `flake8 src/ tests/` sin errores
- [ ] Verificar `isort --check-only src/ tests/` sin errores

## Agent Routing Brief

**DDD Designer needed:** yes / no

[Si yes: explicar qué entidades de dominio requiere esta feature y por qué el DDD Designer
debe modelarlas antes de que comience la implementación.]

[Si no: justificar brevemente por qué la feature no requiere nuevas entidades de dominio.]

## Verificación

[Cómo verificar end-to-end que la feature funciona correctamente:]
1. [Paso de verificación 1 — comando, endpoint o assertion específica]
2. [Paso de verificación 2]
```

## Reglas

- Solo se crean los archivos del spec — nunca se escribe el contenido del plan como texto
  suelto en el chat
- El spec es el contrato entre Chat 1 (diseño) y Chat 2 (implementación)
- La implementación NO puede comenzar sin un spec válido con decisions.md y plan.md
- Si el spec tiene tag `[DDD]` en algún ítem, el Agent Routing Brief DEBE indicar "yes"
  con justificación
