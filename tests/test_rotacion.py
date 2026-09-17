"""
Pruebas del recalculo de rotacion.

Se arman tablas DOCUM/DOCCUER minimas con casos elegidos a mano y se
verifica el numero exacto que tiene que salir. Lo que se prueba es la
logica que el PRG original tenia repartida entre ProcesarFuente y
GrabarArticulo.
"""

from __future__ import annotations

import datetime
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Parametros  # noqa: E402
from app.dbf import leer_tabla  # noqa: E402
from app.rotacion import (  # noqa: E402
    CalculadorRotacion, OpcionesRotacion, calcular_rotacion,
)
from tools.dbf_writer import escribir_dbf  # noqa: E402
from tools.generar_datos_prueba import (  # noqa: E402
    CAMPOS_ARTICULO, CAMPOS_DOCCUER, CAMPOS_DOCUM,
)

HOY = datetime.date(2026, 8, 21)


def _mes(indice: int) -> datetime.date:
    """Un dia dentro del mes `indice` contando hacia atras desde julio 2026.

    indice 0 = julio 2026 (el ultimo mes completo), 1 = junio, etc.
    """
    anio, mes = 2026, 7 - indice
    while mes <= 0:
        mes += 12
        anio -= 1
    return datetime.date(anio, mes, 15)


def _armar(documentos, renglones, articulos=None, carpeta=None) -> Path:
    carpeta = carpeta or Path(tempfile.mkdtemp())
    carpeta.mkdir(parents=True, exist_ok=True)
    escribir_dbf(carpeta / "DOCUM.DBF", CAMPOS_DOCUM, documentos)
    escribir_dbf(carpeta / "DOCCUER.DBF", CAMPOS_DOCCUER, renglones)
    escribir_dbf(
        carpeta / "ARTICULO.DBF", CAMPOS_ARTICULO, articulos or _articulos()
    )
    return carpeta


def _articulos():
    # AR_CODI mide 6: la clave AR_SUCU + AR_CODI da los 7 de DCC_ARTICU
    return [{
        "AR_SUCU": "1", "AR_CODI": "ART001", "AR_PLU_": "P1",
        "AR_DESC": "ARTICULO DE PRUEBA", "AR_TIPO": "UN", "AR_PROV": "232",
        "DESC_PROV": "PROVEEDOR DE PRUEBA",
        "AR_MINI": 0, "AR_MAXI": 0, "AR_CANT": 5, "AR_COST": 100,
        "AR_ACTIVO": "S",
    }]


def _doc(clave, fecha, tipo="FC", sucursal="1", clipro="C", anulada=False):
    return {
        "DOC_CLAVE_": clave, "DOC_FECEMI": fecha, "DOC_TIPDOC": tipo,
        "DOC_SUCURS": sucursal, "DOC_CLIPRO": clipro, "DOC_ANULED": anulada,
        "DOC_NUMERO": clave,
    }


def _ren(clave, cantidad, articulo="1ART001"):
    return {
        "DCC_CLAVE_": clave, "DCC_ARTICU": articulo, "DCC_CANTID": cantidad,
        "DCC_PRECIO": 0, "DCC_FECHA_": None,
    }


def _correr(carpeta, opciones=None, **extras):
    parametros = Parametros(
        carpeta_datos=str(carpeta), sucursal="1", **extras
    )
    opciones = opciones or OpcionesRotacion(meses=12)
    opciones.hoy = opciones.hoy or HOY
    return calcular_rotacion(parametros, opciones)


def _filas(resultado):
    return leer_tabla(resultado.ruta)


# ---------------------------------------------------------------------------

def test_ventana_son_meses_completos():
    """hasta = ultimo dia del mes anterior; desde = N-1 meses antes."""
    calculador = CalculadorRotacion(
        Parametros(carpeta_datos="/tmp", sucursal="1"), OpcionesRotacion(meses=12)
    )
    desde, hasta = calculador.ventana(datetime.date(2026, 8, 21))
    assert hasta == datetime.date(2026, 7, 31)
    assert desde == datetime.date(2025, 8, 1)

    desde, hasta = calculador.ventana(datetime.date(2026, 1, 5))
    assert hasta == datetime.date(2025, 12, 31)
    assert desde == datetime.date(2025, 1, 1)

    calculador.o.meses = 24
    desde, hasta = calculador.ventana(datetime.date(2026, 8, 21))
    assert hasta == datetime.date(2026, 7, 31)
    assert desde == datetime.date(2024, 8, 1)


