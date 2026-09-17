"""
Pruebas de la cascada de parametros y de la autodeteccion del entorno.

Lo que se verifica es la PRECEDENCIA: quien le gana a quien. Si esto se
rompe, el programa abre con las tablas equivocadas y no hay ningun sintoma
salvo que los numeros no son los que el usuario espera.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import (  # noqa: E402
    Parametros, cargar_parametros, completar_desde_erp, reparar_barra_final,
)
from app.config_erp import detectar, leer_config  # noqa: E402
from tools.dbf_writer import escribir_dbf  # noqa: E402
from tools.generar_datos_prueba import CAMPOS_CONFIG  # noqa: E402


def _config(carpeta: Path, **cambios) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    fila = {
        "CFG_PATH__": r"X:\SISTEMA\DATOS",
        "CFG_P_SIS2": r"Y:\SUC2\DATOS",
        "CFG_RESPAL": r"Z:\PENDRIVE",
        "CFG_SUCURS": "1",
        "CFG_CODSUC": "001",
        "CFG_TITULO": "FERRETERIA",
        "CFG_MAQUIN": "1A",
        "CFG_SERVER": False,
        "CFG_OBSERV": "",
    }
    fila.update(cambios)
    escribir_dbf(carpeta / "CONFIG.DBF", CAMPOS_CONFIG, [fila])
    return carpeta


# ---------------------------------------------------------------------------

def test_lee_las_cuatro_variables_del_erp():
    """Son las mismas asignaciones que hace principal.prg al arrancar."""
    carpeta = _config(Path(tempfile.mkdtemp()))
    entorno = leer_config(carpeta)

    assert entorno is not None
    assert entorno.valores["carpeta_datos"] == r"X:\SISTEMA\DATOS"
    assert entorno.valores["carpeta_datos2"] == r"Y:\SUC2\DATOS"
    assert entorno.valores["carpeta_zip"] == r"Z:\PENDRIVE"
    assert entorno.valores["sucursal"] == "1"
    assert entorno.titulo == "FERRETERIA"


def test_una_tabla_que_no_es_el_config_del_erp_se_descarta():
    """Puede haber un CONFIG.DBF de otra cosa. Sin CFG_PATH__ no sirve."""
    carpeta = Path(tempfile.mkdtemp())
    escribir_dbf(
        carpeta / "CONFIG.DBF",
        [("CLAVE", "C", 10, 0), ("VALOR", "C", 10, 0)],
        [{"CLAVE": "algo", "VALOR": "otra cosa"}],
    )
    assert leer_config(carpeta) is None


def test_config_vacio_o_ausente():
    vacia = Path(tempfile.mkdtemp())
    assert leer_config(vacia) is None

    carpeta = Path(tempfile.mkdtemp())
    escribir_dbf(carpeta / "CONFIG.DBF", CAMPOS_CONFIG, [])
    assert leer_config(carpeta) is None


def test_detectar_toma_la_primera_carpeta_que_sirve():
    sin_config = Path(tempfile.mkdtemp())
    con_config = _config(Path(tempfile.mkdtemp()))
    entorno = detectar([sin_config, con_config])
    assert entorno is not None
    assert entorno.ruta.parent == con_config


def test_la_autodeteccion_solo_rellena_vacios():
    """Si el usuario o el ERP ya fijaron un valor, CONFIG.DBF no lo pisa.

    Es la regla que hace que la cascada sea predecible: lo explicito manda
    sobre lo detectado.
    """
    carpeta = _config(Path(tempfile.mkdtemp()))
    parametros = Parametros(carpeta_datos=r"D:\ELEGIDO\A\MANO")

    completar_desde_erp(parametros, str(carpeta))

    assert parametros.carpeta_datos == r"D:\ELEGIDO\A\MANO"   # no se pisa
    assert parametros.carpeta_datos2 == r"Y:\SUC2\DATOS"      # estaba vacio
    assert parametros.sucursal == "1"


def test_forzar_pisa_todo():
    """Es lo que hace el boton 'Detectar del sistema': el usuario lo pide."""
    carpeta = _config(Path(tempfile.mkdtemp()))
    parametros = Parametros(carpeta_datos=r"D:\VIEJO", sucursal="9")

    entorno = completar_desde_erp(parametros, str(carpeta), forzar=True)

    assert entorno is not None
    assert parametros.carpeta_datos == r"X:\SISTEMA\DATOS"
    assert parametros.sucursal == "1"
    assert "CONFIG.DBF" in parametros.origen["carpeta_datos"]


def test_el_json_guardado_le_gana_al_config():
    """Un JSON de configuracion propio se aplica antes, asi que CONFIG.DBF
    solo completa lo que ese JSON no traiga."""
    carpeta = _config(Path(tempfile.mkdtemp()))
    guardado = carpeta / "reposicion.json"
    guardado.write_text(
        json.dumps({"carpeta_datos": r"E:\OTRO", "cobertura": 90}),
        encoding="utf-8",
    )

    parametros = Parametros()
    from app.config import _aplicar_json

    _aplicar_json(parametros, guardado, "config de prueba")
    completar_desde_erp(parametros, str(carpeta))

    assert parametros.carpeta_datos == r"E:\OTRO"
    assert parametros.cobertura == 90
    assert parametros.carpeta_zip == r"Z:\PENDRIVE"


# ---------------------------------------------------------------------------
# La barra final de Windows
# ---------------------------------------------------------------------------

def test_la_barra_final_rompe_la_linea_de_comandos():
    """El caso real: el menu del ERP manda

        --data "S:\\" --sucursal "1" --data2 "X:\\"

    y Windows entrega UN solo argumento, porque el \\" escapa la comilla:

        ['--data', 'S:" --sucursal 1 --data2 X:"']

    Sin reparacion, --sucursal y --data2 nunca se leen y el programa abre
    la configuracion inicial como si no le hubieran pasado nada.
    """
    roto = ["--data", 'S:" --sucursal 1 --data2 X:"']
    reparado, se_reparo = reparar_barra_final(roto)

    assert se_reparo
    assert reparado == ["--data", "S:\\", "--sucursal", "1", "--data2", "X:\\"]


def test_reparacion_con_rutas_largas():
    roto = ["--data", 'X:\\SISTEMA\\DATOS" --sucursal 1 --zip Z:\\PEN"']
    reparado, _ = reparar_barra_final(roto)
    assert reparado == [
        "--data", "X:\\SISTEMA\\DATOS\\", "--sucursal", "1",
        "--zip", "Z:\\PEN\\",
    ]


def test_una_linea_sana_no_se_toca():
    sana = ["--data", "S:\\", "--sucursal", "1", "--data2", "X:\\"]
    reparado, se_reparo = reparar_barra_final(sana)
    assert not se_reparo
    assert reparado == sana


def test_la_reparacion_llega_hasta_los_parametros():
    """De punta a punta: la linea rota tiene que terminar dando los mismos
    parametros que la sana."""
    rotos, _ = cargar_parametros(
        ["--data", 'S:" --sucursal 1 --data2 X:"', "--sin-autodeteccion"]
    )
    assert rotos.carpeta_datos == "S:\\"
    assert rotos.sucursal == "1"
    assert rotos.carpeta_datos2 == "X:\\"
    assert rotos.argv_reparado is True

    sanos, _ = cargar_parametros(
        ["--data", "S:\\", "--sucursal", "1", "--data2", "X:\\",
         "--sin-autodeteccion"]
    )
    assert sanos.carpeta_datos == rotos.carpeta_datos
    assert sanos.sucursal == rotos.sucursal
    assert sanos.carpeta_datos2 == rotos.carpeta_datos2
    assert sanos.argv_reparado is False


def test_unidad_pelada_se_convierte_en_raiz():
    """"S:" es el directorio ACTUAL de esa unidad, no su raiz. Si el
    lanzador saco la barra para esquivar el escapado, hay que devolverla."""
    parametros, _ = cargar_parametros(
        ["--data", "S:", "--sucursal", "1", "--sin-autodeteccion"]
    )
    assert parametros.carpeta_datos == "S:\\"


def test_las_comillas_sueltas_se_limpian():
    parametros, _ = cargar_parametros(
        ["--data", '"S:\\"', "--sucursal", "1", "--sin-autodeteccion"]
    )
    assert parametros.carpeta_datos == "S:\\"


def test_validar_detecta_lo_que_falta():
    parametros = Parametros()
    problemas = parametros.validar()
    assert any("carpeta de datos" in p for p in problemas)
    assert any("sucursal" in p for p in problemas)


def test_normalizacion_de_la_sucursal():
    """cfg_sucurs se guarda sin ALLTRIM en principal.prg, asi que puede
    venir con espacios. El formulario hacia ALLTRIM(sis_sucurs)."""
    carpeta = _config(Path(tempfile.mkdtemp()), CFG_SUCURS="2")
    parametros = Parametros()
    completar_desde_erp(parametros, str(carpeta))
    assert parametros.sucursal == "2"


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
