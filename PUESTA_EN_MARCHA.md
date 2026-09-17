# Puesta en marcha

Pasos para instalarlo de verdad, en orden. Los tres primeros no tocan el
ERP, así que se pueden hacer sin sacar a nadie del sistema.

---

## 0. Borrar la configuración de las pruebas

**Hacelo primero.** Cuando probaste el `.exe` con datos inventados, el
programa guardó esas rutas al cerrarse:

```
%APPDATA%\Reposicion\reposicion.json
```

Ese archivo tiene prioridad sobre la autodetección del `CONFIG.DBF`. Lanzado
desde el menú del ERP no molesta — los parámetros de la línea de comandos le
ganan a todo — pero si alguien abre el `.exe` con doble clic, va a ver los
datos de prueba otra vez y a pensar que el programa está roto.

```bat
del "%APPDATA%\Reposicion\reposicion.json"
```

Y si generaste tablas de prueba en algún lado, borralas también, para que no
quede una carpeta con ARTICULO.DBF falsos dando vueltas.

---

## 1. Copiar el .exe al servidor

Va a la carpeta de datos, la misma de `ARTICULO.DBF`:

```
copy dist\reposicion.exe  <sis_path_>\
```

Una sola copia para todas las terminales. Cuando haya una versión nueva se
reemplaza ahí y listo.

**Dos cosas que suelen morder al correr un .exe desde un recurso de red:**

- **Windows lo marca como "descargado de internet"** y muestra el cartel de
  seguridad en cada arranque. Se saca con clic derecho → Propiedades →
  *Desbloquear*, o con `Unblock-File` de PowerShell.
- **El antivirus corporativo** desconfía de los ejecutables de PyInstaller.
  Si lo pone en cuarentena, hay que agregar la ruta a las excepciones. Firmar
  el `.exe` con un certificado lo resuelve de raíz, si tenés uno.

---

## 2. Correr el diagnóstico

Antes de tocar el menú. Desde cualquier terminal:

```bat
<sis_path_>\reposicion.exe --diagnostico
```

No modifica nada: abre las tablas, revisa que estén los campos, cruza las
claves, prueba si puede escribir y muestra un informe. Deja una copia en el
Escritorio.

Lo que hay que mirar:

| Sección | Qué tiene que decir |
|---|---|
| 2. Tablas | Las cuatro encontradas, con **codepage cp1252** |
| 3. Catálogo | Un porcentaje alto de artículos activos en la sucursal |
| 4. PROVEEDO | *Todos los códigos engancharon* |
| 5. Codificación | Las descripciones con eñes y acentos **legibles** |
| 6. Corrida | Un porcentaje razonable de artículos con ventas, y por **clave completa** |
| 7. Comprobantes | DOCUM y DOCCUER en las tres fuentes |
| 8. Escritura | Se puede escribir en la carpeta de datos |

Si el resumen dice *"Sin problemas bloqueantes"*, seguí. Si marca algo con
`[ERROR]`, mandámelo y lo vemos: el informe está pensado para que se pueda
copiar y pegar entero.

---

## 3. Generar la rotación por primera vez

Abrí el `.exe` normal (doble clic sirve: encuentra el `CONFIG.DBF` solo) y
apretá **RECALCULAR ROTACIÓN**.

Con tus volúmenes son un par de segundos. Hasta que esa tabla exista, la
solapa *Inteligente (rotación)* no tiene de dónde sacar la columna Vta/mes.

**Acá se decide lo de los remitos internos.** La opción viene destildada, o
sea que los `RI` **no** cuentan como venta. Si querés que los números
coincidan con lo que genera el ERP hoy, tildala. Está explicado en la misma
pantalla.

---

## 4. Agregar la opción al menú

Recién ahora se toca el ERP, con todo lo demás ya verificado.

