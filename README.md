# Copiloto de Sala

Asistente para operadores de atención de emergencias (911 / 103 / 107 / 147). Procesa la transcripción de una llamada y, en pantalla:

- segmenta el caso en una **ficha** (ubicación, qué pasó, personas y riesgos) con trazabilidad al texto;
- **valida la dirección** contra el callejero oficial de CABA, con doble chequeo en USIG y mapa;
- guía el **protocolo por pasos** y arma el checklist de preguntas pendientes según el tipo de hecho;
- ofrece **instrucciones de pre-arribo**, **casos similares** e **inconsistencias** solo cuando el operador las pide (F1–F4);
- conforma y **deriva la Carta de Llamada**;
- incluye un **módulo de simulacro** para entrenar sin copiloto.

> Las decisiones de diseño, los supuestos y los trade-offs están en **[DECISIONS.md](DECISIONS.md)**.

---

## Levantar el proyecto

```bash
docker compose up --build
```

| Servicio | URL |
|---|---|
| Panel del operador | **http://localhost:3000** |
| API + documentación OpenAPI | http://localhost:8000/docs |

- **No requiere configuración.** Sin API keys arranca en **modo simulado** (`mock`): determinista, offline y gratis.
- El primer build descarga un modelo de embeddings multilingüe (unos 220 MB) que queda dentro de la imagen. Si el build no tiene internet, el sistema usa un fallback determinista y funciona igual.
- La caché geográfica incluida cubre las direcciones del dataset. Así el mapa y las validaciones funcionan aunque USIG no responda.

### Modo real (LLM)

Copiar `.env.example` a `.env` y definir **una** clave. El proveedor se detecta solo:

```bash
ANTHROPIC_API_KEY=...        # o OPENAI_API_KEY / GEMINI_API_KEY / GROQ_API_KEY
# LLM_MODEL=claude-haiku-5-5   (opcional, cada proveedor tiene un default)
```

Con un modelo local (Ollama o vLLM, API compatible con OpenAI):

```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=llama3.1:8b
```

Si el LLM falla, tarda más de `LLM_TIMEOUT_SECONDS` o devuelve JSON inválido, el operador conserva el resultado de reglas. La UI nunca queda esperando.

---

## Recorrido en 1 minuto

1. Abrir http://localhost:3000 y apretar **`Alt+L`** (o el botón *Cargar*).
2. Elegir un caso, por ejemplo **DEMO-01** (multi-turno con autocorrección) o **DEMO-03** (dirección imposible). Con *Simular en vivo* el relato llega oración por oración y la ficha se va completando.
3. Mirar la ficha:
   - cada dato tiene un punto de confianza (verde, ámbar o rojo), su origen (`dicho`, `inferido` u `operador`) y ✓ para validarlo;
   - al pasar el mouse se resalta en la transcripción el fragmento que lo respalda;
   - un campo vacío indica qué falta preguntar;
   - con un click se corrige un dato (la calle tiene autocompletado del callejero).
4. Abrir las sugerencias solo cuando hacen falta:

   | Tecla | Panel |
   |---|---|
   | `F1` / `Alt+1` | Preguntas pendientes del protocolo (las teclas `1`–`9` las marcan como hechas) |
   | `F2` / `Alt+2` | Instrucciones de pre-arribo para leer al llamante |
   | `F3` / `Alt+3` | Casos similares y recursos (referencia para el despachador) |
   | `F4` / `Alt+4` | Posibles inconsistencias (errores del llamante o de la transcripción) |

5. **Protocolo por pasos.** Por defecto el copiloto se para en el primer paso sin tildar (modo AUTO), pero el operador se mueve libremente:

   | Tecla | Acción |
   |---|---|
   | `Alt+↑` / `Alt+↓` (o `RePág` / `AvPág`) | Paso anterior / siguiente |
   | `Alt+Shift+1…6` o click en el paso | Ir directo a un paso (modo MANUAL) |
   | `Alt+T` o click en el círculo | Tildar / destildar el paso actual |
   | `Alt+0` | Volver al modo automático |

   Ir al paso 4 abre las preguntas (F1) y el paso 5 las instrucciones (F2); los pasos 1–3 resaltan la sección de la ficha.
   Los pasos reaccionan tanto a la transcripción como a las correcciones manuales. Si el operador corrige la dirección, se revalida contra el callejero y USIG, y se actualizan el mapa, el paso 1 y las inconsistencias.
