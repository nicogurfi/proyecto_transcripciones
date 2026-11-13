import json

from fastapi.testclient import TestClient

from app.main import app


def _stream(client, payload):
    r = client.post("/api/analizar", json=payload)
    assert r.status_code == 200
    return [json.loads(line) for line in r.text.strip().splitlines()]


def test_flujo_punta_a_punta_mock():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["proveedor"] == "mock"
        caso = client.get("/api/casos/SFX-REC-2026-005").json()
        fases = _stream(client, {"turnos": caso["turnos"], "timestamp": caso["timestamp"]})
        assert [f["fase"] for f in fases] == ["rapida", "final"]
        final = fases[-1]
        assert final["ficha"]["ubicacion"]["calle"]["value"] == "Av. San Juan"
        assert any("casco" in a["texto"] for a in final["alertas_criticas"])
        valores = {"ubicacion.calle": "Av. San Juan", "ubicacion.interseccion": "Av. Entre Rios",
                   "suceso.categoria": "ACCIDENTE_VIAL", "prioridad": "P1"}
        carta = client.post("/api/cartas", json={
            "turnos": caso["turnos"], "valores_finales": valores,
            "valores_sugeridos": {**valores, "prioridad": "P2"}, "geo": final["geo"],
        }).json()
        assert carta["numero"].startswith("CL-")
        assert carta["correcciones_operador"] == 1
        assert "CARTA DE LLAMADA" in carta["texto_plano"]


def test_texto_vacio_es_422():
    with TestClient(app) as client:
        assert client.post("/api/analizar", json={"texto": "  "}).status_code == 422


def test_simulacro():
    with TestClient(app) as client:
        caso = client.get("/api/simulacro/caso?dificultad=ruidosa").json()
        res = client.post("/api/simulacro/evaluar", json={
            "caso_id": caso["caso_id"], "calle": "Corrientes", "categoria": "INCENDIO_RESCATE", "prioridad": "P1",
            "preguntas_pendientes": ["¿Hay gas?"], "instrucciones": "No reingresar", "tiempo_segundos": 40,
        }).json()
        assert 0 <= res["porcentaje"] <= 100 and res["items"]


def test_revalidar_direccion_corregida_por_operador():
    with TestClient(app) as client:
        ok = client.post("/api/geo/validar", json={"calle": "Thames", "altura": "1900", "entre_calles": "Nicaragua y Costa Rica"}).json()
        assert ok["estado"] == "validada"
        mal = client.post("/api/geo/validar", json={"calle": "Thames", "altura": "4800", "interseccion": "Cabildo"}).json()
        assert mal["estado"] == "no_validada" and mal["altura_en_rango"] is False and mal["cruce_valido"] is False
