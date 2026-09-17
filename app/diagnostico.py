"""
Diagnostico del entorno real, para la puesta en marcha.

    reposicion.exe --diagnostico

Recorre todo lo que el programa necesita y arma un informe: que tablas
encontro, con que codificacion, si los campos estan, si las claves
enganchan, si va a poder escribir ROTACION.DBF y como queda el embudo de
descartes. No modifica NADA.

POR QUE EXISTE:
  Al instalarlo en un servidor de verdad, lo que falla no es la logica
  —eso ya esta probado— sino el entorno: una ruta que apunta a otro lado,
  un codepage que rompe los acentos, una tabla sin permisos de escritura,
  un campo que en esta instalacion se llama distinto. Todo eso da sintomas
  confusos si aparece con la aplicacion abierta: una lista vacia, nombres
  raros, un boton que no hace nada.

  Este modo los pone a todos sobre la mesa de una sola pasada, antes de
  que nadie use el programa.
"""

from __future__ import annotations

import datetime
import os
import tempfile
from pathlib import Path
from typing import Any

from .calculo import MODO_ROTACION, MotorReposicion
from .config import Parametros, resolver_archivo
from .dbf import ErrorDBF, TablaDBF
from .datos import CAMPOS_ARTICULO, CAMPOS_ROTACION, RepositorioERP
from .vfp import alltrim, transform_moneda

OK = "[ OK ]"
AVISO = "[AVISO]"
ERROR = "[ERROR]"

# Campos sin los cuales el programa directamente no funciona.
IMPRESCINDIBLES_ARTICULO = [
    "AR_SUCU", "AR_CODI", "AR_DESC", "AR_PROV", "AR_CANT", "AR_COST", "AR_ACTIVO",
]
CAMPOS_DOCUM = [
    "DOC_CLAVE_", "DOC_FECEMI", "DOC_TIPDOC", "DOC_SUCURS", "DOC_CLIPRO",
    "DOC_ANULED",
]
CAMPOS_DOCCUER = ["DCC_CLAVE_", "DCC_ARTICU", "DCC_CANTID"]


def _miles(numero: Any) -> str:
    """Separador de miles argentino.

    Se hace sobre el numero y no con un .replace() sobre la frase entera:
    esa version tambien se comia las comas del texto que la rodeaba y
    dejaba cosas como "32.938 registros. 25 campos".
    """
    return f"{int(numero):,}".replace(",", ".")


