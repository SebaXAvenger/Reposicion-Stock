"""
Semantica de Visual FoxPro reproducida en Python.

Este modulo existe porque el formulario original corria dentro de un entorno
VFP con SET EXACT OFF, SET DELETED ON y SET DATE DMY activos, y usaba
funciones (ROUND, CEILING, NVL, PADR) cuyo comportamiento NO coincide con el
equivalente directo de Python. Portar esas expresiones "tal cual" cambia
resultados de forma silenciosa.

Cada funcion documenta la diferencia concreta que corrige.
"""

from __future__ import annotations

import datetime
import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any


# ---------------------------------------------------------------------------
# Numeros
# ---------------------------------------------------------------------------

def vfp_round(valor: Any, decimales: int = 0) -> float:
    """ROUND() de VFP: redondeo half-away-from-zero.

    DIFERENCIA CRITICA con Python: round() usa redondeo bancario (half-even).

        VFP:     ROUND(0.5, 0)  ->  1        ROUND(2.5, 0)  ->  3
        Python:  round(0.5)     ->  0        round(2.5)     ->  2

    En este programa aparece en el reparto del pedido entre depositos
    (PedirLoc / PedirRem). Con round() nativo, la mitad de los repartios
    "justos" caeria para el lado equivocado y la suma de las dos columnas
    dejaria de dar exactamente la cantidad pedida.
    """
    numero = to_num(valor)
    if numero is None:
        return 0.0
    try:
        cuantizado = Decimal(repr(numero)).quantize(
            Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, ValueError):
        return 0.0
    return float(cuantizado)


def vfp_ceiling(valor: Any) -> float:
    """CEILING() de VFP. Coincide con math.ceil salvo por el manejo de nulos."""
    numero = to_num(valor)
    if numero is None:
        return 0.0
    return float(math.ceil(numero))


def to_num(valor: Any, defecto: float | None = None) -> float | None:
    """Conversion tolerante a numero. Un campo N vacio en DBF llega como None."""
    if valor is None:
        return defecto
    if isinstance(valor, bool):
        return 1.0 if valor else 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, str):
        limpio = valor.strip().replace(",", ".")
        if not limpio:
            return defecto
        try:
            return float(limpio)
        except ValueError:
            return defecto
    return defecto


def nvl(valor: Any, defecto: Any) -> Any:
    """NVL() de VFP: reemplaza .NULL. por el valor por defecto.

    En VFP un campo numerico vacio puede venir como .NULL. y cualquier cuenta
    que lo toque devuelve .NULL. sin avisar. El codigo original envuelve casi
    todas las lecturas en NVL(); se conserva la misma disciplina aca.
    """
    return defecto if valor is None else valor


def num(valor: Any) -> float:
    """NVL(valor, 0) numerico. Atajo usado en todo el modulo de calculo."""
    resultado = to_num(valor, 0.0)
    return 0.0 if resultado is None else resultado


# ---------------------------------------------------------------------------
# Cadenas
# ---------------------------------------------------------------------------

def alltrim(valor: Any) -> str:
    """ALLTRIM(): saca espacios de ambas puntas. Los campos C de DBF vienen
    rellenados con espacios a la derecha."""
    if valor is None:
        return ""
    if isinstance(valor, bytes):
        valor = valor.decode("latin-1", "replace")
    return str(valor).strip()


def padr(valor: Any, largo: int, relleno: str = " ") -> str:
    """PADR(): justifica a la izquierda rellenando a la derecha."""
    texto = "" if valor is None else str(valor)
    return texto[:largo].ljust(largo, relleno)


def padl(valor: Any, largo: int, relleno: str = " ") -> str:
    """PADL(): justifica a la derecha rellenando a la izquierda."""
    texto = "" if valor is None else str(valor)
    return texto[-largo:] if len(texto) > largo else texto.rjust(largo, relleno)


def igual_exact_off(izquierda: Any, derecha: Any) -> bool:
    """Operador `=` de VFP bajo SET EXACT OFF.

    ESTA ES LA TRAMPA MAS PELIGROSA DEL PORT.

    Con SET EXACT OFF (que es lo que fija el Load del formulario original),
    la comparacion se corta cuando termina el operando DERECHO. O sea que
    `AR_SUCU = lcSucu` no significa "es igual a", significa "empieza con".

        SET EXACT OFF
        ? "10" = "1"      && .T.   <- la sucursal 10 pasa el filtro de la 1
        ? "1"  = "10"     && .F.
        ? "loquesea" = "" && .T.   <- el operando vacio matchea TODO

    Si el negocio tiene sucursales "1" y "10", portar esto como `==`
    cambia que articulos entran en la lista. Se reproduce el comportamiento
    original y se deja `igual_exacto()` para cuando se decida endurecerlo.
    """
    a = "" if izquierda is None else str(izquierda)
    b = "" if derecha is None else str(derecha)
    if b == "":
        return True
    return a.startswith(b)


def igual_exacto(izquierda: Any, derecha: Any) -> bool:
    """Comparacion == de VFP (operador ==, independiente de SET EXACT).
    Compara ignorando el relleno de espacios a la derecha."""
    a = "" if izquierda is None else str(izquierda).rstrip()
    b = "" if derecha is None else str(derecha).rstrip()
    return a == b


# ---------------------------------------------------------------------------
# Fechas y formato
# ---------------------------------------------------------------------------

def dtoc(fecha: Any) -> str:
    """DTOC() con SET DATE DMY: dd/mm/aaaa. Fecha vacia -> cadena vacia."""
    if not fecha:
        return ""
    if isinstance(fecha, datetime.datetime):
        fecha = fecha.date()
    if not isinstance(fecha, datetime.date):
        return str(fecha)
    return fecha.strftime("%d/%m/%Y")


def transform_moneda(valor: Any, decimales: int = 2) -> str:
    """Equivalente a TRANSFORM(x, "999,999,999.99") pero con separadores
    argentinos: punto para miles, coma para decimales."""
    numero = num(valor)
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def transform_num(valor: Any, decimales: int = 0) -> str:
    """Numero con separador de miles, sin simbolo de moneda."""
    return transform_moneda(valor, decimales)
