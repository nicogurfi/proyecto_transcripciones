"""Conformación y derivación de la Carta de Llamada."""

from __future__ import annotations

from datetime import datetime

from app import db
from app.knowledge.catalog import DESCRIPCION_PRIORIDAD
from app.schemas import Carta, CartaRequest
from app.text import norm


def _v(req: CartaRequest, key: str) -> str | None:
    val = req.valores_finales.get(key)
    return val.strip() if isinstance(val, str) and val.strip() else None


def componer_direccion(req: CartaRequest) -> str:
    calle, altura = _v(req, "ubicacion.calle"), _v(req, "ubicacion.altura")
    partes: list[str] = []
    if calle:
        partes.append(f"{calle} {altura}" if altura else calle)
    if piso := _v(req, "ubicacion.piso_depto"):
        partes.append(piso)
    if inter := _v(req, "ubicacion.interseccion"):
        partes.append(f"esq. {inter}")
    if entre := _v(req, "ubicacion.entre_calles"):
        partes.append(f"entre {entre}")
    if ref := _v(req, "ubicacion.referencia"):
        partes.append(f"({ref})")
    if barrio := _v(req, "ubicacion.barrio"):
        partes.append(f"– {barrio}")
    return ", ".join(partes) if partes else "SIN DIRECCIÓN"


def derivar(req: CartaRequest) -> Carta:
    now = datetime.now()
    numero = db.next_carta_number(f"CL-{now:%Y%m%d}-")
    adv: list[str] = []
    if not _v(req, "ubicacion.calle"):
        adv.append("Falta la calle")
    if not (_v(req, "ubicacion.altura") or _v(req, "ubicacion.interseccion") or _v(req, "ubicacion.entre_calles")):
        adv.append("Falta altura o esquina")
    if req.geo is not None and req.geo.estado != "validada":
        adv.append("Dirección no validada en el callejero")
    if not _v(req, "suceso.categoria"):
        adv.append("Falta el tipo de hecho")
    if not _v(req, "prioridad"):
        adv.append("Falta la prioridad")
    respondidas = [
        f"{c.pregunta} → {c.evidencia}" if c.evidencia else c.pregunta
        for c in req.checklist if c.estado in {"confirmada", "respondida_sugerida"}
    ]
    pendientes = [c.pregunta for c in req.checklist if c.estado == "pendiente"]
    correcciones = [
        (k, req.valores_sugeridos.get(k), v, req.confianzas.get(k))
        for k, v in req.valores_finales.items()
        if norm(v or "") != norm(req.valores_sugeridos.get(k) or "")
    ]
    prioridad = _v(req, "prioridad")
    direccion = componer_direccion(req)
    resumen = _v(req, "suceso.descripcion") or next((t.text for t in req.turnos if t.speaker == "llamante"), "")
    carta = Carta(
        numero=numero,
        creada=now.isoformat(timespec="seconds"),
        completa=not [a for a in adv if a != "Dirección no validada en el callejero"],
        advertencias=adv,
        origen=req.origen,
        prioridad=prioridad,
        categoria=_v(req, "suceso.categoria"),
        subcategoria=_v(req, "suceso.subcategoria"),
        direccion=direccion,
        direccion_validada=bool(req.geo and req.geo.estado == "validada"),
        lat=req.geo.lat if req.geo else None,
        lon=req.geo.lon if req.geo else None,
        barrio=_v(req, "ubicacion.barrio") or (req.geo.barrio if req.geo else None),
        comisaria_vecinal=req.geo.comisaria_vecinal if req.geo else None,
        resumen=resumen,
        personas="; ".join(x for x in (_v(req, "personas.cantidad"), _v(req, "personas.victimas"), _v(req, "personas.estado")) if x) or None,
        riesgos=_v(req, "riesgos"),
        preguntas_respondidas=respondidas,
        preguntas_pendientes=pendientes,
        instrucciones_transmitidas=req.instrucciones_transmitidas,
        alertas_criticas=req.alertas_criticas,
        recursos_sugeridos=req.recursos_sugeridos,
        notas_operador=req.notas_operador,
        correcciones_operador=len(correcciones),
        duracion_segundos=req.duracion_segundos,
        texto_plano="",
    )
    carta.texto_plano = texto_plano(carta)
    db.save_carta(carta.model_dump(), correcciones, req.proveedor, req.caso_ref)
    return carta


def texto_plano(c: Carta) -> str:
    p = f"{c.prioridad} – {DESCRIPCION_PRIORIDAD.get(c.prioridad or '', '')}" if c.prioridad else "SIN PRIORIDAD"
    lines = [
        f"CARTA DE LLAMADA {c.numero}  [{p}]",
        f"Origen: {c.origen}   Creada: {c.creada}",
        f"Tipo: {c.categoria or '-'} / {c.subcategoria or '-'}",
        f"Dirección: {c.direccion}{'' if c.direccion_validada else '  (NO VALIDADA)'}",
    ]
    if c.comisaria_vecinal:
        lines.append(f"Comisaría vecinal: {c.comisaria_vecinal}")
    lines += [f"Resumen: {c.resumen}"]
    if c.personas:
        lines.append(f"Personas: {c.personas}")
    if c.riesgos:
        lines.append(f"Riesgos: {c.riesgos}")
    if c.alertas_criticas:
        lines.append("ALERTAS: " + " | ".join(c.alertas_criticas))
    if c.instrucciones_transmitidas:
        lines.append("Instrucciones transmitidas: " + " | ".join(c.instrucciones_transmitidas))
    if c.preguntas_pendientes:
        lines.append("Preguntas sin respuesta: " + " | ".join(c.preguntas_pendientes))
    if c.recursos_sugeridos:
        lines.append("Recursos sugeridos (referencia para despacho): " + " | ".join(c.recursos_sugeridos))
    if c.notas_operador:
        lines.append(f"Notas del operador: {c.notas_operador}")
    if c.advertencias:
        lines.append("ADVERTENCIAS: " + "; ".join(c.advertencias))
    return "\n".join(lines)
