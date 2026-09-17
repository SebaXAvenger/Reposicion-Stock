"""
Informe de analisis en HTML.

Port de Form.GenerarInforme. Explica COMO se armo la recomendacion: con que
parametros se corrio, cuantos articulos quedaron afuera en cada uno de los
cinco filtros y por que, con ejemplos concretos.

Se respeta la regla del original: los numeros salen de la foto congelada de
la corrida (Diagnostico) y de los totales por proveedor, nunca de la lista
que se ve en pantalla, que esta acotada al proveedor seleccionado y haria
que el informe mienta sin avisar.

NO ESCRIBE EN NINGUNA TABLA DEL ERP.
"""

from __future__ import annotations

import datetime
import html
from pathlib import Path

from ..calculo import MODO_ROTACION, Diagnostico, Resultado
from ..vfp import dtoc, transform_moneda
from .comun import nombre_archivo

# Rotulo y explicacion de cada escalon del embudo, en el mismo orden en que
# los aplica el calculo. El orden importa: un articulo sale por el PRIMER
# filtro que contesta que no, asi que los numeros no son independientes.
ESCALONES = [
    ("SINVTA", "desc_sin_venta", "Nunca vendio en la ventana analizada",
     "No figura ninguna venta de este articulo en los meses analizados. Es "
     "catalogo muerto, no faltante.", "#c46a6a"),
    ("SINDEM", "desc_sin_demanda", "Vendio, pero no en el universo elegido",
     "Tiene ventas registradas, pero no en la sucursal (o el conjunto de "
     "sucursales) que se esta analizando.", "#c98d4e"),
    ("ESPORA", "desc_esporadico", "Esporadico: movimiento en un solo mes",
     "Tuvo movimiento en un unico mes. Casi siempre es un pedido especial de "
     "un cliente puntual, no mercaderia de reposicion.", "#b8a13f"),
    ("STOCKOK", "desc_stock_ok", "Todavia le alcanza el stock",
     "Le quedan mas dias de stock que el punto de pedido configurado. Va a "
     "aparecer solo cuando baje.", "#5b8fb0"),
    ("CUBIER", "desc_cubierto", "La cobertura objetivo ya esta cubierta",
     "Entro por debajo del punto de pedido, pero sumando el stock de los dos "
     "depositos ya llega a la cobertura pedida.", "#6f8f6a"),
]

ESCALONES_MANUAL = [
    ("STOCKMIN", "desc_sobre_minimo", "Stock por encima del minimo",
     "Consolidado con la otra sucursal ya no esta en quiebre.", "#5b8fb0"),
    ("SINOBJ", "desc_sin_objetivo", "Sin minimo ni maximo cargados",
     "Sin un objetivo cargado en la ficha no hay nada que sugerir.", "#c98d4e"),
]


