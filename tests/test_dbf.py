"""Pruebas del lector de DBF."""

from __future__ import annotations

import datetime
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dbf import TablaDBF, leer_tabla  # noqa: E402
from tools.dbf_writer import (  # noqa: E402
    BYTE_IDIOMA_CP850, BYTE_IDIOMA_CP1252, escribir_dbf,
)

CAMPOS = [
    ("COD", "C", 6, 0),
    ("DESC", "C", 30, 0),
    ("CANT", "N", 12, 3),
    ("ENTERO", "N", 6, 0),
    ("FECHA", "D", 8, 0),
    ("ACTIVO", "L", 1, 0),
]

FILAS = [
    {"COD": "A1", "DESC": "MAÑANA CAÑERÍA ÑANDÚ", "CANT": 12.5,
     "ENTERO": 7, "FECHA": datetime.date(2026, 8, 21), "ACTIVO": True},
    {"COD": "A2", "DESC": "TORNILLO 3/8", "CANT": -4.25,
     "ENTERO": 0, "FECHA": None, "ACTIVO": False},
    {"COD": "A3", "DESC": "BORRADO", "CANT": 99.0,
     "ENTERO": 1, "FECHA": datetime.date(2020, 1, 1), "ACTIVO": True},
]


def _tabla(codepage="cp1252", byte_idioma=BYTE_IDIOMA_CP1252) -> Path:
    ruta = Path(tempfile.mkdtemp()) / "PRUEBA.DBF"
    escribir_dbf(ruta, CAMPOS, FILAS, byte_idioma=byte_idioma, codepage=codepage)
    return ruta


def test_lectura_basica():
    filas = leer_tabla(_tabla())
    assert len(filas) == 3
    assert filas[0]["COD"] == "A1"
    assert filas[0]["CANT"] == 12.5
    assert filas[0]["ENTERO"] == 7
    assert filas[0]["FECHA"] == datetime.date(2026, 8, 21)
    assert filas[0]["ACTIVO"] is True
    assert filas[1]["CANT"] == -4.25
    assert filas[1]["FECHA"] is None
    assert filas[1]["ACTIVO"] is False


def test_acentos_cp1252_y_cp850():
    """El mismo texto guardado en dos codepages distintos tiene que volver
    igual, siempre que se lo lea con el que corresponde."""
    for codepage, byte_idioma in (
        ("cp1252", BYTE_IDIOMA_CP1252),
        ("cp850", BYTE_IDIOMA_CP850),
    ):
        filas = leer_tabla(_tabla(codepage, byte_idioma))
        assert filas[0]["DESC"] == "MAÑANA CAÑERÍA ÑANDÚ", codepage


def test_codepage_se_detecta_del_encabezado():
    with TablaDBF(_tabla("cp850", BYTE_IDIOMA_CP850)) as tabla:
        assert tabla.codepage == "cp850"
        assert "byte de idioma" in tabla.codepage_origen

    # Y se puede forzar desde la configuracion
    with TablaDBF(_tabla(), codepage="cp850") as tabla:
        assert tabla.codepage == "cp850"
        assert "forzado" in tabla.codepage_origen


def test_registros_borrados_se_saltan():
    """SET DELETED ON: los registros marcados con '*' no existen."""
    ruta = _tabla()
    with TablaDBF(ruta) as tabla:
        inicio = tabla.largo_encabezado + 2 * tabla.largo_registro

    contenido = bytearray(ruta.read_bytes())
    contenido[inicio] = 0x2A            # marca de borrado sobre la tercera fila
    ruta.write_bytes(bytes(contenido))

    filas = leer_tabla(ruta)
    assert len(filas) == 2
    assert [f["COD"] for f in filas] == ["A1", "A2"]

    # Con incluir_borrados si aparece, marcada
    with TablaDBF(ruta, incluir_borrados=True) as tabla:
        todas = list(tabla.filas())
    assert len(todas) == 3
    assert todas[2]["_BORRADO"] is True


def test_lectura_selectiva_de_campos():
    """Pedir solo algunos campos evita decodificar el resto."""
    filas = leer_tabla(_tabla(), campos=["COD", "CANT"])
    assert set(filas[0].keys()) == {"COD", "CANT"}


def test_campo_inexistente_avisa_claro():
    try:
        leer_tabla(_tabla(), campos=["NO_EXISTE"])
    except Exception as error:
        assert "no tiene el campo" in str(error)
    else:
        raise AssertionError("tendria que haber fallado")


def test_estructura():
    with TablaDBF(_tabla()) as tabla:
        assert tabla.nombres == ["COD", "DESC", "CANT", "ENTERO", "FECHA", "ACTIVO"]
        assert tabla.cantidad_registros == 3
        assert tabla.tiene("cant")            # sin distinguir mayusculas
        assert not tabla.tiene("otro")


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
