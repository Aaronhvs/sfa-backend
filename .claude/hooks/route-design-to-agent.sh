#!/usr/bin/env bash
# route-design-to-agent.sh
#
# UserPromptSubmit hook — detecta solicitudes de diseño/planificación y bloquea
# la respuesta directa de Claude, forzando el uso de @Architecture-Engineer.
#
# Input: JSON via stdin con el campo "prompt"
# Exit 0 → permitir respuesta normal
# Exit 2 → bloquear y mostrar mensaje al usuario

set -euo pipefail

# Leer el prompt del JSON de entrada
PROMPT=$(cat | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('prompt', '').lower())
except Exception:
    print('')
")

# Keywords que indican una solicitud de diseño/planificación
DESIGN_KEYWORDS=(
    "diseña"
    "diseñar"
    "diseñemos"
    "planifica"
    "planificar"
    "planifiquemos"
    "crea un spec"
    "crear un spec"
    "arma un plan"
    "armar un plan"
    "quiero un plan"
    "necesito un plan"
    "necesito un spec"
    "montar un flujo"
    "nueva feature"
    "nueva funcionalidad"
    "nuevo módulo"
    "nuevo modulo"
    "agregar un endpoint"
    "añadir un endpoint"
    "implementar una feature"
    "quiero diseñar"
    "quiero planificar"
)

for keyword in "${DESIGN_KEYWORDS[@]}"; do
    if echo "$PROMPT" | grep -qi "$keyword"; then
        echo "Esta solicitud requiere el agente de diseño. Por favor invoca @Architecture-Engineer para que analice el codebase, tome las decisiones arquitectónicas y produzca el spec en specs/NNNN-slug/. No se puede implementar sin un spec válido."
        exit 2
    fi
done

exit 0