6. **`Ctrl+Enter`** abre la revisión final y vuelve a apretarse para **derivar la carta**.
7. Pestañas **Simulacro** (entrenamiento sin copiloto) y **Cartas** (historial y correcciones registradas).

Con `Alt+N` se escribe un nuevo turno de diálogo y se vuelve a analizar. Con `?` se ven todos los atajos.

---

## Arquitectura

```
┌──────────────────────┐  NDJSON   ┌─────────────────────────────────────────────────────────┐
│ frontend (nginx:3000)│◄─────────►│ backend FastAPI (:8000)                                 │
│ React + TS + Zod     │  /api     │                                                         │
│ Leaflet · atajos     │           │  transcript ─► FASE RÁPIDA (~35 ms)                     │
└──────────────────────┘           │                 reglas + callejero offline + catálogo   │
                                   │                 └─► emite análisis "rapida"             │
                                   │              ─► FASE FINAL                              │
                                   │                 LLMProvider (mock│anthropic│openai…)    │
                                   │                 → parseo resiliente → Pydantic          │
                                   │                 → verificación de evidencia → fusión    │
                                   │                 + USIG online (doble chequeo + coords)  │
                                   │                 └─► emite análisis "final"              │
                                   │  seguridad · protocolo · inconsistencias · carta        │
                                   │  embeddings (MiniLM multilingüe ONNX) · SQLite          │
                                   └─────────────────────────────────────────────────────────┘
```

```
backend/app/
  transcript.py          ingesta y offsets por turno
  text.py                normalización, clave fonética rioplatense, tokenización
  geo/                   callejero CABA (offline) · USIG (online + caché) · validación
  extraction/            reglas (rápido/mock) · LLM (prompt, parseo, verificación) · borrador
  providers/             patrón dual provider: mock | Anthropic | API compatible con OpenAI
  knowledge/             dataset · catálogo de protocolos · embeddings · retriever
  analysis/              pipeline 2 fases · seguridad · protocolo/checklist · inconsistencias
  carta.py · training.py · db.py · main.py
frontend/src/
  api/ (Zod + cliente streaming) · state/useCall.ts · components/ · views/
```

## Calidad

```bash
# tests (offline y deterministas)
cd backend && pip install -r requirements-dev.txt && pytest

# evaluación leave-one-out sobre el dataset
python -m app.evaluation.run          # reglas / mock
python -m app.evaluation.run --llm    # con el proveedor configurado
```

Resultado en modo mock. En cada caso se excluye ese mismo caso del catálogo:

| Métrica (n=30) | Resultado |
|---|---|
| Calle principal correcta | 97% |
| Altura correcta (cuando fue dicha) | 100% |
| Esquina / entre calles capturada (cuando fue dicha) | 75% |
| Categoría correcta | 77% |
| Prioridad exacta / a ±1 nivel | 83% / 100% |
| Prioridad subestimada | 3% |
| Latencia fase rápida p50 / p95 | 34 ms / 56 ms |

Los tests cubren el parseo de JSON malformado, las categorías inventadas por el LLM, el descarte de esquinas no dichas y de evidencia inventada, la fusión con criterio de seguridad, la autocorrección del llamante y el flujo punta a punta de la API hasta la derivación.

## Fuentes de datos

- `dataset_challenge_soflex.csv` (provisto).
- Callejero oficial de CABA (USIG / Buenos Aires Data, licencia CC-BY 2.5 AR), embebido para funcionar offline.
- Normalizador y datos útiles de USIG (GCBA) para la segunda verificación online.
- Teselas del mapa de © OpenStreetMap (requieren conexión; sin red se muestran las coordenadas).
