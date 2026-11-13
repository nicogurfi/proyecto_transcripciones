from app.extraction.rules import run_rules
from app.knowledge.dataset import load_dataset
from app.transcript import Document, parse_raw_transcript


def draft_for(text):
    return run_rules(Document.from_turns(parse_raw_transcript(text)))


def test_direccion_completa_con_piso():
    d = draft_for("Llamante: es mi hija de 8 años, estamos en Av. Directorio 2140 3ro C. No le entra el aire!")
    c = d.campos
    assert c["ubicacion.calle"].value == "Av. Directorio"
    assert c["ubicacion.altura"].value == "2140"
    assert c["ubicacion.piso_depto"].value == "3° C"
    assert c["prioridad"].value == "P1"
    assert "hija (8 años)" in c["personas.victimas"].value


def test_autocorreccion_de_altura():
    d = draft_for("Llamante: Avenida Rivadavia 4250, perdón, 4520, segundo B.")
    alt = d.campos["ubicacion.altura"]
    assert alt.value == "4520" and alt.alternatives == ["4250"]
    assert d.campos["ubicacion.piso_depto"].value == "2° B"


def test_toda_extraccion_tiene_evidencia_literal():
    for caso in load_dataset()[:10]:
        doc = Document.from_turns(parse_raw_transcript(caso.transcripcion))
        d = run_rules(doc, exclude=caso.id)
        for key, h in d.campos.items():
            if h.source == "dicho":
                assert h.spans, key
                for s, e in h.spans:
                    assert doc.text[s:e].strip(), key


def test_calle_correcta_en_la_mayoria_del_dataset():
    ok = 0
    casos = load_dataset()
    for caso in casos:
        d = run_rules(Document.from_turns(parse_raw_transcript(caso.transcripcion)), exclude=caso.id)
        calle = d.campos.get("ubicacion.calle")
        gt = caso.calle.lower().replace("av. ", "")
        if calle and (gt.split()[0] in calle.value.lower() or calle.value.lower().split()[-1] in gt):
            ok += 1
    assert ok / len(casos) >= 0.9