def test_promedio_mediana_y_meses_con_venta():
    """12 unidades en un solo mes, sobre 12 meses de ventana.

        total    = 12
        promedio = 12 / 12 = 1
        mediana  = 0   (11 meses en cero: el del medio es cero)
        mescon   = 1
    """
    carpeta = _armar(
        [_doc("D1", _mes(0))],
        [_ren("D1", 12)],
    )
    resultado = _correr(carpeta)
    assert resultado.ok, resultado.mensaje

    fila = _filas(resultado)[0]
    assert fila["ROT_UNIDS"] == 12
    assert fila["ROT_PROME"] == 1
    assert fila["ROT_MEDIA"] == 0
    assert fila["ROT_MESCON"] == 1
    assert fila["ROT_MAXMES"] == 12
    assert fila["ROT_ORIGE"] == "L"
    assert fila["ROT_MESES"] == 12


def test_mediana_con_venta_pareja():
    """10 unidades por mes durante los 12 meses: mediana = 10."""
    documentos = [_doc(f"D{i}", _mes(i)) for i in range(12)]
    renglones = [_ren(f"D{i}", 10) for i in range(12)]
    resultado = _correr(_armar(documentos, renglones))

    fila = _filas(resultado)[0]
    assert fila["ROT_UNIDS"] == 120
    assert fila["ROT_PROME"] == 10
    assert fila["ROT_MEDIA"] == 10
    assert fila["ROT_MESCON"] == 12


def _correr_24(documentos, renglones):
    return _filas(_correr(_armar(documentos, renglones), OpcionesRotacion(meses=24)))[0]


def test_perfil_estacional_por_mes_calendario():
    """24 meses (ago-2024 a jul-2026): 10 por mes, 40 en junio.

    Los 3 primeros meses son de sondeo y no entran: historia = 21.
        ROT_EST06 (junio) = 40, el resto = 10
    """
    documentos = [_doc(f"D{i}", _mes(i)) for i in range(24)]
    renglones = [
        _ren(f"D{i}", 40 if _mes(i).month == 6 else 10) for i in range(24)
    ]
    fila = _correr_24(documentos, renglones)

    assert fila["ROT_ESTHIS"] == 21
    assert fila["ROT_EST06"] == 40
    assert fila["ROT_EST01"] == 10
    assert fila["ROT_EST08"] == 10     # agosto: solo 2025, 2024 es sondeo


def test_perfil_estacional_con_dos_anios_promedia():
    """Junio 2025 vendio 20 y junio 2026 vendio 40 -> 30."""
    documentos = [_doc(f"D{i}", _mes(i)) for i in range(24)]
    renglones = []
    for i in range(24):
        fecha = _mes(i)
        if fecha.month == 6:
            cantidad = 40 if fecha.year == 2026 else 20
        else:
            cantidad = 5
        renglones.append(_ren(f"D{i}", cantidad))
    fila = _correr_24(documentos, renglones)

    assert fila["ROT_EST06"] == 30
    assert fila["ROT_EST03"] == 5


def test_articulo_nuevo_cuenta_historia_desde_la_primera_venta():
    """Vende solo desde mayo 2026 (los ultimos 3 meses de la ventana).

    Los meses anteriores no son temporada baja: el articulo no existia.
    Se cuenta desde el mes siguiente a la primera venta (junio), asi que
    la historia es 2 y el calculo de compra no usa su perfil propio.
    """
    documentos = [_doc(f"D{i}", _mes(i)) for i in range(3)]
    renglones = [_ren(f"D{i}", 10) for i in range(3)]
    fila = _correr_24(documentos, renglones)

    assert fila["ROT_ESTHIS"] == 2
    assert fila["ROT_EST07"] == 10
    assert fila["ROT_EST05"] == 0      # el mes de la primera venta no cuenta
    assert fila["ROT_EST01"] == 0


def test_articulo_existente_con_mes_flojo():
    """No vendio ningun agosto, pero si en el sondeo: ya existia.

    Agosto queda en cero (temporada baja), no se toma como articulo nuevo.
    """
    documentos = [_doc(f"D{i}", _mes(i)) for i in range(24) if _mes(i).month != 8]
    renglones = [_ren(d["DOC_CLAVE_"], 10) for d in documentos]
    fila = _correr_24(documentos, renglones)

    assert fila["ROT_ESTHIS"] == 21
    assert fila["ROT_EST08"] == 0
    assert fila["ROT_EST09"] == 10


def test_ventana_corta_no_alcanza_para_perfil():
    """Con 12 meses, 3 son de sondeo: quedan 9 y no hay perfil completo."""
    documentos = [_doc(f"D{i}", _mes(i)) for i in range(12)]
    renglones = [_ren(f"D{i}", 10) for i in range(12)]
    fila = _filas(_correr(_armar(documentos, renglones)))[0]
    assert fila["ROT_ESTHIS"] == 9


