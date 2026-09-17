*==========================================================================
* ABRIR_REPOSICION.PRG
*
* Reemplaza al DO FORM reposicion. Lanza el ejecutable pasandole por linea
* de comandos las mismas variables publicas que el formulario usaba cuando
* vivia adentro del ERP.
*
* Uso:
*     DO abrir_reposicion
*
* Donde poner el .EXE:
*     Lo mas comodo es dejarlo en la misma carpeta de datos (sis_path_),
*     asi se actualiza en un solo lugar para todas las terminales. Si se
*     prefiere tenerlo local, cambiar lcExe por la ruta que corresponda.
*==========================================================================
LOCAL lcExe, lcParams, lcMsg

*--- 1. Donde esta el ejecutable ------------------------------------------
lcExe = ADDBS(sis_path_) + "reposicion.exe"

IF NOT FILE(lcExe)
    MESSAGEBOX("No se encontro el programa de reposicion en:" + CHR(13) + ;
               lcExe, 16, "Falta el ejecutable")
    RETURN
ENDIF

*--- 2. Parametros --------------------------------------------------------
* Se entrecomillan con Ent() y NO a mano. sis_path_ termina en barra
* invertida (viene de ADDBS), y una barra pegada a la comilla de cierre la
* ESCAPA: Windows se traga el resto de la linea adentro del mismo
* argumento. Ent() duplica esas barras finales. Ver el comentario largo en
* opcion_de_menu.prg.
lcParams = "--data "     + Ent(sis_path_) + " " + ;
           "--sucursal " + Ent(sis_sucurs)

* sis_path2 y zip_path_ son opcionales: si no estan definidas en el entorno
* el programa arranca igual, solo que sin el analisis de la otra sucursal.
IF TYPE("sis_path2") = "C" AND NOT EMPTY(sis_path2)
    lcParams = lcParams + " --data2 " + Ent(sis_path2)
ENDIF

IF TYPE("zip_path_") = "C" AND NOT EMPTY(zip_path_)
    lcParams = lcParams + " --zip " + Ent(zip_path_)
ENDIF

*--- 3. Lanzar ------------------------------------------------------------
* ShellExecute en vez de RUN: no bloquea el ERP mientras el programa esta
* abierto, y no deja una ventana de consola dando vueltas.
DECLARE INTEGER ShellExecute IN shell32.dll ;
    INTEGER hwnd, STRING lpOperation, STRING lpFile, ;
    STRING lpParameters, STRING lpDirectory, INTEGER nShowCmd

LOCAL lnRet
lnRet = ShellExecute(0, "open", lcExe, lcParams, ADDBS(sis_path_), 1)

* Valores menores o iguales a 32 son codigos de error de ShellExecute
IF lnRet <= 32
    DO CASE
        CASE lnRet = 2
            lcMsg = "No se encontro el archivo."
        CASE lnRet = 3
            lcMsg = "No se encontro la carpeta."
        CASE lnRet = 5
            lcMsg = "Acceso denegado."
        CASE lnRet = 8
            lcMsg = "Memoria insuficiente."
        OTHERWISE
            lcMsg = "Codigo de error " + TRANSFORM(lnRet) + "."
    ENDCASE
    MESSAGEBOX("No se pudo abrir el programa de reposicion." + CHR(13) + ;
               CHR(13) + lcMsg, 16, "Error al iniciar")
ENDIF

RETURN


*==========================================================================
* Ent()  -  Entrecomilla un valor para la linea de comandos de Windows,
* duplicando las barras invertidas del final.
*
*     Ent("S:\")           ->  "S:\\"     y Windows lee  S:\
*==========================================================================
FUNCTION Ent
    LPARAMETERS tcValor
    LOCAL lcValor, lnBarras, lnLargo

    lcValor = ALLTRIM(TRANSFORM(tcValor))
    lnLargo = LEN(lcValor)
    lnBarras = 0

    DO WHILE lnBarras < lnLargo ;
             AND SUBSTR(lcValor, lnLargo - lnBarras, 1) == "\"
        lnBarras = lnBarras + 1
    ENDDO

    RETURN '"' + lcValor + REPLICATE("\", lnBarras) + '"'
ENDFUNC