def generar_informe(resultado: Resultado, parametros, catalogo=None) -> Path:
    ruta = nombre_archivo("Analisis_reposicion", parametros.sucursal or "SUC", ".html")
    ruta.write_text(_documento(resultado, parametros, catalogo), encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------

def _documento(resultado: Resultado, parametros, catalogo) -> str:
    diag = resultado.diagnostico
    es_rotacion = diag.modo == MODO_ROTACION
    proveedores, items, monto = resultado.total_general()
    unidades = sum(p.unidades for p in resultado.proveedores)
    inactivos = max(diag.total_catalogo - diag.analizados, 0)

    partes = [
        _cabecera(diag),
        _tarjeta_parametros(diag, es_rotacion),
        _tarjeta_cifras(diag, proveedores, monto, unidades),
        _tarjeta_embudo(diag, es_rotacion, inactivos),
        _tarjeta_ejemplos(resultado, es_rotacion),
        _tarjeta_advertencias(diag, resultado),
        _pie(catalogo),
    ]
    return _ESQUELETO.format(cuerpo="\n".join(partes))


def _cabecera(diag: Diagnostico) -> str:
    modo = (
        "Inteligente (rotacion)" if diag.modo == MODO_ROTACION else "Manual (min/max)"
    )
    return f"""
<div class="head">
  <div class="kicker">Centro de control de quiebres de stock</div>
  <h1>Analisis de reposicion &mdash; como se armo esta recomendacion</h1>
  <p class="sub">Sucursal {_e(diag.sucursal)} &middot; generado el
     {_e(diag.fecha.strftime('%d/%m/%Y'))} a las {_e(diag.hora[:5])}
     &middot; modo {_e(modo)}</p>
</div>"""


def _tarjeta_parametros(diag: Diagnostico, es_rotacion: bool) -> str:
    filas = []
    if es_rotacion:
        filas += [
            ("Punto de pedido", f"{_num(diag.punto_pedido)} dias"),
            ("Cobertura objetivo", f"{_num(diag.cobertura)} dias"),
            ("Criterio de demanda",
             "Mediana mensual" if diag.mediana else "Promedio mensual"),
            ("Esporadicos",
             "Excluidos" if diag.excluir_esporadicos else "Incluidos"),
            ("Temporadas", _texto_estacionalidad(diag)),
        ]
    filas += [
        ("Universo de compra",
         "Toda la empresa" if diag.remoto else "Solo esta sucursal"),
        ("Catalogo",
         "Todas las series" if diag.catalogo_completo
         else f"Solo serie {diag.sucursal}"),
        ("Stock negativo",
         "Tratado como cero" if diag.negativo_como_cero
         else "Usado tal cual (negativo)"),
    ]
    if es_rotacion:
        ventana = "no informada"
        if diag.venta_desde and diag.venta_hasta:
            ventana = (
                f"{dtoc(diag.venta_desde)} a {dtoc(diag.venta_hasta)} "
                f"({diag.venta_meses} meses)"
            )
        filas.append(("Ventana de ventas", ventana))
        filas.append((
            "Rotacion calculada",
            (dtoc(diag.rotacion_fecha) or "?")
            + (" (incluye Zip_Path_)" if diag.rotacion_negro else " (solo blanco)"),
        ))

    celdas = "".join(
        f'<div class="par"><dt>{_e(rotulo)}</dt><dd>{_e(valor)}</dd></div>'
        for rotulo, valor in filas
    )
    return f"""
<div class="card">
  <h2><span class="n">1</span>Con que parametros se corrio</h2>
  <p class="lede">Todo lo que sigue depende de estos valores. Cambiar
     cualquiera cambia la lista.</p>
  <dl class="params">{celdas}</dl>
</div>"""


def _tarjeta_cifras(diag, proveedores: int, monto: float, unidades: float) -> str:
    return f"""
<div class="stats">
  <div class="stat"><div class="lab">Articulos sugeridos</div>
    <div class="val">{_num(diag.sugeridos, 0)}</div>
    <div class="foot">de {_num(diag.analizados, 0)} analizados</div></div>
  <div class="stat"><div class="lab">Proveedores</div>
    <div class="val">{_num(proveedores, 0)}</div>
    <div class="foot">con algo para pedir</div></div>
  <div class="stat"><div class="lab">Compra estimada</div>
    <div class="val money">$&nbsp;{transform_moneda(monto)}</div>
    <div class="foot">{_num(unidades, 0)} unidades, a precio de costo</div></div>
</div>"""


def _tarjeta_embudo(diag, es_rotacion: bool, inactivos: int) -> str:
    escalones = ESCALONES if es_rotacion else ESCALONES_MANUAL
    valores = [(rot, getattr(diag, campo), texto, color)
               for _cod, campo, rot, texto, color in escalones]
    mayor = max([v for _r, v, _t, _c in valores] + [diag.sugeridos, 1])

    filas = []
    for rotulo, cantidad, _texto, color in valores:
        ancho = 0 if mayor == 0 else (cantidad / mayor) * 100
        porcentaje = (
            f"{cantidad / diag.analizados * 100:.1f}%" if diag.analizados else "-"
        )
        filas.append(
            f'<div class="frow"><div class="fl">{_e(rotulo)}</div>'
            f'<div class="track"><span class="bar" style="width:{ancho:.1f}%;'
            f'background:{color}"></span></div>'
            f'<div class="fn">{_num(cantidad, 0)}</div>'
            f'<div class="fq">{porcentaje}</div></div>'
        )

    ancho_final = 0 if mayor == 0 else (diag.sugeridos / mayor) * 100
    filas.append(
        f'<div class="frow keep"><div class="fl">Quedan sugeridos</div>'
        f'<div class="track"><span class="bar" style="width:{ancho_final:.1f}%;'
        f'background:#2f7fd8"></span></div>'
        f'<div class="fn">{_num(diag.sugeridos, 0)}</div><div class="fq"></div></div>'
    )

    pregunta = "cinco preguntas" if es_rotacion else "dos preguntas"
    return f"""
<div class="card">
  <h2><span class="n">2</span>De donde salieron esos {_num(diag.sugeridos, 0)}</h2>
  <p class="lede">Cada articulo del catalogo paso por {pregunta}, en este
     orden. La primera que contesta &laquo;no&raquo; lo deja afuera, asi que
     los numeros no son independientes entre si.</p>
  <div class="universo">
    <span>Catalogo completo <b>{_num(diag.total_catalogo, 0)}</b></span>
    <span>&minus; inactivos o fuera de la serie elegida <b>{_num(inactivos, 0)}</b></span>
    <span>= analizados <b>{_num(diag.analizados, 0)}</b></span>
  </div>
  <div class="funnel">{''.join(filas)}</div>
</div>"""


def _tarjeta_ejemplos(resultado: Resultado, es_rotacion: bool) -> str:
    escalones = ESCALONES if es_rotacion else ESCALONES_MANUAL
    bloques = []

    for indice, (codigo, _campo, rotulo, explicacion, _color) in enumerate(escalones):
        ejemplos = [e for e in resultado.ejemplos if e.motivo == codigo]
        primera = " first" if indice == 0 else ""
        if not ejemplos:
            bloques.append(
                f'<div class="crit{primera}"><h3>{_e(rotulo)}</h3>'
                f'<p>{_e(explicacion)}</p>'
                f'<p class="vacio">Ningun articulo salio por este motivo.</p></div>'
            )
            continue
        bloques.append(
            f'<div class="crit{primera}"><h3>{_e(rotulo)}</h3>'
            f'<p>{_e(explicacion)}</p>{_tabla_ejemplos(ejemplos, es_rotacion)}'
            f'<p class="muestra">Muestra de hasta 5 casos.</p></div>'
        )

    negativos = [e for e in resultado.ejemplos if e.motivo == "NEGATI"]
    if negativos:
        bloques.append(
            '<div class="crit"><h3>Sugeridos con stock negativo</h3>'
            '<p>Entraron en la lista, pero su stock figura por debajo de cero. '
            'Un stock negativo es imposible en la realidad: casi siempre es '
            'mercaderia recibida y nunca cargada. Conviene corregir la ficha '
            'antes de pedirle nada al proveedor.</p>'
            + _tabla_ejemplos(negativos, es_rotacion)
            + '<p class="muestra">Muestra de hasta 5 casos.</p></div>'
        )

    return f"""
<div class="card">
  <h2><span class="n">3</span>Ejemplos concretos de cada descarte</h2>
  <p class="lede">Casos reales de esta corrida, con los numeros que
     provocaron la decision.</p>
  {''.join(bloques)}
</div>"""


def _tabla_ejemplos(ejemplos, es_rotacion: bool) -> str:
    if es_rotacion:
        encabezados = [
            ("Codigo", ""), ("Descripcion", ""), ("Vta/mes", "r"),
            ("Dias stk", "r"), ("Stock", "r"), ("Meses c/vta", "r"),
            ("Ult. venta", "r"),
        ]
    else:
        encabezados = [
            ("Codigo", ""), ("Descripcion", ""), ("Stock", "r"),
            ("Minimo", "r"),
        ]

    cabeza = "".join(
        f'<th class="{clase}">{_e(titulo)}</th>' for titulo, clase in encabezados
    )

    filas = []
    for ejemplo in ejemplos[:5]:
        clase_stock = ' class="r neg"' if ejemplo.stock < 0 else ' class="r"'
        if es_rotacion:
            celdas = (
                f"<td>{_e(ejemplo.codigo)}</td>"
                f'<td class="desc">{_e(ejemplo.descripcion)}</td>'
                f'<td class="r">{_num(ejemplo.vta_mes, 2)}</td>'
                f'<td class="r">{_num(ejemplo.dias, 1) if ejemplo.dias else "-"}</td>'
                f"<td{clase_stock}>{_num(ejemplo.stock, 2)}</td>"
                f'<td class="r">{ejemplo.meses_con_venta or "-"}</td>'
                f'<td class="r">{_e(dtoc(ejemplo.ultima_venta) or "-")}</td>'
            )
        else:
            celdas = (
                f"<td>{_e(ejemplo.codigo)}</td>"
                f'<td class="desc">{_e(ejemplo.descripcion)}</td>'
                f"<td{clase_stock}>{_num(ejemplo.stock, 2)}</td>"
                f'<td class="r">{_num(ejemplo.necesidad, 2)}</td>'
            )
        filas.append(f"<tr>{celdas}</tr>")

    return (
        f'<div class="exwrap"><table><thead><tr>{cabeza}</tr></thead>'
        f"<tbody>{''.join(filas)}</tbody></table></div>"
    )


def _tarjeta_advertencias(diag, resultado: Resultado) -> str:
    puntos = [
        "<b>No conoce los pedidos pendientes.</b> El sistema no registra en "
        "ningun lado lo que ya se le pidio al proveedor y todavia no llego. "
        "Si hoy se compra y manana se vuelve a abrir esta pantalla, va a "
        "sugerir lo mismo otra vez hasta que la mercaderia entre al stock.",
        _advertencia_temporadas(diag),
        "<b>No sabe si el proveedor tiene stock</b> ni cuanto tarda en "
        "entregar.",
    ]
    if diag.negativos:
        puntos.insert(
            0,
            f"<b>{_num(diag.negativos, 0)} de los articulos sugeridos tienen "
            "stock negativo.</b> Al ordenarse por monto suelen quedar arriba "
            "de todo y distorsionan el total estimado. Conviene revisarlos "
            "antes de mandar el pedido"
            + ("." if diag.negativo_como_cero else
               ", o activar 'Tratar stock negativo como cero'."),
        )

    lista = "".join(f"<li>{p}</li>" for p in puntos)
    return f"""
<div class="caveat">
  <h2>Lo que este analisis NO puede saber</h2>
  <ul>{lista}</ul>
</div>"""


def _texto_estacionalidad(diag) -> str:
    """Resumen de la estacionalidad para la tarjeta de parametros."""
    if not diag.estacionalidad:
        return "No se consideran"
    if not diag.estacionalidad_disponible:
        return "Pedidas, pero ROTACION.DBF no trae perfil: recalcular rotacion"
    return (
        f"Ajuste propio en {_num(diag.estac_articulo, 0)}, "
        f"por rubro en {_num(diag.estac_rubro, 0)}, "
        f"sin datos en {_num(diag.estac_neutro, 0)}"
    )


def _advertencia_temporadas(diag) -> str:
    """El limite de lo que sabe el calculo sobre temporadas."""
    if diag.estacionalidad and diag.estacionalidad_disponible:
        return (
            "<b>Las temporadas salen del historial.</b> Si un anio hubo un "
            "quiebre largo o una venta extraordinaria, ese mes queda marcado "
            "como temporada baja o alta. El ajuste esta acotado, pero conviene "
            "mirar el detalle de los articulos con cantidades llamativas."
        )
    return (
        "<b>No esta considerando temporadas.</b> Usa el promedio de la ventana "
        "analizada parejo. Antes de una temporada fuerte conviene activar "
        "'Considerar temporadas' o subir la cobertura a mano."
    )


def _pie(catalogo) -> str:
    lineas = [
        f"<p>Generado el {datetime.datetime.now().strftime('%d/%m/%Y a las %H:%M')}.</p>",
        "<p>Todos los numeros salen de las tablas del propio sistema. "
        "Este informe no modifica ningun dato.</p>",
    ]
    if catalogo is not None and getattr(catalogo, "diagnostico", None):
        detalles = "".join(f"<li>{_e(d)}</li>" for d in catalogo.diagnostico)
        lineas.append(f"<details><summary>Tablas leidas</summary><ul>{detalles}</ul></details>")
    return f"<footer>{''.join(lineas)}</footer>"


# ---------------------------------------------------------------------------

def _e(valor) -> str:
    return html.escape(str(valor if valor is not None else ""))


def _num(valor, decimales: int = -1) -> str:
    """Numero con separador de miles argentino.

    decimales = -1 significa automatico: sin decimales si el valor es entero.
    Es el mismo criterio que usaba HtmlNum en el original, para que un punto
    de pedido de 7 no se muestre como "7,00".
    """
    numero = float(valor or 0)
    if decimales < 0:
        decimales = 0 if abs(numero - round(numero)) < 1e-9 else 2
    return transform_moneda(numero, decimales)


_ESQUELETO = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Analisis de reposicion</title>
<style>
:root{{
  --paper:#faf9f7; --surface:#ffffff; --plane:#f0efec; --rule:#e3e1dc;
  --ring:#d9d6cf; --ink:#1e2024; --ink-2:#4a4f57; --ink-muted:#8a8f98;
  --accent:#2f6fb8; --keep:#2f7fd8; --critical:#b03030; --warning:#c08a1e;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);
  font-family:"Segoe UI",-apple-system,BlinkMacSystemFont,"Inter",sans-serif;
  line-height:1.5;font-size:15px}}
.wrap{{max-width:960px;margin:0 auto;padding:40px 28px 60px}}
.head{{margin-bottom:26px}}
.kicker{{font-size:11.5px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink-muted);font-weight:600;margin-bottom:8px}}
h1{{font-size:27px;line-height:1.25;margin:0 0 8px;font-weight:640;letter-spacing:-.01em}}
.sub{{color:var(--ink-muted);font-size:14px;margin:0}}
.card{{background:var(--surface);border:1px solid var(--rule);border-radius:12px;
  padding:24px 26px;margin-bottom:20px}}
