"""
Modelos de las dos grillas.

Reemplazan al binding directo contra cursores de VFP (RecordSource,
ControlSource, SET KEY TO para el maestro-detalle) y a las expresiones
DynamicBackColor, que aca son un metodo de Python en vez de una cadena
evaluada fila por fila.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont

from ..calculo import MODO_ROTACION, Linea, Proveedor
from ..vfp import dtoc, transform_moneda
from . import estilo


class ModeloProveedores(QAbstractTableModel):
    """Ranking de proveedores. Es curProv."""

    COLUMNAS = ["Proveedor", "Items", "Crit.", "Monto Est."]
    ANCHOS = [None, 58, 58, 150]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filas: list[Proveedor] = []

    def fijar_datos(self, proveedores: list[Proveedor]) -> None:
        self.beginResetModel()
        self._filas = proveedores
        self.endResetModel()

    def proveedor(self, fila: int) -> Proveedor | None:
        if 0 <= fila < len(self._filas):
            return self._filas[fila]
        return None

    def fila_de(self, codigo: str) -> int:
        for indice, proveedor in enumerate(self._filas):
            if proveedor.codigo == codigo:
                return indice
        return -1

    def refrescar_fila(self, fila: int) -> None:
        if 0 <= fila < len(self._filas):
            self.dataChanged.emit(
                self.index(fila, 0), self.index(fila, len(self.COLUMNAS) - 1)
            )

    # -- Qt --------------------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._filas)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNAS)

    def headerData(self, seccion: int, orientacion, rol=Qt.DisplayRole) -> Any:
        if orientacion != Qt.Horizontal:
            return None
        if rol == Qt.DisplayRole:
            return self.COLUMNAS[seccion]
        if rol == Qt.TextAlignmentRole:
            # Qt ignora text-align en QHeaderView::section, hay que decirlo
            # desde el modelo o los titulos salen todos centrados.
            if seccion == 0:
                return int(Qt.AlignLeft | Qt.AlignVCenter)
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def data(self, indice: QModelIndex, rol=Qt.DisplayRole) -> Any:
        if not indice.isValid():
            return None
        proveedor = self._filas[indice.row()]
        columna = indice.column()

        if rol == Qt.DisplayRole:
            if columna == 0:
                return proveedor.nombre.strip()
            if columna == 1:
                return f"{proveedor.items:,}".replace(",", ".")
            if columna == 2:
                return f"{proveedor.criticos:,}".replace(",", ".")
            if columna == 3:
                return "$ " + transform_moneda(proveedor.monto)

        if rol == Qt.TextAlignmentRole:
            if columna == 0:
                return int(Qt.AlignLeft | Qt.AlignVCenter)
            return int(Qt.AlignRight | Qt.AlignVCenter)

        if rol == Qt.BackgroundRole:
            # Mismo criterio que el DynamicBackColor original:
            #   con algun articulo en cero o negativo -> rojo
            #   si no -> amarillo (llego al punto de pedido)
            if proveedor.criticos > 0:
                return QBrush(estilo.FILA_CRITICA)
            return QBrush(estilo.FILA_AVISO)

        if rol == Qt.ForegroundRole:
            if columna == 2 and proveedor.criticos > 0:
                return QBrush(estilo.TEXTO_CRITICO)
            return QBrush(estilo.TEXTO_NORMAL)

        if rol == Qt.FontRole and columna == 0:
            fuente = QFont()
            fuente.setBold(True)
            return fuente

        if rol == Qt.ToolTipRole:
            return (
                f"{proveedor.nombre.strip()}\n"
                f"Codigo: {proveedor.codigo}\n"
                f"{proveedor.items} articulos, {proveedor.criticos} sin stock\n"
                f"{proveedor.unidades:,.0f} unidades  -  "
                f"$ {transform_moneda(proveedor.monto)}"
            )

        return None


class ModeloDetalle(QAbstractTableModel):
    """Detalle de articulos del proveedor seleccionado. Es curQuiebre con el
    SET KEY TO aplicado."""

    cantidad_editada = Signal(object)   # Linea

    COL_CODIGO = 0
    COL_DESC = 1
    COL_UNIDAD = 2
    COL_PARAM1 = 3
    COL_PARAM2 = 4
    COL_STOCK_LOCAL = 5
    COL_STOCK_REMOTO = 6
    COL_PEDIR = 7
    COL_COSTO = 8
    COL_SUBTOTAL = 9
    COL_ULTIMA = 10
    COL_PEDIR_LOCAL = 11
    COL_PEDIR_REMOTO = 12

    ANCHOS = [84, 240, 38, 64, 66, 82, 82, 64, 100, 116, 54, 66, 66]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filas: list[Linea] = []
        self._modo = MODO_ROTACION
        self._consolidado = False
        self._mostrar_reparto = False

    def fijar_datos(
        self, lineas: list[Linea], modo: int, consolidado: bool,
        mostrar_reparto: bool = False,
    ) -> None:
        self.beginResetModel()
        self._filas = lineas
        self._modo = modo
        self._consolidado = consolidado
        self._mostrar_reparto = mostrar_reparto
        self.endResetModel()

    def linea(self, fila: int) -> Linea | None:
        if 0 <= fila < len(self._filas):
            return self._filas[fila]
        return None

    @property
    def lineas(self) -> list[Linea]:
        return self._filas

    def columnas_ocultas(self) -> list[int]:
        """El reparto entre depositos solo tiene sentido comprando para toda
        la empresa; en modo manual no hay datos de demanda para repartir."""
        ocultas = []
        if not self._consolidado:
            ocultas += [self.COL_STOCK_REMOTO]
        if self._modo != MODO_ROTACION:
            # En modo min/max no hay datos de ventas: la fecha de ultima
            # venta saldria vacia en todas las filas.
            ocultas += [self.COL_ULTIMA]
        if (
            not self._consolidado
            or self._modo != MODO_ROTACION
            or not self._mostrar_reparto
        ):
            ocultas += [self.COL_PEDIR_LOCAL, self.COL_PEDIR_REMOTO]
        return ocultas

    # -- Qt --------------------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._filas)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else 13

    def headerData(self, seccion: int, orientacion, rol=Qt.DisplayRole) -> Any:
        if orientacion != Qt.Horizontal:
            return None
        if rol == Qt.DisplayRole:
            # Las columnas 4 y 5 cambian de significado segun el modo, igual
            # que en AplicarModoGrilla del formulario original.
            if seccion == self.COL_PARAM1:
                return "Vta/mes" if self._modo == MODO_ROTACION else "Minimo"
            if seccion == self.COL_PARAM2:
                return "Dias stk" if self._modo == MODO_ROTACION else "Maximo"
            return [
                "Cod. Prov.", "Descripcion", "Und.", "", "", "Stock local",
                "Stock otra", "A pedir", "Costo", "Subtotal", "Ult. v.",
                "Pedir aca", "Pedir otra",
            ][seccion]
        if rol == Qt.TextAlignmentRole:
            if seccion in (self.COL_CODIGO, self.COL_DESC):
                return int(Qt.AlignLeft | Qt.AlignVCenter)
            if seccion == self.COL_UNIDAD:
                return int(Qt.AlignCenter)
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if rol == Qt.ToolTipRole and seccion == self.COL_PEDIR:
            return "Unica columna editable. Doble clic o F2 para cambiar."
        return None

    def flags(self, indice: QModelIndex):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if indice.column() == self.COL_PEDIR:
            return base | Qt.ItemIsEditable
        return base

    def data(self, indice: QModelIndex, rol=Qt.DisplayRole) -> Any:
        if not indice.isValid():
            return None
        linea = self._filas[indice.row()]
        columna = indice.column()

        if rol == Qt.DisplayRole:
            return self._texto(linea, columna)

        if rol == Qt.EditRole and columna == self.COL_PEDIR:
            return linea.cant_pedir

        if rol == Qt.TextAlignmentRole:
            if columna in (self.COL_CODIGO, self.COL_DESC):
                return int(Qt.AlignLeft | Qt.AlignVCenter)
            if columna == self.COL_UNIDAD:
                return int(Qt.AlignCenter)
            return int(Qt.AlignRight | Qt.AlignVCenter)

        if rol == Qt.BackgroundRole:
            if columna == self.COL_PEDIR:
                # VERDE no es un aviso: marca la columna que se puede editar
                return QBrush(
                    estilo.FILA_EDITADA if linea.modificada else estilo.FILA_EDITABLE
                )
            if linea.stock_total <= 0:
                return QBrush(estilo.FILA_CRITICA)
            if self._modo == MODO_ROTACION and linea.dias_stock < 7:
                return QBrush(estilo.FILA_URGENTE)
            return QBrush(estilo.FILA_AVISO)

        if rol == Qt.ForegroundRole:
            if columna in (self.COL_STOCK_LOCAL, self.COL_STOCK_REMOTO):
                valor = (
                    linea.stock_local
                    if columna == self.COL_STOCK_LOCAL
                    else linea.stock_remoto
                )
                if valor < 0:
                    return QBrush(estilo.TEXTO_CRITICO)
            if columna == self.COL_PEDIR:
                return QBrush(QColor(estilo.VERDE))
            if columna == self.COL_DESC:
                return QBrush(estilo.TEXTO_NORMAL)
            return QBrush(estilo.TEXTO_NUMERO)

        if rol == Qt.FontRole and columna == self.COL_PEDIR:
            fuente = QFont()
            fuente.setBold(True)
            return fuente

        if rol == Qt.ToolTipRole:
            return self._detalle(linea)

        return None

    def setData(self, indice: QModelIndex, valor: Any, rol=Qt.EditRole) -> bool:
        """Port de grdReposicion.Column8.Text1.Valid."""
        if rol != Qt.EditRole or indice.column() != self.COL_PEDIR:
            return False
        linea = self._filas[indice.row()]
        try:
            cantidad = float(str(valor).replace(",", "."))
        except (TypeError, ValueError):
            return False

        linea.fijar_cantidad(cantidad)
        self.dataChanged.emit(
            self.index(indice.row(), 0), self.index(indice.row(), 12)
        )
        self.cantidad_editada.emit(linea)
        return True

    # -- formato ----------------------------------------------------------

    def _texto(self, linea: Linea, columna: int) -> str:
        if columna == self.COL_CODIGO:
            return linea.cod_prov_articulo or linea.codigo
        if columna == self.COL_DESC:
            return linea.descripcion
        if columna == self.COL_UNIDAD:
            return linea.unidad
        if columna == self.COL_PARAM1:
            if self._modo == MODO_ROTACION:
                return f"{linea.vta_mes:,.2f}".replace(",", ".")
            return f"{linea.minimo:,.2f}".replace(",", ".")
        if columna == self.COL_PARAM2:
            if self._modo == MODO_ROTACION:
                return f"{linea.dias_stock:,.1f}".replace(",", ".")
            return f"{linea.maximo:,.2f}".replace(",", ".")
        if columna == self.COL_STOCK_LOCAL:
            return _cantidad(linea.stock_local)
        if columna == self.COL_STOCK_REMOTO:
            return _cantidad(linea.stock_remoto)
        if columna == self.COL_PEDIR:
            return _cantidad(linea.cant_pedir)
        if columna == self.COL_COSTO:
            return "$ " + transform_moneda(linea.costo)
        if columna == self.COL_SUBTOTAL:
            return "$ " + transform_moneda(linea.subtotal)
        if columna == self.COL_ULTIMA:
            texto = dtoc(linea.ultima_venta)
            return texto[:5] if texto else ""
        if columna == self.COL_PEDIR_LOCAL:
            return _cantidad(linea.pedir_local)
        if columna == self.COL_PEDIR_REMOTO:
            return _cantidad(linea.pedir_remoto)
        return ""

    def _detalle(self, linea: Linea) -> str:
        partes = [linea.descripcion]
        if linea.marca:
            partes.append(f"Marca: {linea.marca}")
        partes.append(
            f"Codigo interno: {linea.codigo}   "
            f"Cod. proveedor: {linea.cod_prov_articulo}"
        )
        if linea.ubicacion:
            partes.append(f"Ubicacion en deposito: {linea.ubicacion}")
        partes.append(f"Stock local: {linea.stock_local:,.2f}")
        if self._consolidado:
            partes.append(f"Stock otra sucursal: {linea.stock_remoto:,.2f}")
            partes.append(
                f"Reparto sugerido: {linea.pedir_local:,.0f} aca / "
                f"{linea.pedir_remoto:,.0f} en la otra"
            )
        if self._modo == MODO_ROTACION:
            partes.append(
                f"Venta mensual: {linea.vta_mes:,.2f}  "
                f"({linea.vta_mes / 30:,.3f} por dia)"
            )
            partes.append(f"Dias de stock: {linea.dias_stock:,.1f}")
        if linea.modificada:
            partes.append(
                f"Cantidad modificada a mano "
                f"(el sistema sugeria {linea.sugerido_original:,.0f})"
            )
        return "\n".join(partes)


def _cantidad(valor: float) -> str:
    """Cantidades sin decimales cuando son enteras, con dos cuando no."""
    if abs(valor - round(valor)) < 1e-9:
        return f"{int(round(valor)):,}".replace(",", ".")
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
