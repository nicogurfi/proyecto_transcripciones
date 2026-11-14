# Memoria de decisiones

## 1. Cómo entendí el problema

El operador **no despacha**: contiene al llamante, extrae y valida datos, transmite instrucciones y deriva una carta. Por eso el copiloto no "resuelve" el caso. Su trabajo es:

1. **Estructurar lo dicho**, mostrando también lo que *falta*. El campo vacío es información: le dice al operador qué preguntar.
2. **No sobreestimular.** Ninguna sugerencia aparece sin pedirla. Las contraindicaciones críticas ("NO retirar el casco", "NO usar agua: litio") salen de reglas por palabras clave con margen de error: pueden dispararse de más, por ejemplo con negaciones como "no tenía casco". Por eso no se imponen en pantalla. Se ve solo un contador en rojo y la barra se despliega con `Alt+5`, mostrando la palabra que la disparó y un aviso para confirmar con el llamante. *Trade-off:* el operador tiene que pedirla, pero el contador rojo hace difícil ignorarla.
3. **Cada segundo cuenta.** El análisis llega en dos fases por streaming. Las reglas responden en unos 35 ms y el LLM refina después, así que el operador nunca espera al modelo.

## 2. Supuestos

- **Ubicación primero.** Los pasos siguen el orden estándar de 911: Ubicación → Qué pasó → Personas y riesgos → Interrogatorio → Pre-arribo → Carta. Si la llamada se corta, al menos se sabe dónde es.
- **P4 no existe en el dataset** (solo P1–P3). Lo definí como "No urgente / informativo" (reclamos, hechos de hace días).
- **P1 exige evidencia explícita** de riesgo de vida: atrapados, sin respuesta, compromiso respiratorio, fuego activo, gas, etc. Si los casos parecidos sugieren P1 pero el relato no tiene ninguna señal, propongo P2 con confianza baja y lo marco como inconsistencia para verificar. Ante discrepancia entre reglas y LLM, **se toma la prioridad más grave**.
- **La llamada evoluciona.** Para datos que cambian (estado de las personas, atrapamiento), el valor actual es **el último dicho** y el anterior queda como historial: "está bien (antes: se desmayó)". El cambio se informa en F4 para confirmarlo. Si una señal de riesgo de vida parece resolverse ("ya reaccionó", "ya salió"), **la prioridad no baja sola**: se mantiene la más grave, baja la confianza y se pide al operador que evalúe. Bajar un P1 por una frase mal interpretada es el error más caro.
- **Recursos de despacho**: se muestran solo como referencia, y aclarando que la decisión es del despachador CAD.
- **El número de rellamada** no está en las transcripciones. Queda como pregunta base del checklist (en un sistema real lo aporta el ANI).

### Observaciones sobre el dataset

- **El dataset mezcla lo dicho con lo inferido.** Algunos ejemplos:
  - el caso 001 dice "casi Montevideo", pero la referencia es "Montevideo **y Paraná**";
  - el caso 004 tiene altura "4500", que no aparece en el relato.

  Si se usara el CSV como ejemplo de extracción (few-shot), se le enseñaría al modelo a **inventar esquinas**. Por eso el few-shot es **solo de clasificación** (categoría, subcategoría y prioridad), y la evaluación compara la altura y las esquinas solo cuando fueron dichas.
- **Hay contradicciones reales que sirven de prueba para F4**:
  - caso 016: "Buen día" a las 02:45;
  - caso 024: el operador saluda con "buen día" a las 16:35.
- **Las preguntas pendientes no siempre están dentro de las obligatorias.** El checklist usa la unión de ambas, sin duplicados (comparación aproximada más embeddings).
- **30 casos con 30 subcategorías distintas.** En leave-one-out ningún caso tiene un "hermano" en el catálogo: la similitud máxima entre subcategorías distintas ronda 0,68. Por eso el protocolo específico de una subcategoría solo se aplica con similitud ≥ 0,75. Por debajo se usa el protocolo de la categoría y la subcategoría se muestra como **"orientativa"**.

## 3. Control de alucinaciones y resiliencia

