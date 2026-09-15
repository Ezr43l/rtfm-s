# Instalación de RTFM 0.4.11 en Unraid

## Antes de empezar

Una instalación nueva necesita un solo contenedor y un solo directorio
persistente. No crees ficheros de secretos ni contenedores de control.

La imagen ejecuta RTFM como UID/GID `10001:10001`. Si el directorio no existe,
Unraid/Docker suele crearlo; si ya existe, comprueba que ese usuario puede
escribir sin aplicar cambios recursivos a ciegas.

## Crear el contenedor

1. Instala `unraid/my-RTFM.xml`.
2. Revisa el puerto `7400`.
3. Elige el directorio de datos, por defecto
   `/mnt/user/appdata/rtfm/data`.
4. Aplica la plantilla.
5. Abre la WebUI desde el icono del contenedor.

La plantilla tiene exactamente dos campos. Usa red `host`, rootfs de sólo
lectura, un `tmpfs` temporal, elimina capacidades y fija
`no-new-privileges`. La ruta de datos es el único mount.

## Completar el asistente

### Un único servidor

1. Escribe un nombre de nodo.
2. Selecciona `Activo fijo`.
3. Deja vacíos Keepalived, réplicas y código de incorporación.
4. Revisa las políticas propuestas.
5. Crea la cuenta propietaria con una contraseña única.
6. Guarda y espera al reinicio interno del servicio.
7. Inicia sesión y configura 2FA.

### Varios nodos con Keepalived

En el primer nodo:

1. selecciona `Automático`;
2. introduce la API local de Keepalived, normalmente
   `http://127.0.0.1:6060`;
3. pega el token `fip_…` generado por Keepalived;
4. declara los otros nodos como `nombre | URL`;
5. utiliza HTTPS, o acepta explícitamente HTTP sólo en una red de confianza;
6. crea la cuenta propietaria;
7. guarda el código de incorporación que aparece una sola vez.

En cada nodo adicional:

1. configura su nombre local y la misma lista vista desde ese nodo;
2. pega el código de incorporación;
3. introduce el token de su API local de Keepalived;
4. no crees otra cuenta propietaria;
5. espera a que el nodo activo replique cuentas, permisos y contenido.

El código alinea el secreto de sesión, el token de réplica, el servicio y el
identificador de reclamación. Trátalo como una credencial y bórralo de notas no
protegidas cuando termines.

## Cambiar la configuración posteriormente

Una cuenta personal con control total puede abrir **Ajustes → Configuración** y
modificar la identidad del nodo, publicación, Keepalived, pares, políticas y
Git. RTFM valida el formulario completo, lo guarda en el volumen y reinicia el
mismo contenedor para aplicarlo. El puerto y el bind mount siguen perteneciendo
a la plantilla porque deben existir antes de que la WebUI pueda abrirse.

Un token de Keepalived vacío conserva el ya guardado. Para desactivar la
integración, vacía también su URL; RTFM retirará entonces esa credencial local.

Para conectar Keepalived sólo hacen falta normalmente su URL base y una clave API
propia para RTFM con el permiso `claims:write`. La URL debe apuntar al primer nodo
de Keepalived, que actúa como escritor, y no debe incluir `/api/claims`. RTFM genera
el identificador estable de la reclamación y ya conoce su puerto y `/api/health`;
esos valores sólo se muestran dentro de **Ajustes avanzados**.

## HTTPS y proxy inverso

Si el proxy termina TLS, elige esquema `https`, activa la cookie Secure e indica
únicamente las IPs o redes desde las que el proxy conecta realmente. Nunca uses
`*`. Si empleas una CA privada para Keepalived o la réplica, pega su PEM en el
asistente; RTFM lo valida y lo guarda en el volumen.

## Comprobaciones

```bash
docker inspect RTFM --format '{{.Config.Image}} {{.Config.User}} {{.HostConfig.ReadonlyRootfs}}'
docker inspect RTFM --format '{{range .Mounts}}{{println .Destination .RW}}{{end}}'
docker inspect RTFM --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(APP_TOKEN|SESSION_SECRET|REPLICATION_TOKEN|KEEPALIVED_API_KEY)='
```

Debe verse el usuario `10001:10001`, rootfs `true`, un único mount `/data` con
escritura y ninguna coincidencia en el último comando. Los secretos nuevos están
en `/data/.rtfm/secrets` con modo `0600` y no aparecen en `docker inspect`.

Comprueba también:

- `/api/health` y la versión `0.4.11`;
- login y 2FA;
- creación, edición, archivado, eliminación y restauración de un documento;
- exportación a PDF desde la vista de lectura, incluyendo imágenes y diagramas;
- estado de la reclamación de Keepalived;
- réplica y rechazo de escrituras en el nodo pasivo;
- backup y restauración del volumen completo.

## Actualizar una instalación anterior

El launcher detecta las variables y rutas `*_FILE` históricas y conserva ese
modo. No borres los secretos externos ni sus mounts durante la misma operación
en la que cambias la imagen. Primero actualiza y verifica el comportamiento
existente; migra al asistente persistido en una intervención separada.

Para cambiar desde “Base Documental” a `RTFM`, detén el contenedor antiguo,
reutiliza exactamente su mount de datos y valida el contenido antes de retirar
su definición. Dos contenedores nunca deben escribir a la vez en ese volumen.

Si el volumen antiguo no pertenece al UID/GID 10001, usa
`scripts/migrate-data-uid.sh`. El script exige parada completa, crea backup y
estado de rollback, rechaza symlinks, hardlinks y mounts ambiguos y no reinicia
el servicio por su cuenta.

## Backup y recuperación

Detén las escrituras de todos los nodos antes de una copia coherente. Incluye
todo `/data`, especialmente `.rtfm`, `auth`, `vault`, `state.json` y `git`.
Restaura en una ruta nueva, conserva propietarios y prueba un único nodo antes
de reincorporar los demás.

No uses una carpeta vacía con el nombre nuevo suponiendo que los datos se han
perdido: localiza primero el mount que utilizaba el contenedor anterior.
