from app.text import phonetic_key, split_sentences, strip_accents
from app.transcript import Document, parse_raw_transcript


def test_phonetic_key_colapsa_errores_tipicos():
    assert phonetic_key("Escalabrini Ortis") == phonetic_key("Scalabrini Ortiz")
    assert phonetic_key("Billingurst") == phonetic_key("Billinghurst")
    assert phonetic_key("Bera") == phonetic_key("Vera")


def test_strip_accents_conserva_enie():
    assert strip_accents("Castañares Constitución") == "Castañares Constitucion"


def test_parse_turnos_formato_dataset():
    turns = parse_raw_transcript("Operador: 911, ¿dónde es? Llamante: En Corrientes 1540. Operador: ¿Hay heridos? Llamante: No.")
    assert [t.speaker for t in turns] == ["operador", "llamante", "operador", "llamante"]
    assert turns[1].text == "En Corrientes 1540."


def test_texto_sin_etiquetas_es_un_turno_del_llamante():
    turns = parse_raw_transcript("hay humo en el edificio de thames 1900")
    assert len(turns) == 1 and turns[0].speaker == "llamante"


def test_evidencia_se_mapea_al_turno():
    doc = Document.from_turns(parse_raw_transcript("Operador: Hola. Llamante: Fuego en Yerbal 2450."))
    pos = doc.text.index("Yerbal")
    ev = doc.evidence(pos, pos + 6)
    assert ev.turn == 1 and doc.turns[1].text[ev.start : ev.end] == "Yerbal"


def test_split_sentences_offsets():
    text = "Hola. Se prendió fuego! Vengan."
    for s, a, b in split_sentences(text):
        assert text[a:b] == s


def test_split_sentences_no_corta_en_abreviaturas():
    sents = [s for s, _, _ in split_sentences("Chocó un taxi en Av. San Juan y Entre Ríos. El delivery no se mueve.")]
    assert sents == ["Chocó un taxi en Av. San Juan y Entre Ríos.", "El delivery no se mueve."]
