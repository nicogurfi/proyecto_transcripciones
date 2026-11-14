import json

import pytest

from app.extraction.draft import Draft, Hallazgo
from app.extraction.llm import parse_llm_json, to_campos, validate_extraction
from app.analysis.pipeline import merge
from app.transcript import Document, parse_raw_transcript

DOC = Document.from_turns(parse_raw_transcript(
    "Operador: 911. Llamante: Se prendió fuego la cocina de la pizzería de Av. Corrientes 1540 casi Montevideo, adentro quedó el cocinero."
))


def test_json_con_fences_y_comas_colgantes():
    raw = "Claro, acá está:\n```json\n{\"suceso\": {\"categoria\": \"incendio_rescate\",},}\n```"
    data = parse_llm_json(raw)
    assert data["suceso"]["categoria"] == "incendio_rescate"


def test_respuesta_sin_json_falla_con_error_util():
    with pytest.raises(ValueError):
        validate_extraction("No puedo ayudar con eso.")


def test_campos_desconocidos_y_categoria_inventada_se_toleran():
    ext = validate_extraction(json.dumps({"suceso": {"categoria": "TERREMOTO"}, "extra": 1, "prioridad": {"valor": "prioridad 1"}}))
    assert ext.suceso.categoria is None
    assert ext.prioridad.valor == "P1"


def test_esquina_no_dicha_se_descarta():
    # El dataset dice "Montevideo y Paraná" pero "Paraná" no está en el relato.
    ext = validate_extraction(json.dumps({"ubicacion": {
        "calle": {"valor": "Av. Corrientes", "evidencia": "Av. Corrientes 1540"},
        "interseccion": {"valor": "Montevideo y Paraná", "evidencia": "casi Montevideo"},
    }}))
    notas = []
    campos = to_campos(ext, DOC, notas)
    assert "ubicacion.calle" in campos
    assert "ubicacion.interseccion" not in campos
    assert any("Paraná" in n for n in notas)


def test_evidencia_inventada_se_descarta():
    ext = validate_extraction(json.dumps({"personas": {"estado": {"valor": "inconsciente", "evidencia": "el cocinero está inconsciente"}}}))
    notas = []
    assert "personas.estado" not in to_campos(ext, DOC, notas)


def test_fusion_prioridad_toma_la_mas_grave():
    rules = Draft(campos={"prioridad": Hallazgo("P3", [], "reglas", 0.6, source="inferido")})
    llm = {"prioridad": Hallazgo("P1", [], "LLM", 0.7, source="inferido")}
    merged = merge(rules, llm, [])
    assert merged.campos["prioridad"].value == "P1"
    assert merged.campos["prioridad"].alternatives == ["P3"]


def test_subtipo_orientativo_no_sube_por_coincidencia():
    rules = Draft(campos={"suceso.subcategoria": Hallazgo("Convulsión", [], "orientativa: caso X (sim 0.50)", 0.3, source="inferido")})
    llm = {"suceso.subcategoria": Hallazgo("Convulsión", [], "LLM", 0.65, source="inferido")}
    assert merge(rules, llm, []).campos["suceso.subcategoria"].confidence == 0.3
