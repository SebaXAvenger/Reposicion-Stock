"""
Ayuda en pantalla.

El texto viene del formulario original (AyudaPagina1..4), donde estaba armado
a mano con AddObject de shapes y editbox deshabilitados. Se conserva palabra
por palabra: lo escribio quien conoce el negocio y explica cosas que el
programa no puede deducir solo, como que un stock negativo casi siempre es
un error de carga y no una compra pendiente.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from . import estilo

AZUL, VERDE, AMBAR, ROJO = estilo.AZUL, estilo.VERDE, estilo.AMBAR, estilo.ROJO

PAGINAS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Para que sirve", [
        (AZUL, "El problema que resuelve",
         "Antes, para saber que comprar habia que recorrer el deposito, mirar "
         "fichas una por una y acordarse de memoria que se vende y que no.\n\n"
         "Esta pantalla lo hace sola: recorre todo el catalogo, cruza el stock "
         "que hay hoy contra lo que se vendio de verdad, y arma la lista de "
         "compra ya separada por proveedor."),
        (VERDE, "Se usa en tres pasos",
         "1.  Abrir la pantalla. A la izquierda aparecen los proveedores a los "
         "que hay que comprarle hoy, ordenados por monto.\n\n"
         "2.  Hacer clic en un proveedor. A la derecha se llena solo con sus "
         "articulos faltantes y la cantidad sugerida ya calculada.\n\n"
         "3.  Ajustar e imprimir. Si el presupuesto no alcanza se baja alguna "
         "cantidad a mano y se exporta el pedido."),
        (AMBAR, "Las dos solapas de arriba",
         "Manual (min/max):  usa el stock minimo y maximo cargado en la ficha "
         "de cada articulo. Si casi ningun articulo los tiene cargados, esta "
         "solapa se va a ver practicamente vacia. Queda disponible por si "
         "algun dia se completan.\n\n"
         "Inteligente (rotacion):  no necesita que nadie cargue nada. Mira "
         "cuanto se vendio realmente de cada articulo y calcula solo cuanto "
         "hace falta. Es la que conviene usar."),
        (AZUL, "No inventa ningun numero",
         "Todo lo que ve en pantalla sale de las tablas del propio sistema:\n\n"
         "-  El stock, de la ficha del articulo.\n"
         "-  Las ventas, de los comprobantes ya emitidos.\n"
         "-  El costo, del precio de costo cargado en la ficha.\n\n"
         "Si un numero le llama la atencion, se puede rastrear hasta el "
         "comprobante que lo genero."),
        (VERDE, "Sucursal local  /  Todas las sucursales",
         "Arriba a la derecha se elige si mirar solo el stock de esta sucursal "
         "o sumar tambien el de la otra.\n\n"
         "Si un articulo falta aca pero sobra en el otro deposito, con la "
         "opcion Todas las Sucursales deja de aparecer como faltante. Tiene "
         "sentido: primero conviene trasladarlo antes que comprarlo de nuevo."),
        (ROJO, "El boton Actualizar (F5)",
         "Cada vez que se cambia un parametro la pantalla recalcula sola, no "
         "hace falta apretar nada.\n\n"
         "El boton Actualizar, o la tecla F5, fuerza una relectura completa "
         "del stock. Sirve cuando alguien facturo o recibio mercaderia "
         "mientras esta pantalla estaba abierta."),
    ]),
    ("La pantalla", [
        (AZUL, "Panel izquierdo:  los proveedores",
         "Cada fila es un proveedor al que hay algo para comprarle. Esta "
         "ordenado de mayor a menor monto, asi que los de arriba son los que "
         "mas plata representan.\n\n"
         "Si un articulo no tiene proveedor cargado en su ficha, aparece "
         "agrupado como (sin proveedor asignado)."),
        (AMBAR, "Columnas del panel izquierdo",
         "Proveedor:  nombre segun la ficha de proveedores.\n"
         "Items:  cuantos articulos distintos hay que pedirle.\n"
         "Crit.:  cuantos de esos estan en cero o en negativo.\n"
         "Monto est.:  cuanto costaria el pedido completo, a precio de costo."),
        (VERDE, "Panel derecho:  que significa cada columna",
         "Cod. Prov. / Descripcion / Und.:  identificacion del articulo. El "
         "codigo que se muestra es el DEL PROVEEDOR, que es el que se dicta al "
         "hacer el pedido.\n"
         "Vta/mes:  cuantas unidades se venden por mes, en promedio.\n"
         "Dias stk:  cuantos dias de venta cubre el stock que queda hoy.\n"
         "Stock Local:  lo que hay en el deposito de esta sucursal.\n"
         "Stock Suc.:  lo que hay en el otro deposito. Solo se completa si "
         "arriba se eligio Todas las Sucursales.\n"
         "A Pedir:  la sugerencia del sistema. Va sobre fondo verde porque es "
         "el unico casillero que se puede escribir.\n"
         "Costo:  precio de costo unitario.\n"
         "Subtotal:  lo que sale esa linea del pedido.\n"
         "Ult. v.:  cuando se vendio por ultima vez.\n\n"
         "En la solapa manual, Vta/mes y Dias stk se reemplazan por Minimo y "
         "Maximo."),
        (ROJO, "Que significan los colores",
         "ROJO:  el stock esta en cero o en negativo. Se estan perdiendo "
         "ventas en este momento.\n\n"
         "NARANJA:  quedan menos de 7 dias de stock. Urgente.\n\n"
         "AMARILLO:  llego al punto de pedido, pero todavia hay margen.\n\n"
         "VERDE:  no es un aviso. Marca la columna que se puede editar."),
        (AZUL, "Los totales de abajo",
         "Unidades a pedir y Monto estimado corresponden unicamente al "
         "proveedor seleccionado, y se actualizan al instante si se cambia una "
         "cantidad a mano.\n\n"
         "Las tarjetas del encabezado muestran el total de todos los "
         "proveedores juntos."),
        (ROJO, "Cuidado:  rojo no siempre quiere decir comprar",
         "Un stock negativo es imposible en la realidad: significa que se "
         "vendio mas de lo que figura que entro, casi siempre por mercaderia "
         "recibida y nunca cargada.\n\n"
         "Si un articulo aparece en rojo pero en el deposito hay mercaderia, "
         "el problema esta en el inventario, no en la compra. Conviene "
         "corregir la ficha antes de pedirle nada al proveedor.\n\n"
         "Al ordenarse por monto, estos casos suelen quedar arriba de todo y "
         "distorsionan el total estimado. La opcion Tratar stock negativo "
         "como cero los saca de la cuenta."),
    ]),
    ("Los parametros", [
        (AZUL, "Pedir cuando queden menos de  X  dias",
         "Es el disparador. Mientras el stock alcance para mas de X dias, el "
         "articulo no aparece en la lista.\n\n"
         "Sirve para no estar pidiendo todos los dias de a poquito.\n\n"
         "Valor sugerido:  15 dias. O el tiempo que tarda ese proveedor en "
         "entregar, mas unos dias de colchon."),
        (VERDE, "Comprar stock para  Y  dias",
         "Es cuanto se compra, una vez que se decidio comprar.\n\n"
         "Valor sugerido:  45 dias, si a ese proveedor se le compra una vez "
         "por mes.\n\n"
         "Y siempre tiene que ser mayor que X. Si fueran iguales, cada compra "
         "dejaria el stock justo en el punto de pedido y habria que volver a "
         "comprar al dia siguiente."),
        (AMBAR, "Ejemplo con numeros reales",
         "Alicate cortaperno 18 pulgadas. Se venden 6 por mes, o sea 0,2 por "
         "dia. Quedan 2 en el deposito.\n\n"
         "Dias de stock  =  2  /  0,2  =  10 dias\n"
         "Como 10 es menor que el punto de pedido (15), aparece en la lista.\n\n"
         "Objetivo  =  0,2  x  45 dias  =  9 unidades\n"
         "Sugerido  =  9  -  2  =  7 unidades\n\n"
         "Si la cobertura se sube a 60 dias, el objetivo pasa a 12 y sugiere 10."),
        (AZUL, "Promedio  o  Mediana",
         "Promedio:  suma todo lo vendido y lo divide por los meses. Es "
         "simple, pero si hubo una venta grande de una sola vez (una obra, por "
         "ejemplo) infla el numero para siempre.\n\n"
         "Mediana:  toma el mes del medio. Un articulo que vendio 200 unidades "
         "una vez y nada mas tiene mediana cero, asi que no se sugiere.\n\n"
         "Empezar con Promedio. Si las cantidades salen exageradas, pasar a "
         "Mediana."),
        (VERDE, "Excluir articulos que vendieron en un solo mes",
         "Deja afuera los articulos que tuvieron movimiento en un unico mes de "
         "los doce analizados.\n\n"
         "Casi siempre son pedidos especiales de un cliente puntual, no "
         "mercaderia de reposicion. Comprarlos por las dudas es plata "
         "inmovilizada.\n\n"
         "Conviene dejarlo activado."),
        (AMBAR, "El boton Recalcular rotacion",
         "El analisis de ventas se guarda ya calculado en una tabla aparte "
         "(ROTACION.DBF), para que esta pantalla abra rapido.\n\n"
         "Ese boton la vuelve a generar leyendo todo el historial de "
         "comprobantes de las tres bases: la local, la de la otra sucursal y "
         "el pendrive. Conviene que nadie mas tenga esta pantalla abierta: si "
         "otro puesto tiene la tabla tomada, no se puede reemplazar y la "
         "vieja queda intacta.\n\n"
         "Alcanza con hacerlo una vez por semana. No hace falta todos los "
         "dias: el stock se lee siempre fresco, lo unico que envejece es el "
         "promedio de ventas."),
    ]),
    ("En la practica", [
        (VERDE, "Un lunes a la manana, paso a paso",
         "1.  Se abre la pantalla. Arriba dice:  38 proveedores a comprar, 412 "
         "articulos, compra total estimada $ 8.400.000.\n\n"
         "2.  A la izquierda encabeza Bulonfer S.A. con 34 items y $ 960.000, "
         "de los cuales 12 estan sin stock.\n\n"
         "3.  Se hace clic en Bulonfer. A la derecha aparecen sus 34 articulos "
         "con la cantidad sugerida ya puesta.\n\n"
         "4.  El primero sugiere 40 unidades y parece mucho. Se mira la "
         "columna Vta/mes: dice 8 por mes, y la cobertura esta en 45 dias. El "
         "numero cierra.\n\n"
         "5.  El presupuesto no da para $ 960.000. Se bajan a mano las "
         "cantidades de tres articulos caros y el Monto estimado de abajo baja "
         "solo.\n\n"
         "6.  Se aprieta Exportar a Excel y el pedido queda listo para mandar."),
        (AZUL, "De donde salen las ventas del calculo",
         "Cuentan como salida de mercaderia:  facturas (FC y FE) y notas de "
         "debito (ND, DE).\n\n"
         "Se restan del consumo:  notas de credito y devoluciones (NC, CE).\n\n"
         "Los remitos internos (RI) quedan afuera por defecto: mueven "
         "mercaderia de un deposito al otro, pero no son una venta. Se pueden "
         "incluir desde la pantalla de Recalcular rotacion.\n\n"
         "No cuentan:  presupuestos, pedidos, notas de venta y cualquier "
         "comprobante anulado.\n\n"
         "Se toman en cuenta los comprobantes de las dos bases del sistema, no "
         "solamente los de la base principal.\n\n"
         "La ventana analizada son los ultimos 12 meses completos. El mes en "
         "curso queda afuera a proposito: al estar a la mitad, bajaria el "
         "promedio."),
        (ROJO, "Lo que el sistema NO sabe",
         "No sabe que se le pidio ayer al proveedor y todavia no llego. El "
         "sistema no registra pedidos pendientes en ningun lado.\n\n"
         "Consecuencia practica:  si hoy se compra y manana se vuelve a abrir "
         "esta pantalla, va a sugerir lo mismo otra vez, hasta que la "
         "mercaderia entre y se cargue en el stock.\n\n"
         "Tampoco sabe de temporadas. Usa el promedio de los ultimos doce "
         "meses parejo. Antes de una temporada fuerte conviene subir la "
         "cobertura a mano.\n\n"
         "Y no sabe si un proveedor tiene el articulo disponible ni cuanto "
         "tarda en entregarlo."),
        (AMBAR, "Si algo no cuadra",
         "Un articulo que se vende mucho no aparece:  puede estar marcado como "
         "inactivo en su ficha, o el analisis de rotacion puede estar "
         "desactualizado.\n\n"
         "Aparece uno que no se vende hace anios:  lo mas probable es que su "
         "stock este en negativo por un error de carga.\n\n"
         "Todas las cantidades dan muy altas:  bajar la cobertura, o cambiar "
         "el criterio de Promedio a Mediana.\n\n"
         "La lista sale vacia:  revisar que la solapa activa sea Inteligente "
         "(rotacion) y no la manual."),
    ]),
]


class Tarjeta(QFrame):
    def __init__(self, acento: str, titulo: str, cuerpo: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {estilo.FONDO_PANEL_ALTO};
                border: 1px solid {estilo.BORDE};
                border-left: 3px solid {acento};
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; border: none; }}
            """
        )
        capa = QVBoxLayout(self)
        capa.setContentsMargins(15, 12, 15, 13)
        capa.setSpacing(7)

        rotulo = QLabel(titulo)
        rotulo.setStyleSheet(
            f"color: {estilo.TEXTO}; font-size: 13px; font-weight: 700;"
        )
        rotulo.setWordWrap(True)
        capa.addWidget(rotulo)

        texto = QLabel(cuerpo)
        texto.setStyleSheet("color: #c6d0e0; font-size: 12px;")
        texto.setWordWrap(True)
        texto.setTextInteractionFlags(Qt.TextSelectableByMouse)
        capa.addWidget(texto)


