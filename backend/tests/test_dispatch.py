import json

from fastapi.testclient import TestClient

from app.analysis.dispatch import nota_operativa, recursos_sugeridos
from app.config import DATA_DIR
from app.main import app


def _final(client, turnos, timestamp=None):
    r = client.post("/api/analizar", json={"turnos": turnos, "timestamp": timestamp})
    return [json.loads(x) for x in r.text.strip().splitlines()][-1]


def test_caso_nuevo_no_copia_recursos_de_un_caso_distinto():
    demo = json.loads((DATA_DIR / "demo_casos.json").read_text(encoding="utf-8"))[0]  # señor descompuesto
    with TestClient(app) as client:
        final = _final(client, demo["turnos"], demo["timestamp"])
    textos = " ".join(r["texto"] for r in final["recursos_sugeridos"])
    assert "anticonvulsivantes" not in textos.lower()
    assert all(r["fuente"] == "regla" for r in final["recursos_sugeridos"])
    assert any("SAME" in r["texto"] for r in final["recursos_sugeridos"])


def test_caso_del_catalogo_usa_sus_recursos():
    with TestClient(app) as client:
        caso = client.get("/api/casos/SFX-REC-2026-012").json()  # fuga de gas
        final = _final(client, caso["turnos"], caso["timestamp"])
    assert final["recursos_sugeridos"][0]["fuente"].startswith("catálogo")


def test_reglas_por_riesgo():
    valores = {"suceso.categoria": "DEFENSA_CIVIL", "riesgos": "Gas / riesgo de explosión; Riesgo eléctrico"}
    textos = [r.texto for r in recursos_sugeridos(valores, [], None, "hay olor a gas y cables caídos")]
    assert any("Metrogas" in t for t in textos) and any("Edesur" in t for t in textos)


def test_nota_operativa_solo_con_datos_de_la_ficha():
    valores = {"suceso.categoria": "EMERGENCIA_MEDICA", "ubicacion.calle": "Av. Rivadavia", "ubicacion.altura": "4520",
               "personas.victimas": "papá (67 años)", "personas.estado": "no me contesta"}
    nota = nota_operativa(valores, None, ["Mantener la vía aérea libre."])
    assert nota.startswith("Emergencia médica en Av. Rivadavia 4520 (dirección sin validar).")
    assert "papá (67 años) – no me contesta" in nota and "Mantener la vía aérea libre" in nota


def test_previsualizar_no_guarda_y_respeta_nota_editada():
    with TestClient(app) as client:
        antes = len(client.get("/api/cartas").json())
        body = {"turnos": [{"speaker": "llamante", "text": "Hay fuego en Yerbal 2450"}],
                "valores_finales": {"ubicacion.calle": "Yerbal", "ubicacion.altura": "2450", "suceso.categoria": "INCENDIO_RESCATE"}}
        prev = client.post("/api/cartas/previsualizar", json=body).json()
        assert prev["numero"] == "BORRADOR" and "Yerbal 2450" in prev["nota_operativa"]
        assert len(client.get("/api/cartas").json()) == antes
        carta = client.post("/api/cartas", json={**body, "nota_operativa": "Nota escrita por el operador"}).json()
        assert carta["nota_operativa"] == "Nota escrita por el operador"
        assert "NOTA OPERATIVA: Nota escrita por el operador" in carta["texto_plano"]


def test_subtipo_orientativo_no_va_a_la_carta():
    with TestClient(app) as client:
        body = {"turnos": [{"speaker": "llamante", "text": "mi papá no me contesta"}],
                "valores_finales": {"suceso.categoria": "EMERGENCIA_MEDICA", "suceso.subcategoria": "Convulsión en Restaurante"},
                "valores_sugeridos": {"suceso.subcategoria": "Convulsión en Restaurante"},
                "confianzas": {"suceso.subcategoria": 0.3}}
        prev = client.post("/api/cartas/previsualizar", json=body).json()
        assert prev["subcategoria"] is None and "Convulsión" not in prev["nota_operativa"]
        validado = client.post("/api/cartas/previsualizar", json={**body, "campos_validados": ["suceso.subcategoria"]}).json()
        assert validado["subcategoria"] == "Convulsión en Restaurante"


def test_cartas_viejas_sin_campos_nuevos_siguen_listandose():
    import json as _json

    from app import db

    vieja = {"numero": "CL-20200101-0001", "creada": "2020-01-01T00:00:00", "estado": "DERIVADA", "completa": True,
             "advertencias": [], "origen": "TELEFONIA_911", "prioridad": "P2", "categoria": None, "subcategoria": None,
             "direccion": "Yerbal 2450", "direccion_validada": False, "lat": None, "lon": None, "barrio": None,
             "comisaria_vecinal": None, "resumen": "x", "personas": None, "riesgos": None, "preguntas_respondidas": [],
             "preguntas_pendientes": [], "instrucciones_transmitidas": [], "alertas_criticas": [], "recursos_sugeridos": [],
             "notas_operador": None, "correcciones_operador": 0, "duracion_segundos": None, "texto_plano": "x"}
    with db.connect() as c:
        c.execute("INSERT OR REPLACE INTO cartas(numero, creada, prioridad, categoria, direccion, payload) VALUES (?,?,?,?,?,?)",
                  (vieja["numero"], vieja["creada"], "P2", None, vieja["direccion"], _json.dumps(vieja)))
    with TestClient(app) as client:
        cartas = client.get("/api/cartas").json()
    v = next(c for c in cartas if c["numero"] == "CL-20200101-0001")
    assert v["nota_operativa"] == "" and v["recursos_detalle"] == []
