"""
Pedido en PDF.

REEMPLAZA a XFRX + rep_compras.frx. El original dependia de dos cosas
externas: que XFRX.PRG estuviera cargado en el entorno del ERP con SET
PROCEDURE, y que el archivo rep_compras.frx existiera en sis_path_. Si
faltaba cualquiera de las dos, el boton no hacia nada util.

Aca el layout es codigo y viaja adentro del ejecutable: no hay FRX que
mantener aparte ni motor de terceros que licenciar.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from ..calculo import MODO_ROTACION, Linea
from ..vfp import dtoc, transform_moneda
from .comun import nombre_archivo

AZUL = colors.HexColor("#1f4e79")
GRIS_SUAVE = colors.HexColor("#f2f4f7")
GRIS_LINEA = colors.HexColor("#c9d0da")
ROJO = colors.HexColor("#b03030")
VERDE = colors.HexColor("#dff0e0")


def exportar_pedido_pdf(
    lineas: list[Linea], proveedor, parametros, modo: int
) -> Path:
    ruta = nombre_archivo(
        "Pedido", proveedor.nombre if proveedor else "SIN_PROVEEDOR", ".pdf"
    )
    es_rotacion = modo == MODO_ROTACION
    nombre_proveedor = proveedor.nombre.strip() if proveedor else "Sin proveedor"

    documento = SimpleDocTemplate(
        str(ruta),
        pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=14 * mm,
        title=f"Pedido - {nombre_proveedor}",
        author="Centro de control de quiebres de stock",
    )

    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "titulo", parent=estilos["Title"], fontSize=15, spaceAfter=2,
        textColor=AZUL, alignment=0,
    )
    subtitulo = ParagraphStyle(
        "subtitulo", parent=estilos["Normal"], fontSize=9,
        textColor=colors.HexColor("#5a6472"),
    )
    celda = ParagraphStyle(
        "celda", parent=estilos["Normal"], fontSize=7.5, leading=9,
    )

    elementos = [
        Paragraph("PEDIDO DE REPOSICION", titulo),
        Paragraph(
            f"<b>{_escapar(nombre_proveedor)}</b> &nbsp;|&nbsp; "
            f"Sucursal {_escapar(parametros.sucursal)} &nbsp;|&nbsp; "
            f"{datetime.date.today().strftime('%d/%m/%Y')} &nbsp;|&nbsp; "
            + ("Modo inteligente (rotacion)" if es_rotacion else "Modo manual (min/max)"),
            subtitulo,
        ),
        Spacer(1, 6 * mm),
    ]

    encabezados = [
        "Cod. Prov.", "Descripcion", "Und.",
        "Vta/mes" if es_rotacion else "Minimo",
        "Dias" if es_rotacion else "Maximo",
        "Stock", "A PEDIR", "Costo", "Subtotal", "Ult. vta.",
    ]

    filas = [encabezados]
    total_unidades = 0.0
    total_monto = 0.0
    filas_criticas = []

    ordenadas = sorted(lineas, key=lambda l: l.descripcion)
    for indice, linea in enumerate(ordenadas, start=1):
        total_unidades += linea.cant_pedir
        total_monto += linea.subtotal
        if linea.stock_total <= 0:
            filas_criticas.append(indice)

        filas.append([
            linea.cod_prov_articulo or linea.codigo,
            Paragraph(_escapar(linea.descripcion), celda),
            linea.unidad,
            f"{linea.vta_mes:,.2f}" if es_rotacion else f"{linea.minimo:,.2f}",
            f"{linea.dias_stock:,.1f}" if es_rotacion else f"{linea.maximo:,.2f}",
            f"{linea.stock_total:,.2f}",
            f"{linea.cant_pedir:,.0f}",
            transform_moneda(linea.costo),
            transform_moneda(linea.subtotal),
            dtoc(linea.ultima_venta),
        ])

    filas.append([
        "", "", "", "", "", "TOTALES",
        f"{total_unidades:,.0f}", "", transform_moneda(total_monto), "",
    ])

    anchos = [24 * mm, None, 12 * mm, 20 * mm, 15 * mm, 20 * mm, 20 * mm,
              26 * mm, 30 * mm, 20 * mm]
    ancho_libre = (
        documento.width - sum(a for a in anchos if a is not None)
    )
    anchos = [a if a is not None else ancho_libre for a in anchos]

    tabla = Table(filas, colWidths=anchos, repeatRows=1)
    estilo_tabla = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -2), 0.3, GRIS_LINEA),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, GRIS_SUAVE]),
        ("BACKGROUND", (6, 1), (6, -2), VERDE),
        ("FONTNAME", (6, 1), (6, -2), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1.1, AZUL),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for fila in filas_criticas:
        estilo_tabla.append(("TEXTCOLOR", (5, fila), (5, fila), ROJO))
        estilo_tabla.append(("FONTNAME", (5, fila), (5, fila), "Helvetica-Bold"))

    tabla.setStyle(TableStyle(estilo_tabla))
    elementos.append(tabla)

    elementos.append(Spacer(1, 5 * mm))
    elementos.append(
        Paragraph(
            "Las cantidades son una sugerencia calculada sobre el stock y las "
            "ventas registradas. El sistema no conoce los pedidos ya hechos y "
            "todavia no recibidos.",
            ParagraphStyle(
                "nota", parent=estilos["Normal"], fontSize=7.5,
                textColor=colors.HexColor("#8a94a3"),
            ),
        )
    )

    documento.build(elementos, onLaterPages=_pie, onFirstPage=_pie)
    return ruta


def _pie(lienzo, documento) -> None:
    lienzo.saveState()
    lienzo.setFont("Helvetica", 7)
    lienzo.setFillColor(colors.HexColor("#98a3b6"))
    lienzo.drawString(
        12 * mm, 8 * mm,
        f"Generado el {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}",
    )
    lienzo.drawRightString(
        documento.pagesize[0] - 12 * mm, 8 * mm, f"Pagina {documento.page}"
    )
    lienzo.restoreState()


def _escapar(texto: str) -> str:
    return (
        str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
