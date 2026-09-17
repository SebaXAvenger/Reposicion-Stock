"""
Autodeteccion del entorno leyendo CONFIG.DBF.

El ERP no inventa las rutas: las saca de CONFIG.DBF al arrancar. En
principal.prg, antes de cualquier otra cosa, hace esto:

    USE (dir_base_ + "CONFIG")
    sis_path_  = ADDBS(UPPER(ALLTRIM(cfg_path__)))
    zip_path_  = ALLTRIM(cfg_respal)
    sis_path2  = ALLTRIM(cfg_p_sis2)
    sis_sucurs = cfg_sucurs

O sea que las cuatro variables publicas que este programa necesita estan
guardadas en una tabla, en un lugar conocido. No hace falta que nadie las
escriba a mano en una pantalla de configuracion: alcanza con encontrar esa
tabla y leerla, que es exactamente lo que hace el ERP.

DONDE SE BUSCA, en este orden:
    1. La carpeta que se indique explicitamente (--erp).
    2. La carpeta del propio ejecutable. Es el caso comodo: se copia
       reposicion.exe al lado de SISTEMA.EXE y se configura solo.
    3. La carpeta de datos, si ya se conoce. principal.prg contempla que
       haya una copia de CONFIG.DBF en el servidor ademas de la local.

Esta capa solo RELLENA VACIOS: nunca pisa un valor que haya llegado por
linea de comandos, por el archivo de traspaso o por la configuracion que el
usuario guardo a mano. Si alguien eligio otra carpeta a proposito, esa
eleccion manda.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .dbf import ErrorDBF, TablaDBF
from .vfp import alltrim

# Campo de CONFIG.DBF -> campo de Parametros, con el tratamiento que le da
# principal.prg a cada uno.
EQUIVALENCIAS = {
    "CFG_PATH__": "carpeta_datos",     # sis_path_
    "CFG_P_SIS2": "carpeta_datos2",    # sis_path2
    "CFG_RESPAL": "carpeta_zip",       # zip_path_
    "CFG_SUCURS": "sucursal",          # sis_sucurs
}

# Extras informativos, para el titulo de la ventana y el diagnostico.
EXTRAS = ["CFG_TITULO", "CFG_CODSUC", "CFG_MAQUIN", "CFG_SERVER"]


class EntornoERP:
    """Lo que se pudo leer de un CONFIG.DBF."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.valores: dict[str, Any] = {}
        self.titulo: str = ""
        self.codigo_sucursal: str = ""
        self.maquina: str = ""
        self.es_servidor: bool = False

    def __bool__(self) -> bool:
        return bool(self.valores.get("carpeta_datos"))

    def descripcion(self) -> str:
        partes = [f"CONFIG.DBF en {self.ruta}"]
        if self.titulo:
            partes.append(f"sistema '{self.titulo}'")
        if self.valores.get("sucursal"):
            partes.append(f"sucursal {self.valores['sucursal']}")
        return "  ·  ".join(partes)


def leer_config(carpeta: Path | str) -> EntornoERP | None:
    """Lee un CONFIG.DBF y devuelve el entorno, o None si no sirve."""
    carpeta = Path(carpeta)
    ruta = _buscar_archivo(carpeta)
    if ruta is None:
        return None

    entorno = EntornoERP(ruta)
    try:
        with TablaDBF(ruta) as tabla:
            campos = [c for c in EQUIVALENCIAS if tabla.tiene(c)]
            if "CFG_PATH__" not in campos:
                # No es el CONFIG.DBF del ERP, es otra tabla con ese nombre
                return None
            campos += [c for c in EXTRAS if tabla.tiene(c)]

            fila = next(iter(tabla.filas(campos)), None)
            if fila is None:                      # tabla vacia
                return None

            for campo_dbf, campo_parametro in EQUIVALENCIAS.items():
                valor = alltrim(fila.get(campo_dbf, ""))
                if valor:
                    entorno.valores[campo_parametro] = valor

            entorno.titulo = alltrim(fila.get("CFG_TITULO", ""))
            entorno.codigo_sucursal = alltrim(fila.get("CFG_CODSUC", ""))
            entorno.maquina = alltrim(fila.get("CFG_MAQUIN", ""))
            entorno.es_servidor = bool(fila.get("CFG_SERVER"))
    except (ErrorDBF, OSError, StopIteration):
        return None

    return entorno if entorno else None


def detectar(carpetas: list[Path | str]) -> EntornoERP | None:
    """Prueba varias carpetas y devuelve el primer CONFIG.DBF que sirva."""
    vistas: set[str] = set()
    for carpeta in carpetas:
        if not carpeta:
            continue
        clave = str(carpeta).lower()
        if clave in vistas:
            continue
        vistas.add(clave)
        entorno = leer_config(carpeta)
        if entorno:
            return entorno
    return None


def _buscar_archivo(carpeta: Path) -> Path | None:
    if not carpeta.is_dir():
        return None
    for nombre in ("CONFIG.DBF", "config.dbf", "Config.dbf"):
        candidato = carpeta / nombre
        if candidato.is_file():
            return candidato
    # Ultimo intento, por si el recurso de red distingue mayusculas
    try:
        for hijo in carpeta.iterdir():
            if hijo.name.lower() == "config.dbf" and hijo.is_file():
                return hijo
    except OSError:
        pass
    return None
