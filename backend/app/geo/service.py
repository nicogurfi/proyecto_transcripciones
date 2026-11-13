"""Validación de la dirección: callejero offline + USIG online (doble chequeo)."""

from __future__ import annotations

from app.extraction.draft import Draft
from app.geo.callejero import Tramo, display_name, get_callejero
from app.geo.usig import get_usig
from app.schemas import GeoValidacion


def _strip_av(name: str) -> str:
    return name.replace("Av. ", "")


async def validar(draft: Draft, online: bool = True) -> GeoValidacion:
    cal = get_callejero()
    d = draft.direccion
    geo = GeoValidacion()
    calle_campo = draft.campos.get("ubicacion.calle")
    if calle_campo is None:
        return geo

    tramos: list[Tramo] = d.calle_tramos
    if not tramos:  # calle propuesta por el LLM: se busca en el callejero
        found = cal.lookup(calle_campo.value)
        if found:
            tramos = found[1]
    if not tramos:
        geo.estado = "no_validada"
        geo.calle_existe = False
        geo.verificaciones.append(f"'{calle_campo.value}' no existe en el callejero de CABA")
        return geo

    geo.calle_existe = True
    altura = d.altura
    if altura is None and (alt := draft.campos.get("ubicacion.altura")) and alt.value.isdigit():
        altura = int(alt.value)
    tramo = cal.pick_tramo(tramos, altura, any(t.es_avenida for t in tramos[:1]))
    geo.calle_oficial = display_name(tramo)
    geo.rangos_altura = cal.rangos([t for t in tramos if t.nombre == tramo.nombre] or tramos)
    geo.verificaciones.append(f"Calle '{geo.calle_oficial}' existe en el callejero oficial")

    if altura is not None:
        en_rango = cal.altura_en_rango([t for t in tramos if t.nombre == tramo.nombre] or tramos, altura)
        geo.altura_en_rango = en_rango
        if en_rango is True:
            geo.verificaciones.append(f"Altura {altura} dentro del rango de la calle")
        elif en_rango is False:
            rangos = ", ".join(f"{a}-{b}" for a, b in geo.rangos_altura)
            geo.verificaciones.append(f"Altura {altura} FUERA de rango ({rangos})")

    cruces = d.cruces or d.entre
    cruce_nombres: list[str] = []
    if cruces:
        validos = [cal.se_cruzan(tramos, m.tramos) for m in cruces]
        geo.cruce_valido = all(validos)
        for m, ok in zip(cruces, validos, strict=True):
            nombre = display_name(cal.pick_tramo(m.tramos, None, m.av_cue))
            cruce_nombres.append(nombre)
            geo.verificaciones.append(
                f"{nombre} {'cruza' if ok else 'NO cruza'} {geo.calle_oficial}"
            )
    elif (inter := draft.campos.get("ubicacion.interseccion")) is not None:
        found = cal.lookup(inter.value.split(" y ")[0])
        if found:
            ok = cal.se_cruzan(tramos, found[1])
            geo.cruce_valido = ok
            cruce_nombres.append(display_name(found[1][0]))
            geo.verificaciones.append(f"{cruce_nombres[0]} {'cruza' if ok else 'NO cruza'} {geo.calle_oficial}")

    # --- doble chequeo online (USIG) + coordenadas
    usig = get_usig()
    res = None
    if altura is not None and geo.altura_en_rango is not False:
        res = await usig.geocode(f"{_strip_av(geo.calle_oficial)} {altura}", con_altura=True, allow_network=online)
    if res is None and cruce_nombres and geo.cruce_valido:
        res = await usig.geocode(f"{_strip_av(geo.calle_oficial)} y {_strip_av(cruce_nombres[0])}", con_altura=False, allow_network=online)
    if res is not None:
        geo.lat, geo.lon = res.lat, res.lon
        geo.direccion_normalizada = res.direccion
        geo.barrio, geo.comuna, geo.comisaria_vecinal = res.barrio, res.comuna, res.comisaria_vecinal
        geo.fuente_coordenadas = "usig" if res.fuente == "usig" else "cache"
        geo.verificaciones.append(
            f"USIG confirma: {res.direccion}" + (" (caché local)" if res.fuente == "cache" else "")
        )

    ok_altura = geo.altura_en_rango is not False
    ok_cruce = geo.cruce_valido is not False
    tiene_precision = altura is not None or bool(cruce_nombres)
    if ok_altura and ok_cruce and tiene_precision:
        geo.estado = "validada"
    elif not ok_altura or not ok_cruce:
        geo.estado = "no_validada"
    else:
        geo.estado = "parcial"
    return geo
