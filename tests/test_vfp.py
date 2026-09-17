"""
Pruebas de la capa de compatibilidad con VFP.

No prueban "que Python funcione": prueban las DIFERENCIAS entre VFP y Python
que, si se portan mal, mueven numeros en silencio.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.vfp import (  # noqa: E402
    alltrim, dtoc, igual_exact_off, igual_exacto, num, nvl, padl, padr,
    transform_moneda, vfp_ceiling, vfp_round,
)


def test_redondeo_no_es_bancario():
    """ROUND(0.5, 0) da 1 en VFP y 0 con round() de Python."""
    assert vfp_round(0.5, 0) == 1
    assert vfp_round(1.5, 0) == 2
    assert vfp_round(2.5, 0) == 3      # round(2.5) de Python da 2
    assert vfp_round(-0.5, 0) == -1    # se aleja del cero
    assert vfp_round(2.345, 2) == 2.35
    assert vfp_round(None, 0) == 0


def test_reparto_entre_depositos_suma_exacto():
    """PedirLoc + PedirRem tiene que dar SIEMPRE la cantidad pedida.

    Es la razon por la que el redondeo importa: si se redondea para el lado
    equivocado, las dos columnas dejan de cerrar contra el total.
    """
    for total in range(0, 200):
        for proporcion in (0.0, 0.25, 0.5, 0.75, 1.0, 1 / 3):
            local = vfp_round(total * proporcion, 0)
            remoto = total - local
            assert local + remoto == total


def test_ceiling():
    assert vfp_ceiling(0.1) == 1
    assert vfp_ceiling(5.0) == 5
    assert vfp_ceiling(-0.5) == 0
    assert vfp_ceiling(None) == 0


def test_exact_off_es_empieza_con():
    """Con SET EXACT OFF el `=` compara hasta donde termina el operando
    derecho. La sucursal 10 pasa el filtro de la sucursal 1."""
    assert igual_exact_off("10", "1") is True
    assert igual_exact_off("1", "10") is False
    assert igual_exact_off("cualquier cosa", "") is True   # el vacio matchea todo
    assert igual_exact_off("1", "1") is True

    # El operador == de VFP, en cambio, si compara de verdad
    assert igual_exacto("10", "1") is False
    assert igual_exacto("1 ", "1") is True                  # ignora el relleno


def test_nulos():
    assert nvl(None, 0) == 0
    assert nvl(5, 0) == 5
    assert num(None) == 0.0
    assert num("") == 0.0
    assert num("12,5") == 12.5


def test_cadenas():
    assert alltrim("  hola  ") == "hola"
    assert alltrim(None) == ""
    assert padr("232", 7) == "232    "
    assert padl("232", 6) == "   232"
    # La regla de NormalizarProv: "232" -> "1" + PADL(codigo, 6)
    assert "1" + padl("232", 6) == "1   232"


def test_formato_argentino():
    assert transform_moneda(1234567.891) == "1.234.567,89"
    assert transform_moneda(0) == "0,00"
    assert transform_moneda(1000, 0) == "1.000"
    assert dtoc(datetime.date(2026, 8, 21)) == "21/08/2026"
    assert dtoc(None) == ""


if __name__ == "__main__":
    fallos = 0
    for nombre, funcion in sorted(globals().items()):
        if nombre.startswith("test_") and callable(funcion):
            try:
                funcion()
                print(f"  OK    {nombre}")
            except AssertionError as error:
                fallos += 1
                print(f"  FALLO {nombre}: {error}")
    print("Sin fallos." if not fallos else f"{fallos} fallo(s).")
    raise SystemExit(1 if fallos else 0)