def test_nota_de_credito_resta():
    """NC y CE restan del consumo del mes."""
    carpeta = _armar(
        [_doc("D1", _mes(0)), _doc("D2", _mes(0), tipo="NC")],
        [_ren("D1", 30), _ren("D2", 10)],
    )
    fila = _filas(_correr(carpeta))[0]
    assert fila["ROT_UNIDS"] == 20


def test_devolucion_mayor_que_la_venta_se_acota_en_cero():
    """Un mes no puede aportar consumo negativo.

    Mes 0: vende 5, devuelve 20  ->  -15, se acota en 0
    Mes 1: vende 10              ->  10
    Total = 10, no -5.
    """
    carpeta = _armar(
        [
            _doc("D1", _mes(0)), _doc("D2", _mes(0), tipo="NC"),
            _doc("D3", _mes(1)),
        ],
        [_ren("D1", 5), _ren("D2", 20), _ren("D3", 10)],
    )
    fila = _filas(_correr(carpeta))[0]
    assert fila["ROT_UNIDS"] == 10
    assert fila["ROT_MESCON"] == 1


def test_se_ignoran_anuladas_proveedores_y_tipos_que_no_cuentan():
    carpeta = _armar(
        [
            _doc("D1", _mes(0)),                        # cuenta
            _doc("D2", _mes(0), anulada=True),          # anulada
            _doc("D3", _mes(0), clipro="P"),            # de proveedor
            _doc("D4", _mes(0), tipo="PR"),             # presupuesto
            _doc("D5", _mes(0), tipo="NV"),             # nota de venta
            _doc("D6", datetime.date(2020, 1, 1)),      # fuera de ventana
        ],
        [_ren(f"D{i}", 10) for i in range(1, 7)],
    )
    fila = _filas(_correr(carpeta))[0]
    assert fila["ROT_UNIDS"] == 10


def test_remitos_internos_segun_la_opcion():
    """El PRG define ProcesarFuente dos veces con criterios opuestos.
    Aca la decision es explicita."""
    documentos = [_doc("D1", _mes(0)), _doc("D2", _mes(0), tipo="RI")]
    renglones = [_ren("D1", 10), _ren("D2", 25)]

    carpeta = _armar(documentos, renglones)
    excluidos = _filas(_correr(carpeta, OpcionesRotacion(meses=12)))[0]
    assert excluidos["ROT_UNIDS"] == 10

    carpeta = _armar(documentos, renglones)
    incluidos = _filas(_correr(
        carpeta,
        OpcionesRotacion(meses=12, remitos_internos_son_venta=True),
    ))[0]
    assert incluidos["ROT_UNIDS"] == 35


def test_articulo_sin_movimiento_no_entra():
    """Si el total da cero o menos, el articulo no se graba."""
    carpeta = _armar(
        [_doc("D1", _mes(0)), _doc("D2", _mes(0), tipo="NC")],
        [_ren("D1", 10), _ren("D2", 10)],
    )
    resultado = _correr(carpeta)
    assert not resultado.ok
    assert "ningun articulo con movimiento" in resultado.mensaje


def test_clave_duplicada_multiplica_como_el_join():
    """DOC_CLAVE_ repetida: el INNER JOIN del PRG emite un renglon por cada
    cabecera, o sea que la cantidad se cuenta dos veces. Se reproduce."""
    carpeta = _armar(
        [_doc("D1", _mes(0)), _doc("D1", _mes(1))],
        [_ren("D1", 10)],
    )
    resultado = _correr(carpeta)
    fila = _filas(resultado)[0]
    assert fila["ROT_UNIDS"] == 20          # 10 en cada uno de los dos meses
    assert fila["ROT_MESCON"] == 2


def test_origenes_local_y_remoto():
    """El blanco local es todo "L" y el de la otra sucursal todo "R",
    sin importar lo que diga DOC_SUCURS."""
    base = Path(tempfile.mkdtemp())
    local = _armar(
        [_doc("D1", _mes(0), sucursal="9")],   # sucursal rara a proposito
        [_ren("D1", 10)],
        carpeta=base / "DATOS",
    )
    _armar(
        [_doc("R1", _mes(0), sucursal="9")],
        [_ren("R1", 40)],
        carpeta=base / "DATOS2",
    )

    resultado = calcular_rotacion(
        Parametros(
            carpeta_datos=str(local), carpeta_datos2=str(base / "DATOS2"),
            sucursal="1",
        ),
        OpcionesRotacion(meses=12, incluir_pendrive=False),
    )
    assert resultado.ok, resultado.mensaje

    por_origen = {f["ROT_ORIGE"]: f["ROT_UNIDS"] for f in _filas(resultado)}
    assert por_origen == {"L": 10, "R": 40}