| Riesgo | Mitigación |
|---|---|
| El LLM inventa un dato | Cada dato "dicho" debe venir con una **cita textual** que se localiza en la transcripción (coincidencia aproximada ≥ 85). Si no aparece, se descarta y queda registrado en "notas del modelo". |
| Completa una esquina o altura no dicha | Además de la cita, **cada calle propuesta debe haber sido dicha** (literal o resuelta por el callejero). El caso "Montevideo y Paraná" se descarta: hay test. |
| JSON malformado (fences, texto extra, comas colgantes) | Parseo tolerante → validación Pydantic → **un reintento** con el error de validación → fallback a reglas. |
| Valores fuera de dominio | Categorías inventadas → `null`. "prioridad 1" → `P1`. Campos extra → se ignoran. |
| LLM lento o caído | `asyncio.wait_for` con timeout. La fase rápida ya está en pantalla. |
| Confianza "autodeclarada" | No se le pide el % al LLM. La confianza **se calcula**: método de extracción, coincidencia en el callejero, acuerdo entre reglas y LLM, dudas del llamante en el mismo fragmento, y altura o cruce inválidos. |
| Dirección inexistente | Validación offline contra el callejero oficial (existencia, rango de altura, que las calles se crucen) y doble chequeo online con USIG. |

**Patrón dual provider.** `LLMProvider` tiene tres implementaciones: `MockProvider`, `AnthropicProvider` y `OpenAICompatibleProvider` (este último cubre OpenAI, Groq, Gemini, Ollama y vLLM). El mock devuelve **el mismo esquema JSON que un LLM**, construido con las reglas. Así, en modo offline se ejercita el pipeline completo (parseo, validación, verificación y fusión), no un atajo.

## 4. Decisiones técnicas y trade-offs

- **Reglas + gazetteer como base, LLM como refinamiento.** Una dirección mal leída es el error más caro en sala. El callejero oficial (2.548 calles, con alturas y cruces) da precisión, velocidad y explicabilidad que un LLM solo no garantiza. *Trade-off:* las reglas cubren menos variantes del lenguaje; eso lo absorbe el LLM cuando está disponible.
- **Normalización fonética rioplatense** (b/v, s/z/c, ll/y, h muda, E protética: "Escalabrini Ortis" → Scalabrini Ortiz) más coincidencia aproximada con umbral alto. Para evitar falsos positivos ("Belgrano R", "Plaza Almagro", "vías del Mitre"), una calle solo se acepta con contexto: "en", "Av.", "al 800", "y", "entre", mayúscula. Lo que solo coincide de forma aproximada se informa en F4 ("¿quiso decir…?").
- **Embeddings**: `paraphrase-multilingual-MiniLM-L12-v2` vía fastembed (ONNX, CPU, unos 30 ms), incluido en la imagen. *Vector store* = numpy en memoria: 30 casos no justifican Chroma ni pgvector. Hay fallback determinista por hashing de n-gramas para que `docker compose up` nunca falle por el modelo.
- **Streaming NDJSON** en lugar de WebSocket: más simple, funciona a través de nginx (`proxy_buffering off`) y alcanza para el patrón petición → 2 respuestas.
- **SQLite**: cartas, **correcciones del operador** (pares sugerido → final, que son el dataset para recalibrar y reentrenar) y sesiones de simulacro.
- **Contratos duplicados Pydantic ↔ Zod**: la UI valida cada respuesta. Si el contrato cambia, falla de forma explícita en lugar de mostrar datos corruptos. *Trade-off:* hay que mantener dos definiciones (con más tiempo se generarían desde OpenAPI).
- **Leave-one-out en evaluación, pero no en la UI.** En la demo, cargar un caso del dataset lo encuentra en el catálogo, como en un sistema real con protocolos cargados. La evaluación sí lo excluye para medir la generalización honestamente.
- **Mapa con teselas OSM**: requiere internet. Sin red se muestran las coordenadas y la validación sigue funcionando.

## 5. Módulo de simulacro

Para evitar la **atrofia de habilidades**, el operador resuelve casos **sin copiloto**: la llamada llega de a poco y hay variantes "ruidosas" con errores fonéticos, muletillas y sin puntuación. Se evalúa contra la referencia en calle, altura, esquina dicha, tipo, prioridad (exacta o ±1), preguntas pendientes identificadas (comparación semántica) e instrucciones. Al final se muestra qué habría sugerido el copiloto. Cada sesión queda registrada.

## 6. Qué haría con más tiempo

1. **Calibración de la confianza** con las correcciones registradas, para que "80%" signifique 80% de acierto real.
2. **Más casos de catálogo** por subcategoría (protocolos reales tipo MPDS o APCO) y clasificador supervisado de subcategoría.
3. **Entrada de audio**: ASR en streaming (Whisper) con diarización; el pipeline ya trabaja turno a turno.
4. **Normalización de números hablados** ("al ochocientos cincuenta") y de puntos de referencia (estaciones, hospitales, plazas → coordenadas).
5. Integración real con CAD (HL7 o APIs del despacho) y con el ANI/ALI de la telefonía.
6. Generar los tipos de TypeScript desde OpenAPI, tests E2E (Playwright) en CI y métricas de latencia en producción.
7. Modo multi-operador con historial de llamadas en paralelo y supervisor.