1. `MODIFY MENU <nombre del menú>`
2. Ubicate en el popup que corresponda (Compras, Consultas, Informes...).
3. Nueva fila:
   - **Prompt:** `Reposición de stock`
   - **Result:** `Procedimiento` ← no *Comando*
4. Botón **Crear** y pegá el contenido de
   `integracion_vfp/opcion_de_menu.prg`.
5. **Menú → Generar** (regenera el `.MPR`).
6. Recompilá `SISTEMA.EXE` y distribuilo como siempre.

El código es autocontenido: no llama a ningún PRG externo, así que no hay que
acordarse de copiar un archivo aparte ni de agregarlo al proyecto.

**No armes los parámetros a mano concatenando comillas.** Usá la función
`Ent()` que viene al final del archivo. `sis_path_` termina en barra
invertida (viene de `ADDBS`), y una barra pegada a la comilla de cierre la
**escapa**: Windows se traga el resto de la línea adentro del mismo
argumento y el programa no recibe ni la sucursal ni la segunda carpeta.

```
--data "S:\" --sucursal "1"     ->  Windows entrega UN argumento:
                                     S:" --sucursal 1

--data "S:\\" --sucursal "1"     ->  Windows entrega lo correcto:
                                     S:\  /  --sucursal  /  1
```

`Ent()` duplica esas barras finales. El programa además detecta la línea
rota y la repara solo, pero conviene no depender de eso.

Le pasa las cuatro variables del entorno por línea de comandos, que es la
capa de mayor prioridad. Así el programa usa **siempre** los valores del ERP
que lo está lanzando, sin importar qué haya guardado antes.

---

## 5. Probar desde el menú

Andá a la opción nueva. Tiene que abrir con los datos reales y el encabezado
arriba a la derecha mostrando la sucursal y la carpeta de datos. Verificá:

- El ranking de proveedores con **nombres de verdad**, no `[código] no está
  en PROVEEDO`.
- Las descripciones con eñes bien escritas.
- Clic en un proveedor: la grilla de la derecha se llena.
- **Exportar a Excel** y **Imprimir / Exportar PDF** (esta última es la que
  usa Pillow, conviene probarla una vez).
- **Ver informe del análisis**, que abre en el navegador.

---

## Después: mantenimiento

**Recalcular rotación una vez por semana.** No hace falta más seguido: el
stock se lee fresco en cada apertura, lo único que envejece es el promedio de
ventas. Conviene hacerlo con la pantalla cerrada en los demás puestos — si
otro la tiene abierta, el reemplazo falla con un mensaje claro y la tabla
anterior queda intacta.

**Para actualizar el programa**, reemplazás el `.exe` en el servidor. Nada
más: no hay instalador, ni registro, ni dependencias en las terminales.

**Si algo raro pasa en una terminal puntual**, corré ahí mismo
`reposicion.exe --diagnostico`. La mayoría de los problemas de una sola
máquina son permisos o una unidad de red que no está mapeada, y el informe
los nombra.

---

## Los parámetros, por si hacen falta a mano

Ojo con la barra final si los escribís a mano: hay que **duplicarla**.

```bat
reposicion.exe --data "X:\SISTEMA\DATOS\\" --data2 "Y:\SUC2\DATOS\\" ^
               --sucursal "1" --zip "Z:\PENDRIVE\\"
```

| Parámetro | Era | Para qué |
|---|---|---|
| `--data` | `sis_path_` | Carpeta de ARTICULO, PROVEEDO, ROTACION, DOCUM, DOCCUER |
| `--data2` | `sis_path2` | La otra sucursal. Opcional |
| `--sucursal` | `sis_sucurs` | Filtra `AR_SUCU` |
| `--zip` | `zip_path_` | El pendrive. Sólo para recalcular rotación |
| `--diagnostico` | — | Revisa el entorno y sale |
| `--ajustes` | — | Abre la pantalla de configuración |
| `--codepage` | — | Forzar `cp850` si los acentos salieran mal |
