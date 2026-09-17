"""
Resolucion de los parametros que el formulario heredaba del ERP.

Dentro de Visual FoxPro estas cuatro variables publicas ya existian en el
entorno. Al sacar el formulario del ERP se pierden, asi que hay que
inyectarlas desde afuera.

    sis_path_   ->  carpeta_datos     ARTICULO.DBF, PROVEEDO.DBF, ROTACION.DBF
    sis_path2   ->  carpeta_datos2    ARTICULO.DBF de la otra sucursal
    sis_sucurs  ->  sucursal          codigo de sucursal (filtra AR_SUCU)
    zip_path_   ->  carpeta_zip       segunda base, para el recalculo de rotacion

ORDEN DE RESOLUCION (gana el primero que aporte el valor):

    1. Linea de comandos          -> lanzado por el ERP
    2. Archivo de traspaso        -> --config c:\\temp\\lo_que_sea.json
    3. reposicion.json junto al ejecutable
    4. %APPDATA%\\Reposicion\\reposicion.json
    5. Asistente de primera ejecucion (lo dispara la UI si falta algo)

La cascada permite que UN MISMO BINARIO sirva llamado desde el ERP y tambien
abierto solo desde un acceso directo, sin recompilar ni mantener dos versiones.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

NOMBRE_CONFIG = "reposicion.json"


# ---------------------------------------------------------------------------

@dataclass
class Parametros:
    """Parametros de entorno + preferencias de calculo."""

    # --- Heredado del ERP (era PUBLIC en VFP) ---------------------------
    carpeta_datos: str = ""      # sis_path_
    carpeta_datos2: str = ""     # sis_path2
    sucursal: str = ""           # sis_sucurs
    carpeta_zip: str = ""        # zip_path_

    # --- Preferencias de calculo (eran controles del form) --------------
    punto_pedido: int = 7        # spnPunto   - pedir cuando queden menos de N dias
    cobertura: int = 45          # spnCober   - comprar stock para N dias
    criterio_mediana: bool = False   # optCriterio 1=promedio 2=mediana
    excluir_esporadicos: bool = True # chkExclEsporad
    # Ajusta la demanda segun la temporada (ver calculo.indice_estacional).
    # No existia en el formulario VFP.
    estacionalidad: bool = True
    negativo_como_cero: bool = False # chkNegCero
    catalogo_completo: bool = False  # chkCatalogoFull
    consolidar_sucursales: bool = False  # optSucursal 1=local 2=todas
    manual_sin_parametros: bool = False  # chkSinParam (solapa manual)
    modo: int = 2                # 1 = manual (min/max), 2 = rotacion

    # --- Tecnicas -------------------------------------------------------
    codepage: str = "auto"       # auto | cp1252 | cp850 | cp437 ...
    exact_off: bool = True       # semantica VFP del filtro de sucursal

    # De donde salio cada valor, para mostrarlo en la pantalla de ajustes
    origen: dict[str, str] = field(default_factory=dict)
    # True si hubo que reparar la linea de comandos (ver reparar_barra_final)
    argv_reparado: bool = False

    # -----------------------------------------------------------------

    @property
    def ruta_articulo(self) -> Path:
        return Path(self.carpeta_datos) / "articulo.dbf"

    @property
    def ruta_proveedo(self) -> Path:
        return Path(self.carpeta_datos) / "proveedo.dbf"

    @property
    def ruta_rotacion(self) -> Path:
        return Path(self.carpeta_datos) / "rotacion.dbf"

    @property
    def ruta_articulo_remoto(self) -> Path:
        return Path(self.carpeta_datos2) / "articulo.dbf"

    def validar(self) -> list[str]:
        """Devuelve la lista de problemas. Vacia = se puede arrancar.

        Se chequean los archivos, no solo las carpetas: el Load original
        hacia exactamente esto (IF NOT FILE(lcRuta) ... MESSAGEBOX) y es la
        diferencia entre un error claro al abrir y un error 'variable no
        encontrada' quince pantallas mas adelante.
        """
        problemas: list[str] = []

        if not self.carpeta_datos:
            problemas.append(
                "Falta la carpeta de datos principal (era sis_path_ en el ERP)."
            )
        elif not Path(self.carpeta_datos).is_dir():
            problemas.append(f"No existe la carpeta de datos: {self.carpeta_datos}")
        else:
            if not _existe_sin_distinguir(self.ruta_articulo):
                problemas.append(f"No se encontro ARTICULO.DBF en: {self.carpeta_datos}")
            if not _existe_sin_distinguir(self.ruta_proveedo):
                problemas.append(f"No se encontro PROVEEDO.DBF en: {self.carpeta_datos}")

        if not self.sucursal:
            problemas.append(
                "Falta el codigo de sucursal (era sis_sucurs en el ERP)."
            )

        return problemas

    def avisos(self) -> list[str]:
        """Problemas que NO impiden arrancar, pero desactivan funciones."""
        avisos: list[str] = []

        if self.carpeta_datos and not _existe_sin_distinguir(self.ruta_rotacion):
            avisos.append(
                "ROTACION.DBF no existe todavia: el modo Inteligente (rotacion) "
                "no va a poder calcular hasta que se genere."
            )

        if not self.carpeta_datos2:
            avisos.append(
                "No se configuro la carpeta de la otra sucursal (sis_path2): "
                "solo se puede analizar el stock local."
            )
        elif not _existe_sin_distinguir(self.ruta_articulo_remoto):
            avisos.append(
                f"No se encontro ARTICULO.DBF de la otra sucursal en: "
                f"{self.carpeta_datos2}"
            )

        return avisos

    def puede_consolidar(self) -> bool:
        """True si el stock de la otra sucursal esta realmente disponible."""
        return bool(self.carpeta_datos2) and _existe_sin_distinguir(
            self.ruta_articulo_remoto
        )

    # -----------------------------------------------------------------

    def a_dict(self) -> dict[str, Any]:
        datos = asdict(self)
        datos.pop("origen", None)
        datos.pop("argv_reparado", None)   # es de esta corrida, no se guarda
        return datos

    def guardar(self, ruta: Path | None = None) -> Path:
        """Persiste la configuracion. Por defecto en %APPDATA%, que siempre
        es escribible; la carpeta del ejecutable puede estar en un recurso
        de red de solo lectura."""
        destino = ruta or ruta_config_usuario()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(self.a_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return destino


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

def carpeta_ejecutable() -> Path:
    """Carpeta del .exe (o del fuente si corre sin empaquetar).

    sys.executable apunta al .exe cuando PyInstaller esta al mando;
    sys.frozen es la marca que deja el empaquetador.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def ruta_config_usuario() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return Path(base) / "Reposicion" / NOMBRE_CONFIG


