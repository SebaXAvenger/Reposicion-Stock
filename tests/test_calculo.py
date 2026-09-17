"""
Pruebas de la logica de reposicion con casos armados a mano.

Los numeros esperados salen del ejemplo que la propia ayuda del formulario
usa para explicar el calculo, asi que si estas pruebas pasan, el port
reproduce lo que el usuario tiene documentado.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.calculo import (  # noqa: E402
    ESTAC_TOPE_MAXIMO, MODO_MANUAL, MODO_ROTACION, MotorReposicion,
    indice_estacional, pesos_horizonte,
)
from app.config import Parametros  # noqa: E402
from app.datos import (  # noqa: E402
    Articulo, Catalogo, DemandaArticulo, InfoRotacion, clave_proveedor,
    normalizar_proveedor, nombre_proveedor,
)


def _articulo(clave="1ART001", stock=2.0, costo=100.0, minimo=0.0, maximo=0.0,
              proveedor="1   232", desc_proveedor="", rubro="HER"):
    return Articulo(
        sucursal="1", codigo=clave[1:], clave=clave, clave_corta=clave[1:],
        cod_prov_articulo="PROV-1", descripcion="ALICATE CORTAPERNO 18",
        unidad="UN", cod_proveedor_bruto=proveedor,
        desc_proveedor=desc_proveedor, minimo=minimo, maximo=maximo,
        stock_local=stock, costo=costo, marca="BAHCO", ubicacion="B-12-3",
        rubro=rubro,
    )


def _demanda(promedio=6.0, mediana=6.0, meses=12, promedio_r=0.0,
             perfil=None, historia=0):
    return DemandaArticulo(
        promedio_local=promedio, promedio_remoto=promedio_r,
        mediana_local=mediana, mediana_remota=0.0,
        meses_con_venta_local=meses, meses_con_venta_remoto=0,
        unidades_totales=promedio * meses, ultima_venta=None,
        perfil_local=perfil, perfil_remoto=None,
        historia_local=historia, historia_remota=0,
    )


# Perfil de temporada de invierno: 10 por mes, 40 en junio y julio.
# Promedio anual = (10 x 10 + 40 x 2) / 12 = 15
PERFIL_INVIERNO = [10.0] * 5 + [40.0, 40.0] + [10.0] * 5
PARECIDO_A_MAYO = datetime.date(2026, 5, 25)
PARECIDO_A_OCTUBRE = datetime.date(2026, 10, 1)


def _catalogo(articulos, demanda, remoto=None, respaldo=None):
    catalogo = Catalogo()
    catalogo.proveedores_respaldo = respaldo or {}
    catalogo.articulos = articulos
    catalogo.total_catalogo = len(articulos)
    catalogo.demanda = demanda
    catalogo.proveedores = {"1   232": "BULONFER S.A."}
    catalogo.info_rotacion = InfoRotacion(
        disponible=True, con_perfil=any(
            d.perfil_local is not None for d in demanda.values()
        ),
    )
    if remoto:
        catalogo.stock_remoto = remoto
        catalogo.remoto_disponible = True
    return catalogo


def _parametros(**cambios):
    base = dict(
        carpeta_datos="/tmp", sucursal="1", punto_pedido=15, cobertura=45,
        excluir_esporadicos=True,
    )
    base.update(cambios)
    return Parametros(**base)


# ---------------------------------------------------------------------------

def test_ejemplo_de_la_ayuda():
    """El caso que la ayuda del formulario usa para explicar el calculo:

        Se venden 6 por mes = 0,2 por dia. Quedan 2 en el deposito.
        Dias de stock  = 2 / 0,2 = 10 dias  ->  10 < 15, entra en la lista
        Objetivo       = 0,2 x 45 = 9 unidades
        Sugerido       = 9 - 2 = 7 unidades
    """
    catalogo = _catalogo([_articulo(stock=2.0)], {"1ART001": _demanda(6.0)})
    resultado = MotorReposicion(_parametros(), catalogo).calcular(MODO_ROTACION, False)

    assert resultado.ok
    linea = resultado.lineas[0]
    assert round(linea.dias_stock, 1) == 10.0
    assert linea.cant_pedir == 7
    assert linea.subtotal == 700.0


def test_ejemplo_de_la_ayuda_con_60_dias():
    """Subiendo la cobertura a 60 dias, el objetivo pasa a 12 y sugiere 10."""
    catalogo = _catalogo([_articulo(stock=2.0)], {"1ART001": _demanda(6.0)})
    resultado = MotorReposicion(_parametros(cobertura=60), catalogo).calcular(
        MODO_ROTACION, False
    )
    assert resultado.lineas[0].cant_pedir == 10


def test_filtro_sin_ventas():
    """Un articulo sin fila en ROTACION es catalogo muerto, no faltante."""
    catalogo = _catalogo([_articulo(stock=0.0)], {})
    resultado = MotorReposicion(_parametros(), catalogo).calcular(MODO_ROTACION, False)
    assert not resultado.ok
    assert resultado.diagnostico.desc_sin_venta == 1


def test_filtro_esporadico():
    """Un solo mes con venta queda afuera si el filtro esta activo."""
    parametros = _parametros()
    catalogo = _catalogo([_articulo(stock=0.0)], {"1ART001": _demanda(6.0, meses=1)})
    resultado = MotorReposicion(parametros, catalogo).calcular(MODO_ROTACION, False)
    assert resultado.diagnostico.desc_esporadico == 1

    # Desactivando el filtro, el mismo articulo entra
    parametros.excluir_esporadicos = False
    catalogo = _catalogo([_articulo(stock=0.0)], {"1ART001": _demanda(6.0, meses=1)})
    resultado = MotorReposicion(parametros, catalogo).calcular(MODO_ROTACION, False)
    assert resultado.ok


def test_filtro_stock_suficiente():
    """Con 100 unidades y 6 por mes le alcanza de sobra: no entra."""
    catalogo = _catalogo([_articulo(stock=100.0)], {"1ART001": _demanda(6.0)})
    resultado = MotorReposicion(_parametros(), catalogo).calcular(MODO_ROTACION, False)
    assert resultado.diagnostico.desc_stock_ok == 1


def test_guardas_de_parametros():
    """Punto de pedido mayor que la cobertura no puede correr."""
    catalogo = _catalogo([_articulo()], {"1ART001": _demanda()})
    resultado = MotorReposicion(
        _parametros(punto_pedido=60, cobertura=45), catalogo
    ).calcular(MODO_ROTACION, False)
    assert not resultado.ok
    assert "no puede ser mayor" in resultado.mensaje


def test_stock_negativo_como_cero():
    """El stock negativo es un error de inventario, no faltante real.

    Con -10 de stock y la opcion apagada, la cuenta pide de mas para tapar
    el negativo. Con la opcion prendida, se calcula desde cero.
    """
    demanda = {"1ART001": _demanda(30.0)}      # 1 por dia

    apagado = MotorReposicion(
        _parametros(negativo_como_cero=False),
        _catalogo([_articulo(stock=-10.0)], demanda),
    ).calcular(MODO_ROTACION, False)

    prendido = MotorReposicion(
        _parametros(negativo_como_cero=True),
        _catalogo([_articulo(stock=-10.0)], dict(demanda)),
    ).calcular(MODO_ROTACION, False)

    assert apagado.lineas[0].cant_pedir == 55      # 45 objetivo + 10 de agujero
    assert prendido.lineas[0].cant_pedir == 45     # 45 objetivo, el negativo se ignora
    # En los dos casos la grilla sigue mostrando el stock REAL
    assert apagado.lineas[0].stock_total == -10.0
    assert prendido.lineas[0].stock_total == -10.0


def test_reparto_entre_depositos():
    """El pedido consolidado se reparte proporcional al faltante de cada
    deposito, y las dos partes tienen que sumar el total."""
    demanda = {"1ART001": _demanda(30.0, promedio_r=30.0)}
    catalogo = _catalogo(
        [_articulo(stock=0.0)], demanda, remoto={"1ART001": 0.0}
    )
    resultado = MotorReposicion(_parametros(), catalogo).calcular(MODO_ROTACION, True)

    linea = resultado.lineas[0]
    assert linea.cant_pedir == 90                  # 45 dias para los dos juntos
    assert linea.pedir_local + linea.pedir_remoto == linea.cant_pedir
    assert abs(linea.prop_local - 0.5) < 1e-9      # misma demanda, mitad y mitad


def test_edicion_manual_rehace_el_reparto():
    demanda = {"1ART001": _demanda(30.0, promedio_r=30.0)}
    catalogo = _catalogo([_articulo(stock=0.0)], demanda, remoto={"1ART001": 0.0})
    resultado = MotorReposicion(_parametros(), catalogo).calcular(MODO_ROTACION, True)

    linea = resultado.lineas[0]
    linea.fijar_cantidad(31)
    assert linea.pedir_local + linea.pedir_remoto == 31
    assert linea.subtotal == 3100.0
    assert linea.modificada

    linea.fijar_cantidad(-5)                       # no se aceptan negativas
    assert linea.cant_pedir == 0


def test_modo_manual():
    """Con minimo 10 y maximo 40, y 2 de stock, sugiere 38."""
    catalogo = _catalogo(
        [_articulo(stock=2.0, minimo=10.0, maximo=40.0)], {}
    )
    resultado = MotorReposicion(_parametros(), catalogo).calcular(MODO_MANUAL, False)
    assert resultado.ok
    assert resultado.lineas[0].cant_pedir == 38


def test_modo_manual_sin_objetivo():
    """Sin minimo ni maximo cargados no hay nada que sugerir: es ruido."""
    catalogo = _catalogo([_articulo(stock=0.0)], {})
    parametros = _parametros(manual_sin_parametros=True)
    resultado = MotorReposicion(parametros, catalogo).calcular(MODO_MANUAL, False)
    assert not resultado.ok
    assert resultado.diagnostico.desc_sin_objetivo == 1


def test_cruce_con_rotacion_por_clave_corta():
    """ROT_ARTIC puede guardar el codigo sin el prefijo de sucursal.

    Si el cruce no tolerara las dos formas, TODO el catalogo caeria en
    "sin ventas registradas" y la lista saldria vacia sin ningun error.
    """
    catalogo = _catalogo([_articulo(stock=2.0)], {"ART001": _demanda(6.0)})
    resultado = MotorReposicion(_parametros(), catalogo).calcular(MODO_ROTACION, False)

    assert resultado.ok
    assert resultado.lineas[0].cant_pedir == 7
    assert resultado.diagnostico.enganche_clave_corta == 1
    assert resultado.diagnostico.enganche_clave_completa == 0


def test_cruce_con_rotacion_por_clave_completa():
    catalogo = _catalogo([_articulo(stock=2.0)], {"1ART001": _demanda(6.0)})
    resultado = MotorReposicion(_parametros(), catalogo).calcular(MODO_ROTACION, False)
    assert resultado.diagnostico.enganche_clave_completa == 1
    assert resultado.diagnostico.enganche_clave_corta == 0


def test_desc_prov_como_respaldo():
    """Si PROVEEDO no engancha, el nombre sale de DESC_PROV del articulo.

    Sin este respaldo, una deteccion fallida del campo codigo en PROVEEDO
    dejaria toda la lista con "[codigo] no esta en PROVEEDO".
    """
    articulos = [_articulo(stock=0.0, desc_proveedor="BULONFER S.A.")]
    catalogo = _catalogo(
        articulos, {"1ART001": _demanda(30.0)},
        respaldo={"1   232": "BULONFER S.A."},
    )
    catalogo.proveedores = {}          # PROVEEDO no aporta nada
    resultado = MotorReposicion(_parametros(), catalogo).calcular(MODO_ROTACION, False)

    assert resultado.proveedores[0].nombre == "BULONFER S.A."


def test_sin_respaldo_avisa_que_no_encontro_el_proveedor():
    catalogo = _catalogo([_articulo(stock=0.0)], {"1ART001": _demanda(30.0)})
    catalogo.proveedores = {}
    resultado = MotorReposicion(_parametros(), catalogo).calcular(MODO_ROTACION, False)
    assert "no esta en PROVEEDO" in resultado.proveedores[0].nombre
    assert any("no se pudieron resolver" in d for d in catalogo.diagnostico)


def test_clave_de_proveedor_con_codigo_numerico():
    """PROVEEDO guarda PR_CODIGO como NUMERICO y PR_SUCURS aparte.

    La clave con la que AR_PROV lo referencia es la sucursal pegada adelante
    del codigo justificado a la derecha en 6 lugares, con espacios: el
    proveedor 232 de la sucursal 1 es "1   232".

    Es la misma cadena que arma NormalizarProv a partir de AR_PROV, y es la
    que tiene que salir de las dos puntas para que el cruce enganche.
    """
    assert clave_proveedor("1", 232) == "1   232"
    assert clave_proveedor("1", 232.0) == "1   232"       # por si viene float
    assert clave_proveedor("2", 5) == "2     5"
    assert clave_proveedor("1", 123456) == "1123456"
    assert clave_proveedor("", 232) == "1   232"          # sin sucursal -> "1"
    assert clave_proveedor("1", None) == "*SINPRO"
    assert clave_proveedor("1", 0) == "1     0"

    # Las dos puntas del cruce tienen que coincidir
    assert clave_proveedor("1", 232) == normalizar_proveedor("232")
    assert clave_proveedor("1", 13) == normalizar_proveedor("1    13")


def test_normalizacion_de_proveedor():
    assert normalizar_proveedor("232") == "1   232"
    assert normalizar_proveedor("") == "*SINPRO"
    assert normalizar_proveedor("   ") == "*SINPRO"
    assert normalizar_proveedor("1   232") == "1   232"

    proveedores = {"1   232": "BULONFER S.A."}
    assert nombre_proveedor("1   232", proveedores) == "BULONFER S.A."
    assert nombre_proveedor("1   999", {}, {"1   999": "DEL ARTICULO"}) == "DEL ARTICULO"
    assert nombre_proveedor("*SINPRO", proveedores) == "(sin proveedor asignado)"
    assert "no esta en PROVEEDO" in nombre_proveedor("1   999", proveedores)


def test_agrupado_ordena_por_monto():
    articulos = [
        _articulo(clave="1ART001", stock=0.0, costo=10.0, proveedor="232"),
        _articulo(clave="1ART002", stock=0.0, costo=500.0, proveedor="777"),
    ]
    demanda = {"1ART001": _demanda(30.0), "1ART002": _demanda(30.0)}
    resultado = MotorReposicion(
        _parametros(), _catalogo(articulos, demanda)
    ).calcular(MODO_ROTACION, False)

    assert [p.codigo for p in resultado.proveedores] == ["1   777", "1   232"]
    assert resultado.proveedores[0].criticos == 1


# ---------------------------------------------------------------------------
# Estacionalidad
# ---------------------------------------------------------------------------

def test_pesos_del_horizonte():
    """Del 20 de mayo, 45 dias: 12 de mayo, 30 de junio y 3 de julio."""
    pesos = pesos_horizonte(datetime.date(2026, 5, 20), 45)
    assert abs(sum(pesos) - 1) < 1e-9
    assert round(pesos[4] * 45) == 12
    assert round(pesos[5] * 45) == 30
    assert round(pesos[6] * 45) == 3


def test_indice_perfil_parejo_es_uno():
    assert indice_estacional([10.0] * 12, pesos_horizonte(PARECIDO_A_MAYO, 45)) == 1


def test_indice_tiene_tope():
    """Un solo mes con venta no puede multiplicar la compra por 12."""
    perfil = [0.0] * 5 + [120.0] + [0.0] * 6
    pesos = pesos_horizonte(datetime.date(2026, 6, 1), 30)
    assert indice_estacional(perfil, pesos) == ESTAC_TOPE_MAXIMO


def test_temporada_alta_sube_la_compra():
    """Antes del invierno compra mas que el promedio parejo."""
    demanda = {"1ART001": _demanda(15.0, perfil=PERFIL_INVIERNO, historia=24)}
    catalogo = _catalogo([_articulo(stock=0.0)], demanda)
    resultado = MotorReposicion(
        _parametros(), catalogo, hoy=PARECIDO_A_MAYO
    ).calcular(MODO_ROTACION, False)

    linea = resultado.lineas[0]
    assert linea.fuente_estacional == "articulo"
    assert linea.indice_estacional > 1.5
    # Sin temporadas pediria 15 / 30 x 45 = 22,5 -> 23
    assert linea.cant_pedir > 23
    assert resultado.diagnostico.estac_articulo == 1


def test_temporada_baja_baja_la_compra():
    demanda = {"1ART001": _demanda(15.0, perfil=PERFIL_INVIERNO, historia=24)}
    catalogo = _catalogo([_articulo(stock=0.0)], demanda)
    resultado = MotorReposicion(
        _parametros(), catalogo, hoy=PARECIDO_A_OCTUBRE
    ).calcular(MODO_ROTACION, False)

    linea = resultado.lineas[0]
    assert linea.indice_estacional < 1
    assert linea.cant_pedir < 23


def test_apagado_calcula_como_siempre():
    """Con la opcion apagada el numero es el de siempre, aunque haya perfil."""
    demanda = {"1ART001": _demanda(15.0, perfil=PERFIL_INVIERNO, historia=24)}
    catalogo = _catalogo([_articulo(stock=0.0)], demanda)
    resultado = MotorReposicion(
        _parametros(estacionalidad=False), catalogo, hoy=PARECIDO_A_MAYO
    ).calcular(MODO_ROTACION, False)

    linea = resultado.lineas[0]
    assert linea.cant_pedir == 23
    assert linea.indice_estacional == 1
    assert linea.fuente_estacional == ""


def test_poca_historia_usa_el_rubro():
    """Un articulo con 5 meses de historia toma la temporada de su rubro.

    El rubro tiene 5 articulos con historia completa y perfil de invierno.
    """
    articulos = [
        _articulo(clave=f"1ART00{n}", stock=500.0, rubro="EST") for n in (1, 2, 3, 4, 5)
    ] + [_articulo(clave="1NUEVO1", stock=0.0, rubro="EST")]
    demanda = {
        f"1ART00{n}": _demanda(15.0, perfil=PERFIL_INVIERNO, historia=24)
        for n in (1, 2, 3, 4, 5)
    }
    demanda["1NUEVO1"] = _demanda(
        15.0, perfil=[15.0] * 12, historia=5
    )
    resultado = MotorReposicion(
        _parametros(), _catalogo(articulos, demanda), hoy=PARECIDO_A_MAYO
    ).calcular(MODO_ROTACION, False)

    linea = next(l for l in resultado.lineas if l.clave == "1NUEVO1")
    assert linea.fuente_estacional == "rubro"
    assert linea.indice_estacional > 1.5


def test_sin_articulo_ni_rubro_no_ajusta():
    """Poca historia y rubro sin datos suficientes: indice 1."""
    demanda = {"1ART001": _demanda(15.0, perfil=[15.0] * 12, historia=5)}
    resultado = MotorReposicion(
        _parametros(), _catalogo([_articulo(stock=0.0)], demanda),
        hoy=PARECIDO_A_MAYO,
    ).calcular(MODO_ROTACION, False)

    linea = resultado.lineas[0]
    assert linea.fuente_estacional == ""
    assert linea.cant_pedir == 23
    assert resultado.diagnostico.estac_neutro == 1


def test_rotacion_vieja_sin_perfil_no_rompe():
    """ROTACION.DBF generada por el PRG de VFP: sin perfil, calcula igual."""
    catalogo = _catalogo([_articulo(stock=2.0)], {"1ART001": _demanda(6.0)})
    resultado = MotorReposicion(_parametros(), catalogo).calcular(MODO_ROTACION, False)
    assert resultado.lineas[0].cant_pedir == 7
    assert not resultado.diagnostico.estacionalidad_disponible
    assert "recalcular" in resultado.leyenda_rotacion


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