class Diagnostico:
    def __init__(self, parametros: Parametros):
        self.p = parametros
        self.lineas: list[str] = []
        self.problemas = 0
        self.avisos = 0

    # -- salida ----------------------------------------------------------

    def _txt(self, texto: str = "") -> None:
        self.lineas.append(texto)

    def _titulo(self, texto: str) -> None:
        self._txt()
        self._txt(texto)
        self._txt("-" * 72)

    def _ok(self, texto: str) -> None:
        self._txt(f"  {OK}  {texto}")

    def _aviso(self, texto: str) -> None:
        self.avisos += 1
        self._txt(f"  {AVISO} {texto}")

    def _error(self, texto: str) -> None:
        self.problemas += 1
        self._txt(f"  {ERROR} {texto}")

    def texto(self) -> str:
        return "\n".join(self.lineas)

    # -- corrida ---------------------------------------------------------

    def correr(self) -> str:
        self._txt("=" * 72)
        self._txt("DIAGNOSTICO DEL ENTORNO")
        self._txt(datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        self._txt("=" * 72)

        self._parametros()
        catalogo = self._tablas()
        if catalogo is not None:
            self._proveedores(catalogo)
            self._acentos(catalogo)
            self._corrida(catalogo)
        self._comprobantes()
        self._escritura()
        self._cierre()
        return self.texto()

    # -- 1. parametros ---------------------------------------------------

    def _parametros(self) -> None:
        self._titulo("1. PARAMETROS DEL ENTORNO")
        campos = [
            ("carpeta_datos", "sis_path_", True),
            ("carpeta_datos2", "sis_path2", False),
            ("carpeta_zip", "zip_path_", False),
            ("sucursal", "sis_sucurs", True),
        ]
        for campo, original, obligatorio in campos:
            valor = getattr(self.p, campo, "")
            origen = self.p.origen.get(campo, "no configurado")
            if valor:
                self._ok(f"{original:<12} = {valor}")
                self._txt(f"          (de: {origen})")
            elif obligatorio:
                self._error(f"{original:<12} = SIN CONFIGURAR")
            else:
                self._aviso(
                    f"{original:<12} = vacio  "
                    + ("(sin analisis de la otra sucursal)"
                       if campo == "carpeta_datos2"
                       else "(sin el pendrive en el recalculo)")
                )

        self._txt(f"        codepage     = {self.p.codepage}")

        if getattr(self.p, "argv_reparado", False):
            self._txt()
            self._aviso(
                "La linea de comandos llego rota y hubo que repararla."
            )
            self._txt(
                "          El lanzador esta pasando las rutas con la barra "
                "final pegada a la comilla de cierre, y Windows la usa para"
            )
            self._txt(
                "          escapar esa comilla. El programa lo corrigio solo, "
                "pero conviene actualizar el lanzador del ERP con la"
            )
            self._txt(
                "          version de integracion_vfp/opcion_de_menu.prg, que "
                "duplica las barras finales."
            )

    # -- 2. tablas -------------------------------------------------------

    def _tablas(self) -> Any:
        self._titulo("2. TABLAS DEL SISTEMA")

        articulo = self._revisar_tabla(
            self.p.ruta_articulo, "ARTICULO.DBF",
            IMPRESCINDIBLES_ARTICULO, CAMPOS_ARTICULO,
        )
        if articulo is None:
            self._error("Sin ARTICULO.DBF no se puede seguir.")
            return None

        self._revisar_tabla(self.p.ruta_proveedo, "PROVEEDO.DBF", ["PR_NOMBRE"], [])

        if resolver_archivo(self.p.ruta_rotacion).is_file():
            self._revisar_tabla(
                self.p.ruta_rotacion, "ROTACION.DBF",
                ["ROT_ARTIC", "ROT_ORIGE", "ROT_DESDE", "ROT_HASTA", "ROT_MESES"],
                CAMPOS_ROTACION,
            )
        else:
            self._aviso(
                "ROTACION.DBF todavia no existe. El modo Inteligente no va a "
                "funcionar hasta correr Recalcular rotacion."
            )

        if self.p.carpeta_datos2:
            self._revisar_tabla(
                self.p.ruta_articulo_remoto, "ARTICULO.DBF (otra sucursal)",
                ["AR_SUCU", "AR_CODI", "AR_CANT"], [],
            )

        self._titulo("3. LECTURA DEL CATALOGO")
        try:
            catalogo = RepositorioERP(self.p).cargar(
                con_remoto=bool(self.p.carpeta_datos2),
                con_rotacion=True,
            )
        except Exception as error:
            self._error(f"No se pudo leer el catalogo: {error}")
            return None

        for linea in catalogo.diagnostico:
            self._txt(f"        {linea}")

        total = catalogo.total_catalogo
        activos = len(catalogo.articulos)
        self._txt()
        if activos == 0:
            self._error(
                f"De {_miles(total)} articulos del catalogo, NINGUNO paso el filtro."
            )
            self._txt(
                f"          El filtro es AR_ACTIVO = 'S' y AR_SUCU que empiece "
                f"con '{alltrim(self.p.sucursal)}'."
            )
            self._txt("          Revisar el codigo de sucursal.")
        else:
            porcentaje = activos / total * 100 if total else 0
            self._ok(
                f"{_miles(activos)} de {_miles(total)} articulos activos en la "
                f"sucursal {alltrim(self.p.sucursal)} ({porcentaje:.1f}%)"
            )
            if porcentaje < 5:
                self._aviso(
                    "Es un porcentaje muy bajo. Verificar el codigo de sucursal."
                )

        tiempos = " + ".join(f"{k} {v:.2f}s" for k, v in catalogo.tiempos.items())
        self._txt(f"        tiempos: {tiempos}")
        return catalogo

    def _revisar_tabla(
        self, ruta: Path, etiqueta: str, imprescindibles: list[str],
        deseables: list[str],
    ) -> TablaDBF | None:
        real = resolver_archivo(ruta)
        if not real.is_file():
            self._error(f"{etiqueta}: no se encontro en {ruta.parent}")
            return None

        try:
            tabla = TablaDBF(real, codepage=self.p.codepage)
        except ErrorDBF as error:
            self._error(f"{etiqueta}: {error}")
            return None

        with tabla:
            tamanio = real.stat().st_size / 1_048_576
            self._ok(
                f"{etiqueta}: {_miles(tabla.cantidad_registros)} registros, "
                f"{len(tabla.campos)} campos, {tamanio:.1f} MB"
            )
            self._txt(
                f"          codepage {tabla.codepage} ({tabla.codepage_origen})"
            )
            if tabla.cantidad_registros == 0:
                self._aviso(f"{etiqueta} esta vacia.")

            faltan = [c for c in imprescindibles if not tabla.tiene(c)]
            if faltan:
                self._error(
                    f"{etiqueta}: faltan campos necesarios: {', '.join(faltan)}"
                )
                self._txt(f"          Campos presentes: {', '.join(tabla.nombres)}")

            opcionales = [
                c for c in deseables
                if c not in imprescindibles and not tabla.tiene(c)
            ]
            if opcionales:
                self._aviso(
                    f"{etiqueta}: sin {', '.join(opcionales)} (se asumen vacios)"
                )
            return tabla

    # -- 4. proveedores --------------------------------------------------

    def _proveedores(self, catalogo: Any) -> None:
        self._titulo("4. CRUCE CON PROVEEDO")

        if not catalogo.proveedores:
            self._error(
                "No se leyo ningun proveedor. Los articulos van a aparecer "
                "agrupados por codigo, sin nombre."
            )
            return

        from .datos import nombre_proveedor, normalizar_proveedor

        codigos = {
            normalizar_proveedor(a.cod_proveedor_bruto) for a in catalogo.articulos
        }
        codigos.discard("*SINPRO")

        sin_resolver = [
            c for c in codigos
            if "no esta en PROVEEDO" in nombre_proveedor(
                c, catalogo.proveedores, catalogo.proveedores_respaldo
            )
        ]
        sin_proveedor = sum(
            1 for a in catalogo.articulos
            if normalizar_proveedor(a.cod_proveedor_bruto) == "*SINPRO"
        )

        resueltos = len(codigos) - len(sin_resolver)
        if not sin_resolver:
            self._ok(
                f"Los {len(codigos)} codigos de proveedor del catalogo "
                f"engancharon con PROVEEDO."
            )
        else:
            porcentaje = resueltos / len(codigos) * 100 if codigos else 0
            metodo = self._aviso if porcentaje >= 80 else self._error
            metodo(
                f"{len(sin_resolver)} de {len(codigos)} codigos de proveedor "
                f"NO engancharon ({porcentaje:.0f}% resuelto)."
            )
            self._txt("          Ejemplos sin resolver: " + ", ".join(
                f"[{c}]" for c in sorted(sin_resolver)[:6]
            ))
            self._txt("          Claves leidas de PROVEEDO: " + ", ".join(
                f"[{c}]" for c in sorted(catalogo.proveedores)[:6]
            ))

        if sin_proveedor:
            self._txt(
                f"        {_miles(sin_proveedor)} articulos sin proveedor "
                f"cargado en la ficha (grupo 'sin proveedor asignado')."
            )

    # -- 5. acentos ------------------------------------------------------

    def _acentos(self, catalogo: Any) -> None:
        self._titulo("5. CODIFICACION DE TEXTOS")
        self._txt("        Descripciones con enie o acento, para revisar a ojo:")
        self._txt()

        muestras = [
            a.descripcion for a in catalogo.articulos
            if any(c in a.descripcion for c in "ÑñÁÉÍÓÚáéíóúÜü")
        ]
        raros = [
            a.descripcion for a in catalogo.articulos
            if any(c in a.descripcion for c in "����")
        ]

        if not muestras and not raros:
            self._aviso(
                "No se encontro ninguna descripcion con enie ni acentos. "
                "Puede ser normal, o senial de que el codepage esta mal."
            )
        for texto in muestras[:6]:
            self._txt(f"          {texto[:64]}")

        if raros:
            self._error(
                f"{len(raros)} descripciones traen caracteres rotos. "
                f"Probar con --codepage cp850."
            )
            for texto in raros[:3]:
                self._txt(f"          {texto[:64]}")
        elif muestras:
            self._ok(
                "Si esas lineas se leen bien, el codepage "
                f"({catalogo.codepage}) es el correcto."
            )

    # -- 6. corrida ------------------------------------------------------

    def _corrida(self, catalogo: Any) -> None:
        self._titulo("6. CORRIDA DE PRUEBA (modo Inteligente)")

        if not catalogo.info_rotacion.disponible:
            self._aviso(
                "Sin ROTACION.DBF utilizable: "
                + (catalogo.info_rotacion.mensaje or "no disponible")
            )
            self._txt("        Correr Recalcular rotacion antes de usar el programa.")
            return

        resultado = MotorReposicion(self.p, catalogo).calcular(
            MODO_ROTACION, bool(catalogo.remoto_disponible)
        )
        d = resultado.diagnostico

        total_enganche = d.enganche_clave_completa + d.enganche_clave_corta
        if total_enganche == 0:
            self._error(
                "NINGUN articulo engancho contra ROTACION.DBF. "
                "La lista de compra va a salir vacia."
            )
            self._txt(
                "          Suele significar que DCC_ARTICU no guarda la misma "
                "clave que AR_SUCU + AR_CODI."
            )
        else:
            porcentaje = total_enganche / max(d.analizados, 1) * 100
            forma = (
                "clave completa (AR_SUCU + AR_CODI)"
                if d.enganche_clave_completa >= d.enganche_clave_corta
                else "codigo solo, sin prefijo de sucursal"
            )
            metodo = self._ok if porcentaje >= 30 else self._aviso
            metodo(
                f"{_miles(total_enganche)} articulos con ventas registradas "
                f"({porcentaje:.0f}% del catalogo activo), por {forma}."
            )

        self._txt()
        self._txt(f"        Catalogo total ............ {_miles(d.total_catalogo):>8}")
        self._txt(f"        Analizados ................ {_miles(d.analizados):>8}")
        self._txt(f"          - sin ventas ............ {_miles(d.desc_sin_venta):>8}")
        self._txt(f"          - sin demanda ........... {_miles(d.desc_sin_demanda):>8}")
        self._txt(f"          - esporadicos ........... {_miles(d.desc_esporadico):>8}")
        self._txt(f"          - stock suficiente ...... {_miles(d.desc_stock_ok):>8}")
        self._txt(f"          - cobertura cubierta .... {_miles(d.desc_cubierto):>8}")
        self._txt(f"        SUGERIDOS ................. {_miles(d.sugeridos):>8}")
        self._txt(f"          con stock negativo ...... {_miles(d.negativos):>8}")
        self._txt()

        if resultado.ok:
            proveedores, items, monto = resultado.total_general()
            self._ok(
                f"{proveedores} proveedores, {items} articulos, "
                f"$ {transform_moneda(monto)}"
            )
            self._txt()
            self._txt("        Primeros proveedores:")
            for prov in resultado.proveedores[:5]:
                self._txt(
                    f"          {prov.nombre.strip()[:40]:<42}"
                    f"{prov.items:>5} items   $ {transform_moneda(prov.monto):>18}"
                )
        else:
            self._aviso(
                "La corrida no devolvio articulos: "
                + resultado.mensaje.split("\n")[0]
            )

    # -- 7. comprobantes -------------------------------------------------

    def _comprobantes(self) -> None:
        self._titulo("7. COMPROBANTES (para Recalcular rotacion)")

        fuentes = [
            ("Blanco local", self.p.carpeta_datos, True),
            ("Otra sucursal", self.p.carpeta_datos2, False),
            ("Pendrive", self.p.carpeta_zip, False),
        ]
        for etiqueta, carpeta, obligatoria in fuentes:
            if not carpeta:
                if obligatoria:
                    self._error(f"{etiqueta}: sin carpeta configurada")
                continue

            docum = resolver_archivo(Path(carpeta) / "DOCUM.DBF")
            doccuer = resolver_archivo(Path(carpeta) / "DOCCUER.DBF")

            if not docum.is_file() or not doccuer.is_file():
                metodo = self._error if obligatoria else self._aviso
                metodo(f"{etiqueta}: faltan DOCUM.DBF o DOCCUER.DBF en {carpeta}")
                continue

            try:
                with TablaDBF(docum, codepage=self.p.codepage) as t1, \
                     TablaDBF(doccuer, codepage=self.p.codepage) as t2:
                    self._ok(
                        f"{etiqueta}: DOCUM {_miles(t1.cantidad_registros)} / "
                        f"DOCCUER {_miles(t2.cantidad_registros)}"
                    )
                    faltan = [c for c in CAMPOS_DOCUM if not t1.tiene(c)]
                    if faltan:
                        self._error(
                            f"{etiqueta}: DOCUM sin {', '.join(faltan)}"
                        )
                    faltan = [c for c in CAMPOS_DOCCUER if not t2.tiene(c)]
                    if faltan:
                        self._error(
                            f"{etiqueta}: DOCCUER sin {', '.join(faltan)}"
                        )
            except ErrorDBF as error:
                self._error(f"{etiqueta}: {error}")

    # -- 8. escritura ----------------------------------------------------

    def _escritura(self) -> None:
        self._titulo("8. PERMISOS DE ESCRITURA")
        self._txt("        Solo se toca ROTACION.DBF, y solo al recalcular.")
        self._txt()

        carpeta = Path(self.p.carpeta_datos)
        try:
            descriptor, ruta = tempfile.mkstemp(
                prefix="_prueba_", suffix=".tmp", dir=str(carpeta)
            )
            os.close(descriptor)
            os.unlink(ruta)
            self._ok(f"Se puede escribir en {carpeta}")
        except OSError as error:
            self._error(
                f"NO se puede escribir en {carpeta}: {error}\n"
                f"          Recalcular rotacion va a fallar. Hay que dar "
                f"permiso de escritura sobre esa carpeta."
            )

        rotacion = resolver_archivo(self.p.ruta_rotacion)
        if rotacion.is_file():
            try:
                with open(rotacion, "r+b"):
                    pass
                self._ok("ROTACION.DBF no esta bloqueada por otro puesto.")
            except OSError:
                self._aviso(
                    "ROTACION.DBF esta abierta por otro programa. El recalculo "
                    "no va a poder reemplazarla hasta que se cierre."
                )

        cdx = rotacion.with_suffix(".CDX")
        if cdx.is_file():
            self._txt(
                "        Hay un ROTACION.CDX: el recalculo lo borra, porque "
                "quedaria apuntando a registros que ya no existen."
            )

    # -- cierre ----------------------------------------------------------

    def _cierre(self) -> None:
        self._titulo("RESUMEN")
        if self.problemas:
            self._txt(
                f"  {self.problemas} problema(s) que hay que resolver antes de "
                f"poner el programa en produccion."
            )
        if self.avisos:
            self._txt(f"  {self.avisos} aviso(s): revisar, pero no bloquean.")
        if not self.problemas and not self.avisos:
            self._txt("  Todo en orden. El entorno esta listo.")
        elif not self.problemas:
            self._txt("  Sin problemas bloqueantes: el programa puede usarse.")
        self._txt()


def correr_diagnostico(parametros: Parametros) -> tuple[str, int]:
    """Devuelve (informe, cantidad_de_problemas)."""
    diagnostico = Diagnostico(parametros)
    texto = diagnostico.correr()
    return texto, diagnostico.problemas