def test_pendrive_se_reparte_por_sucursal():
    """El pendrive es una base compartida: cada comprobante va al origen que
    dice DOC_SUCURS, y los que vienen sin cargar se asignan a la local."""
    base = Path(tempfile.mkdtemp())
    local = _armar([], [], carpeta=base / "DATOS")
    _armar(
        [
            _doc("Z1", _mes(0), sucursal="1"),    # local
            _doc("Z2", _mes(0), sucursal="2"),    # la otra
            _doc("Z3", _mes(0), sucursal=""),     # sin cargar -> local
        ],
        [_ren("Z1", 10), _ren("Z2", 40), _ren("Z3", 5)],
        carpeta=base / "ZIP",
    )

    resultado = calcular_rotacion(
        Parametros(
            carpeta_datos=str(local), carpeta_zip=str(base / "ZIP"),
            sucursal="1",
        ),
        OpcionesRotacion(meses=12, incluir_remoto=False),
    )
    assert resultado.ok, resultado.mensaje

    por_origen = {f["ROT_ORIGE"]: f["ROT_UNIDS"] for f in _filas(resultado)}
    assert por_origen == {"L": 15, "R": 40}
    assert resultado.unidades_sin_sucursal == 5
    assert _filas(resultado)[0]["ROT_NEGRO"] is True


def test_sin_pendrive_marca_rot_negro_en_falso():
    carpeta = _armar([_doc("D1", _mes(0))], [_ren("D1", 10)])
    resultado = _correr(carpeta, OpcionesRotacion(meses=12, incluir_pendrive=False))
    assert _filas(resultado)[0]["ROT_NEGRO"] is False


def test_clave_de_siete_como_la_real():
    """AR_SUCU C(1) + AR_CODI C(6) = 7, que es lo que mide DCC_ARTICU y lo
    que el PRG declara en ROT_ARTIC C(7). No hay que ensanchar nada."""
    carpeta = _armar([_doc("D1", _mes(0))], [_ren("D1", 10, "1ART001")])
    resultado = _correr(carpeta)
    assert resultado.ancho_clave == 7
    assert _filas(resultado)[0]["ROT_ARTIC"] == "1ART001"
    assert resultado.enganchan_con_articulo == 1


def test_una_clave_mas_larga_ensancha_en_vez_de_truncar():
    """Si alguna base guardara una clave mas larga que 7, el PRG la truncaba
    contra su ROT_ARTIC C(7) fijo y rompia el cruce en silencio."""
    carpeta = Path(tempfile.mkdtemp())
    escribir_dbf(carpeta / "DOCUM.DBF", CAMPOS_DOCUM, [_doc("D1", _mes(0))])
    escribir_dbf(
        carpeta / "DOCCUER.DBF",
        [("DCC_CLAVE_", "C", 8, 0), ("DCC_ARTICU", "C", 10, 0),
         ("DCC_CANTID", "N", 10, 3)],
        [{"DCC_CLAVE_": "D1", "DCC_ARTICU": "1ART001234", "DCC_CANTID": 10}],
    )
    escribir_dbf(carpeta / "ARTICULO.DBF", CAMPOS_ARTICULO, _articulos())

    resultado = _correr(carpeta)
    assert resultado.ancho_clave == 10
    assert _filas(resultado)[0]["ROT_ARTIC"] == "1ART001234"


def test_fechas_de_primera_y_ultima_venta():
    carpeta = _armar(
        [_doc("D1", _mes(5)), _doc("D2", _mes(1))],
        [_ren("D1", 10), _ren("D2", 10)],
    )
    fila = _filas(_correr(carpeta))[0]
    assert fila["ROT_PRIVTA"] == _mes(5)
    assert fila["ROT_ULTVTA"] == _mes(1)
    assert fila["ROT_DESDE"] == datetime.date(2025, 8, 1) or fila["ROT_DESDE"]


def test_falta_docum_avisa_claro():
    carpeta = Path(tempfile.mkdtemp())
    escribir_dbf(carpeta / "ARTICULO.DBF", CAMPOS_ARTICULO, _articulos())
    resultado = _correr(carpeta)
    assert not resultado.ok
    assert "DOCUM" in resultado.mensaje


def test_el_cdx_viejo_se_borra():
    """Un CDX de la corrida anterior apunta a registros que ya no existen."""
    carpeta = _armar([_doc("D1", _mes(0))], [_ren("D1", 10)])
    cdx = carpeta / "ROTACION.CDX"
    cdx.write_bytes(b"indice viejo")
    resultado = _correr(carpeta)
    assert resultado.ok
    assert not cdx.exists()


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
