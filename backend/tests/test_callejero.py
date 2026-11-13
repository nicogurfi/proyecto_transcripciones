from app.geo.callejero import get_callejero


def mentions(text):
    return [(m.alias, m.match) for m in get_callejero().find_mentions(text)]


def test_detecta_calle_y_cruces():
    assert mentions("Scalabrini Ortiz al 800, entre Vera y Velasco") == [
        ("SCALABRINI ORTIZ", "exacto"), ("VERA", "exacto"), ("VELASCO", "exacto")]


def test_error_de_transcripcion_fonetico():
    assert mentions("en escalabrini ortis al 1300")[0] == ("SCALABRINI ORTIZ", "fonetico")


def test_no_confunde_lugares_ni_barrios_con_calles():
    assert mentions("trabando la circulación hacia Belgrano R.") == []
    assert mentions("corriendo por el Parque Indoamericano en Soldati") == []


def test_avenida_de_mayo():
    assert mentions("sobre Avenida de Mayo al 900")[0][0] == "AVENIDA DE MAYO"


def test_validaciones_de_altura_y_cruce():
    cal = get_callejero()
    thames = cal.lookup("Thames")[1]
    assert cal.altura_en_rango(thames, 1900) is True
    assert cal.altura_en_rango(thames, 4800) is False
    assert cal.se_cruzan(thames, cal.lookup("Nicaragua")[1]) is True
    assert cal.se_cruzan(thames, cal.lookup("Cabildo")[1]) is False