h2{{font-size:17px;margin:0 0 6px;font-weight:640;display:flex;align-items:center;gap:10px}}
h2 .n{{display:inline-flex;align-items:center;justify-content:center;
  width:23px;height:23px;border-radius:50%;background:var(--accent);color:#fff;
  font-size:12.5px;font-weight:700;flex:none}}
.lede{{color:var(--ink-2);font-size:14.5px;margin:0 0 16px}}
.params{{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));
  gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:8px;
  overflow:hidden;margin:0}}
.par{{background:var(--surface);padding:11px 14px}}
.par dt{{font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;
  color:var(--ink-muted);font-weight:600;margin-bottom:3px}}
.par dd{{margin:0;font-size:14.5px;font-weight:600}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:20px}}
.stat{{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:18px 20px}}
.lab{{font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;
  color:var(--ink-muted);font-weight:600;margin-bottom:6px}}
.val{{font-size:30px;font-weight:650;letter-spacing:-.02em;line-height:1.1;
  font-variant-numeric:tabular-nums}}
.val.money{{font-size:24px}}
.foot{{font-size:12.5px;color:var(--ink-muted);margin-top:4px}}
.universo{{display:flex;flex-wrap:wrap;gap:14px;background:var(--plane);
  border-radius:8px;padding:11px 14px;font-size:13.5px;color:var(--ink-2);margin-bottom:16px}}