def _existe_sin_distinguir(ruta: Path) -> bool:
    """FILE() de VFP no distingue mayusculas porque Windows tampoco.

    En Windows basta con exists(). Se agrega el barrido del directorio para
    que el mismo codigo sirva si las tablas viven en un recurso de red
    montado desde Linux, donde ARTICULO.DBF y articulo.dbf son dos archivos
    distintos.
    """
    if ruta.exists():
        return True
    carpeta = ruta.parent
    if not carpeta.is_dir():
        return False
    objetivo = ruta.name.lower()
    try:
        return any(h.name.lower() == objetivo for h in carpeta.iterdir())
    except OSError:
        return False


def resolver_archivo(ruta: Path) -> Path:
    """Devuelve la ruta con las mayusculas reales del disco."""
    if ruta.exists():
        return ruta
    carpeta = ruta.parent
    objetivo = ruta.name.lower()
    if carpeta.is_dir():
        for hijo in carpeta.iterdir():
            if hijo.name.lower() == objetivo:
                return hijo
    return ruta


# ---------------------------------------------------------------------------
# Cascada de resolucion
# ---------------------------------------------------------------------------

_CLAVES_ENTORNO = {
    "carpeta_datos": ("sis_path_", "REPOSICION_DATA"),
    "carpeta_datos2": ("sis_path2", "REPOSICION_DATA2"),
    "sucursal": ("sis_sucurs", "REPOSICION_SUCURSAL"),
    "carpeta_zip": ("zip_path_", "REPOSICION_ZIP"),
}


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reposicion",
        description="Centro de control de quiebres de stock.",
        epilog=(
            "Llamada tipica desde el ERP:\n"
            '  reposicion.exe --data "X:\\SISTEMA\\DATOS\\" '
            '--data2 "Y:\\SUC2\\DATOS\\" --sucursal "01"'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data", dest="carpeta_datos", help="sis_path_")
    parser.add_argument("--data2", dest="carpeta_datos2", help="sis_path2")
    parser.add_argument("--sucursal", dest="sucursal", help="sis_sucurs")
    parser.add_argument("--zip", dest="carpeta_zip", help="zip_path_")
    parser.add_argument(
        "--config",
        dest="config",
        help="Archivo JSON de traspaso escrito por el ERP.",
    )
    parser.add_argument(
        "--erp",
        dest="erp",
        help=(
            "Carpeta donde esta el CONFIG.DBF del sistema. De ahi se sacan "
            "solas las rutas y la sucursal."
        ),
    )
    parser.add_argument(
        "--sin-autodeteccion",
        action="store_true",
        help="No leer CONFIG.DBF para completar lo que falte.",
    )
    parser.add_argument(
        "--borrar-config",
        action="store_true",
        help="Borra el archivo de --config despues de leerlo.",
    )
    parser.add_argument("--codepage", dest="codepage", help="cp1252 | cp850 | auto")
    parser.add_argument(
        "--ajustes",
        action="store_true",
        help="Abre directamente la pantalla de configuracion.",
    )
    parser.add_argument(
        "--diagnostico",
        action="store_true",
        help=(
            "Revisa el entorno (tablas, campos, claves, permisos) y sale. "
            "No modifica nada."
        ),
    )
    return parser


def reparar_barra_final(argv: list[str]) -> tuple[list[str], bool]:
    """Deshace el destrozo que hace la barra final de Windows.

    EL PROBLEMA:
      sis_path_ viene de ADDBS(), asi que termina en barra: "S:\\". En la
      linea de comandos de Windows, una barra invertida justo antes de la
      comilla de cierre ESCAPA esa comilla:

          --data "S:\\" --sucursal "1" --data2 "X:\\"

      no se parte en cinco argumentos. El \\" del primero cuenta como una
      comilla literal, la cadena nunca se cierra, y el proceso recibe UN
      solo argumento con todo lo demas adentro:

          ['--data', 'S:" --sucursal 1 --data2 X:"']

      Consecuencia: la ruta llega rota y --sucursal y --data2 nunca se
      leen. El programa cree que no le pasaron nada y abre la pantalla de
      configuracion inicial, sin ninguna pista de por que.

    LA REPARACION:
      Cada comilla que quedo en el medio del argumento marca el lugar donde
      habia una barra final que Windows se comio. Se corta ahi, se le
      devuelve la barra al valor y lo que sigue se vuelve a separar en
      argumentos sueltos.

    El arreglo de verdad va en el lanzador (duplicar las barras finales
    antes de la comilla de cierre; ver integracion_vfp/opcion_de_menu.prg).
    Esto es la red por si queda algun lanzador viejo dando vueltas: mejor
    abrir bien y dejar constancia, que mandar al usuario a configurar a mano
    algo que el ERP ya sabia.

    LIMITE CONOCIDO: si la ruta tuviera espacios, la informacion se perdio
    en el destrozo y no hay forma de recuperarla con certeza. Por eso solo
    se repara cuando el patron es inequivoco (hay una comilla seguida de
    otro parametro con guiones).
    """
    if not any('" -' in arg for arg in argv):
        return argv, False

    reparados: list[str] = []
    for arg in argv:
        if '" -' not in arg:
            reparados.append(arg)
            continue

        partes = arg.split('"')
        for indice, parte in enumerate(partes):
            piezas = parte.split()
            if not piezas:
                continue
            if indice < len(partes) - 1:
                # Antes de cada comilla habia una barra final
                piezas[-1] = piezas[-1] + "\\"
            reparados.extend(piezas)

    return reparados, True


def cargar_parametros(argv: list[str] | None = None) -> tuple[Parametros, Any]:
    """Aplica la cascada completa y devuelve (parametros, argumentos_cli).

    Se recorre de MENOR a MAYOR prioridad y cada capa pisa a la anterior,
    anotando en `origen` de donde salio cada valor. Ese registro no es
    decorativo: cuando el .exe abre con las tablas equivocadas, lo primero
    que hay que saber es si las rutas vinieron del ERP o de un JSON viejo.
    """
    parser = construir_parser()

    crudos = list(sys.argv[1:] if argv is None else argv)
    crudos, se_reparo = reparar_barra_final(crudos)
    args = parser.parse_args(crudos)

    parametros = Parametros()
    parametros.argv_reparado = se_reparo
    campos_entorno = list(_CLAVES_ENTORNO.keys())

    # --- capa 4: %APPDATA% ---------------------------------------------
    _aplicar_json(parametros, ruta_config_usuario(), "config de usuario")

    # --- capa 3: junto al ejecutable ------------------------------------
    _aplicar_json(
        parametros, carpeta_ejecutable() / NOMBRE_CONFIG, "config junto al .exe"
    )

    # --- capa 2: archivo de traspaso ------------------------------------
    if args.config:
        traspaso = Path(args.config)
        _aplicar_json(parametros, traspaso, "archivo de traspaso")
        if args.borrar_config:
            try:
                traspaso.unlink()
            except OSError:
                pass

    # --- capa 1.5: variables de entorno ---------------------------------
    for campo, alias in _CLAVES_ENTORNO.items():
        for nombre in alias:
            valor = os.environ.get(nombre) or os.environ.get(nombre.upper())
            if valor:
                setattr(parametros, campo, valor.strip())
                parametros.origen[campo] = f"variable de entorno {nombre}"
                break

    # --- capa 1: linea de comandos --------------------------------------
    for campo in campos_entorno + ["codepage"]:
        valor = getattr(args, campo, None)
        if valor:
            setattr(parametros, campo, str(valor).strip())
            parametros.origen[campo] = "linea de comandos"

    _normalizar(parametros)

    # --- capa 0: CONFIG.DBF del ERP, solo para rellenar lo que falte -----
    # Va al final a proposito: no pisa nada de lo anterior. Ver el modulo
    # config_erp para por que esta capa existe.
    if not args.sin_autodeteccion:
        completar_desde_erp(parametros, args.erp)
        _normalizar(parametros)

    return parametros, args


def completar_desde_erp(
    parametros: Parametros, carpeta_erp: str | None = None, forzar: bool = False
) -> Any:
    """Rellena los valores vacios con lo que diga el CONFIG.DBF del sistema.

    Con `forzar` pisa tambien los que ya tenian valor: es lo que hace el
    boton "Detectar" de la pantalla de configuracion, donde el usuario pide
    explicitamente volver a tomar el entorno del ERP.
    """
    from .config_erp import detectar

    candidatas = [
        carpeta_erp,
        carpeta_ejecutable(),
        parametros.carpeta_datos,
    ]
    entorno = detectar([c for c in candidatas if c])
    if entorno is None:
        return None

    etiqueta = f"CONFIG.DBF ({entorno.ruta})"
    for campo, valor in entorno.valores.items():
        if forzar or not getattr(parametros, campo, ""):
            setattr(parametros, campo, valor)
            parametros.origen[campo] = etiqueta

    return entorno


def _aplicar_json(parametros: Parametros, ruta: Path, etiqueta: str) -> None:
    if not ruta or not ruta.is_file():
        return
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(datos, dict):
        return

    # Se aceptan tanto los nombres nuevos como los originales del ERP, para
    # que el ERP pueda escribir el JSON con la nomenclatura que ya conoce.
    equivalencias = {
        "sis_path_": "carpeta_datos",
        "sis_path2": "carpeta_datos2",
        "sis_sucurs": "sucursal",
        "zip_path_": "carpeta_zip",
        "data": "carpeta_datos",
        "data2": "carpeta_datos2",
    }

    validos = {f for f in Parametros.__dataclass_fields__ if f != "origen"}
    for clave, valor in datos.items():
        campo = equivalencias.get(clave, clave)
        if campo in validos and valor is not None:
            setattr(parametros, campo, valor)
            parametros.origen[campo] = etiqueta


def _normalizar(parametros: Parametros) -> None:
    """Limpia las rutas. ADDBS() de VFP agregaba la barra final; aca se
    normaliza con Path, que ademas arregla las barras mezcladas."""
    for campo in ("carpeta_datos", "carpeta_datos2", "carpeta_zip"):
        valor = str(getattr(parametros, campo) or "").strip().strip('"').strip()

        # Una unidad pelada NO es lo mismo que la raiz de esa unidad:
        # "S:" significa "el directorio actual de S:", que puede ser
        # cualquiera. "S:\" es la raiz. Si llego sin la barra (tipico
        # cuando el lanzador la saco para esquivar el problema del
        # escapado), se la devolvemos.
        if re.fullmatch(r"[A-Za-z]:", valor):
            valor += "\\"
        elif valor:
            valor = str(Path(valor))

        setattr(parametros, campo, valor)

    # ALLTRIM(sis_sucurs): el codigo viene de un campo C rellenado con espacios
    parametros.sucursal = str(parametros.sucursal or "").strip()

    parametros.punto_pedido = max(1, int(parametros.punto_pedido or 1))
    parametros.cobertura = max(1, int(parametros.cobertura or 1))