class DialogoAyuda(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Como funciona esta pantalla")
        self.resize(1120, 760)
        self.setStyleSheet(estilo.hoja_de_estilos())

        capa = QVBoxLayout(self)
        capa.setContentsMargins(14, 14, 14, 14)
        capa.setSpacing(10)

        solapas = QTabWidget()
        for titulo, tarjetas in PAGINAS:
            solapas.addTab(self._pagina(tarjetas), titulo)
        capa.addWidget(solapas, 1)

        pie = QHBoxLayout()
        pie.addStretch(1)
        cerrar = QPushButton("CERRAR")
        cerrar.setObjectName("primario")
        cerrar.setMinimumWidth(110)
        cerrar.clicked.connect(self.accept)
        pie.addWidget(cerrar)
        capa.addLayout(pie)

    def _pagina(self, tarjetas: list[tuple[str, str, str]]) -> QWidget:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)

        contenido = QWidget()
        grilla = QGridLayout(contenido)
        grilla.setContentsMargins(12, 12, 12, 12)
        grilla.setSpacing(11)

        for indice, (acento, titulo, cuerpo) in enumerate(tarjetas):
            grilla.addWidget(
                Tarjeta(acento, titulo, cuerpo), indice // 2, indice % 2
            )
        grilla.setColumnStretch(0, 1)
        grilla.setColumnStretch(1, 1)
        grilla.setRowStretch(grilla.rowCount(), 1)

        area.setWidget(contenido)
        return area