.universo b{{color:var(--ink);font-variant-numeric:tabular-nums}}
.funnel{{display:grid;grid-template-columns:1fr minmax(90px,2fr) auto auto;
  gap:2px 14px;align-items:center}}
.frow{{display:contents}}
.frow > *{{padding:7px 0}}
.fl{{font-size:14px;color:var(--ink-2);line-height:1.35}}
.track{{background:var(--plane);border-radius:3px;height:15px}}
.bar{{height:15px;border-radius:0 4px 4px 0;min-width:3px;display:block}}
.fn{{text-align:right;font-weight:620;font-size:14.5px;white-space:nowrap;
  font-variant-numeric:tabular-nums}}
.fq{{text-align:right;font-size:13px;color:var(--ink-muted);white-space:nowrap;padding-left:6px}}
.frow.keep > *{{border-top:1px solid var(--ink);margin-top:6px;padding-top:12px}}
.frow.keep .fl{{color:var(--ink);font-weight:620;font-size:15px}}
.frow.keep .fn{{font-size:19px;color:var(--keep)}}
.exwrap{{overflow-x:auto;margin:14px 0 4px;border:1px solid var(--rule);border-radius:8px}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;
  font-variant-numeric:tabular-nums;background:var(--surface)}}
th{{text-align:left;font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;
  color:var(--ink-muted);font-weight:600;padding:9px 12px;
  border-bottom:1px solid var(--rule);white-space:nowrap;background:#fcfcfb}}
td{{padding:8px 12px;border-bottom:1px solid var(--rule)}}
tr:last-child td{{border-bottom:none}}
th.r,td.r{{text-align:right}}
.desc{{color:var(--ink-2)}}
.neg{{color:var(--critical);font-weight:620}}
.muestra{{font-size:12.5px;color:var(--ink-muted);margin:8px 0 0}}
.crit{{border-top:1px solid var(--rule);padding-top:14px;margin-top:16px}}
.crit.first{{border-top:none;padding-top:0;margin-top:0}}
.crit h3{{font-size:15px;margin:0 0 5px;font-weight:620}}
.crit p{{font-size:14px;color:var(--ink-2);margin:0 0 6px}}
.caveat{{background:#fffdf5;border:1px solid var(--ring);
  border-left:3px solid var(--warning);border-radius:12px;padding:20px 24px;margin-bottom:22px}}
.caveat h2{{margin-bottom:10px}}
.caveat ul{{margin:0;padding-left:20px}}
.caveat li{{margin-bottom:7px;font-size:14.5px;color:var(--ink-2)}}
.caveat li b{{color:var(--ink);font-weight:620}}
.caveat li:last-child{{margin-bottom:0}}
.vacio{{color:var(--ink-muted);font-size:14px;font-style:italic;margin:6px 0 0}}
footer{{color:var(--ink-muted);font-size:12.5px;border-top:1px solid var(--rule);
  padding-top:14px;margin-top:28px}}
footer p{{margin:0 0 3px}}
footer ul{{margin:6px 0 0;padding-left:18px}}
summary{{cursor:pointer;margin-top:8px}}
@media (max-width:720px){{
  .stats{{grid-template-columns:1fr}}
  .funnel{{grid-template-columns:1fr auto;gap:2px 10px}}
  .track{{display:none}}
}}
@media print{{
  body{{background:#fff}}
  .wrap{{max-width:none;padding:0}}
  .card,.caveat,.stat,.exwrap{{break-inside:avoid;border:1px solid #ccc}}
}}
</style></head>
<body><div class="wrap">
{cuerpo}
</div></body></html>
"""
