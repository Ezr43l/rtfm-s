# Changelog

## [0.4.10] - 2026-09-13

### Añadido

- Añadido en el acceso, el pie del portal y la pantalla de nodo pasivo el enlace de
  soporte a la comunidad de Discord de Unraides.
- La plantilla pública continúa siguiendo el canal de desarrollo `dev`.

## [0.4.9] - 2026-09-11

### Añadido

- Cada documento dispone de una acción **Exportar PDF** en su vista de lectura.
- La exportación espera a que terminen de cargar las imágenes y los diagramas Mermaid y
  utiliza el motor de impresión del navegador, sin añadir servicios ni contenedores.
- La hoja de impresión genera un documento A4 limpio, sin navegación ni controles, y adapta
  títulos, tablas, bloques de código, imágenes y diagramas para evitar cortes incorrectos.

## [0.4.8] - 2026-09-11

### Corregido

- La conexión con Keepalived muestra como datos principales únicamente su URL base y la
  clave API de RTFM, e indica dónde crearla y qué permiso necesita.
- El identificador de reclamación, la ruta de salud, el servicio, los puertos, el timeout y
  las CA privadas se explican y agrupan como ajustes avanzados; RTFM conserva sus valores
  automáticos para una instalación normal.
- La configuración de réplicas distingue las direcciones directas de los nodos de la IP
  flotante y aporta ejemplos completos sin incorporar datos del entorno de desarrollo.
- Los campos de Keepalived y réplica mantienen alturas y alineación uniformes tanto en el
  primer arranque como en la configuración autenticada.

## [0.4.7] - 2026-09-11

### Corregido

- La página de configuración deja de ser meramente informativa: una cuenta personal con
  control total puede editar desde RTFM la identidad del nodo, publicación, Keepalived,
  réplica, políticas e historial Git.
- Los cambios se validan con el mismo contrato del primer arranque, se guardan de forma
  atómica en el volumen persistente y se aplican reiniciando el único contenedor.
- El token de Keepalived nunca se devuelve al navegador. Un campo vacío conserva el token
  existente y vaciar también la URL desactiva la integración y elimina esa credencial.
- La plantilla Unraid continúa reducida a las dos conexiones imprescindibles para arrancar:
  puerto de la WebUI y volumen de datos.

## [0.4.6] - 2026-09-07

### Corregido

- La plantilla Unraid pasa de 42 campos a dos conexiones Docker: puerto y datos.
- El primer arranque se completa en la WebUI y guarda la configuración dentro
  del volumen persistente.
- Los secretos de sesión y réplica se generan con modo `0600`; Keepalived se
  configura sin publicar su token en Docker.
- El código de incorporación comparte de forma controlada las credenciales de
  sesión y réplica y la identidad de la reclamación entre nodos RTFM.
- Las instalaciones históricas que proporcionan variables o `*_FILE` conservan
  su comportamiento y no entran en el asistente nuevo.

- RTFM acepta tanto los Bearer históricos como los nuevos Bearer reforzados que
  genera Keepalived, bajo el contrato común `fip_` de 32 a 128 caracteres.

## [0.4.5] - 2026-09-07

### Corregido

- El canal compartido adopta definitivamente el nombre de producto `rtfm-s`; imagen,
  plantilla, metadatos OCI, CI, release y documentación dejan de usar el nombre anterior.
- Se retiran del árbol exportable los diarios y evidencias de laboratorios privados. El
  repositorio compartido contiene sólo producto, pruebas reproducibles y documentación
  universal.
- La instalación conserva un único servicio y un único contenedor RTFM, sin datos de nodos,
  rutas, inventarios ni credenciales de una instalación particular.

## [0.4.4] - 2026-09-01

### Corregido

- La publicación usa los digests propios de AMD64 y ARM64 al validar cada imagen y evita
  repetir antes de publicar las pruebas que ya exige la CI del mismo commit.

## [0.4.3] - 2026-09-01

### Corregido

- La publicación multi-arquitectura elimina la copia local de cada plataforma antes de
  validar la siguiente y espera a que GitHub haga visible el borrador de la release.

## [0.4.2] - 2026-09-01

- desactivado el mantenimiento Git automático en segundo plano para que no compita con
  backups, migraciones ni la retirada de repositorios efímeros;
- exportación pública desde el snapshot inmutable de `HEAD`, con regeneración del manifiesto
  al reexportar un árbol público y publicación atómica sin sobrescritura;
- lectura de secretos limitada a ficheros regulares, pequeños, sin symlinks ni hardlinks y
  con permisos compatibles tanto con UID/GID `10001` en Unraid como con secretos Docker
  root-owned de solo lectura;
- migración transaccional y reversible de bind mounts a UID/GID `10001`, con estado durable,
  revalidación inmediata de mounts y escritores, rechazo de hardlinks y tipos especiales,
  backup verificado y rollback sin depender de variables de otra sesión;
- plantillas, documentación y artefactos actuales alineados con
  `Ezr43l/rtfm-s:0.4.2`, sin referencias exportables al repositorio privado ni a
  infraestructura personal.

## [0.4.1] - 2026-08-30

- exportación pública determinista construida exclusivamente desde los blobs enumerados por
  `git ls-files`, con denylist, detección de secretos e infraestructura privada, metadatos
  normalizados y manifiesto SHA-256, sin historial ni directorios ignorados; los autores de
  la proyección Git usan el dominio reservado `rtfm.invalid` en vez de un sufijo de red local;
- procedimiento reutilizable para migrar volúmenes existentes a UID/GID `10001`, con parada
  coordinada, ruta real obtenida de Docker, rechazo de symlinks/mounts anidados, backup frío,
  prueba aislada, verificación funcional y rollback conservador;
- plantilla Unraid endurecida para montar `APP_TOKEN`, `SESSION_SECRET`,
  `REPLICATION_TOKEN` y `KEEPALIVED_API_KEY` desde ficheros `0400` de solo lectura, sin
  valores directos visibles en `docker inspect`, con guía de bootstrap y migración;
- permisos por biblioteca con modos abierto y restringido para personas y clientes API;
- rol global conservado como techo de privilegio, sin posibilidad de elevarlo mediante una
  concesión local;
- acceso de recuperación garantizado para cuentas humanas activas con control total, evitando
  el bloqueo accidental de una instalación;
- bibliotecas de versiones anteriores tratadas como abiertas sin reescritura destructiva y
  políticas explícitamente corruptas tratadas como restringidas sin concesiones;
- ocultación uniforme de bibliotecas no autorizadas en catálogo, árbol, documentos, imágenes,
  búsqueda, etiquetas, favoritos, archivado, papelera y métricas del panel;
- controles de lectura, creación, edición, movimiento, archivado, eliminación y restauración
  aplicados en la API, incluida la comprobación simultánea de origen y destino al mover;
- gestión visual de permisos reservada a personas con control total y protegida con
  reconfirmación de contraseña y segundo factor cuando está activo;
- registros completos y exportaciones restringidos a cuentas humanas con control total para
  evitar que la auditoría revele contenido o identidades fuera del ámbito autorizado;
- política replicada dentro de la entidad biblioteca manteniendo el esquema HA 6 y la
  compatibilidad de actualización desde `0.4.0`;
- licencia Apache-2.0 adoptada para código y documentación del proyecto compartido;
- avisos de terceros separados de la licencia del producto, textos npm y Python de
  producción recolectados de forma determinista y términos de Git/iproute2 conservados
  en la imagen;
- releases bloqueadas hasta adjuntar fuentes Alpine verificadas y reproducibles de las
  dependencias recíprocas presentes en AMD64 y ARM64, incluida MPL-2.0;
- wheels Python bloqueados por SHA-256 para impedir sustituciones silenciosas durante el build;
- reverse proxies configurables mediante una lista cerrada de orígenes confiables y una
  puerta HTTPS que verifica TLS, HSTS, cookie segura y limitación de login por cliente;
- todas las salidas HTTP(S) validan de nuevo el esquema y el destino en el límite de
  transporte; las invocaciones a Git e `ip` usan binarios absolutos, argumentos fijos y nunca
  un shell;
- CI y release auditan dependencias, análisis estático en todas las severidades, secretos e
  imágenes por arquitectura con herramientas y acciones fijadas por commit o digest;
- base de ejecución migrada de Debian a Alpine 3.24 para eliminar los hallazgos HIGH/CRITICAL
  sin corrección que introducía la cadena de dependencias de Perl de Git, manteniendo Git,
  `iproute2`, el usuario no privilegiado y las bases fijadas por digest;
- smoke de runtime actualizado al contrato `/api/v1`, con biblioteca obligatoria, sesión,
  CSRF, ciclo crear/editar/eliminar/restaurar y verificación del registro de auditoría;
- 54 pruebas unitarias, compilación TypeScript, build de producción, recorrido integral de
  permisos y actualización real `0.4.0` → `0.4.1` verificadas en contenedores aislados;
- seis recorridos smoke reproducibles cubren runtime, editor, perfil/TOTP, permisos,
  orden/favoritos y la forma persistida heredada; CI y release los ejecutan sin reutilizar
  contenedores ni volúmenes.

## [0.4.0] - 2026-08-29 · EN DESARROLLO

- producto renombrado a **RTFM (Read The Fucking Manual)** en la interfaz, API, imagen,
  contenedor Compose, plantilla Unraid, exportaciones, TOTP, Git y documentación;
- reclamación idempotente de la IP flotante mediante la API autenticada de Keepalived con
  Bearer `fip_…`, timeout, HTTPS/CA privada y opt-in para HTTP remoto;
- dirección asignada por Keepalived utilizada como fuente efectiva del rol activo/pasivo y
  confirmada periódicamente sin liberar la reclamación compartida al detener un nodo;
- estado del conector, dirección efectiva, última confirmación y errores seguros visibles en
  la API y en Ajustes, con salud `ok`, `degraded` o `unknown`;
- compatibilidad manual mediante `FLOATING_IP` y derivación configurable de la URL pública;
- nuevos tokens de integración propios con prefijo `rtfm_`; los `bdapi_` existentes siguen
  siendo válidos hasta su rotación;
- instalación generalizada mediante Compose, `.env.example` y plantilla
  `unraid/my-RTFM.xml`, sin nombres de nodos, IP, registro ni rutas del entorno original;
- convención de promoción fijada desde un repositorio privado de desarrollo al futuro
  repositorio público limpio `Ezr43l/rtfm-s`, sin cambiar la versión;
- plantilla Unraid directamente consumible, sin marcadores, preparada para la futura imagen
  `ghcr.io/ezr43l/rtfm-s:0.4.0` y con valores neutros editables;
- build reproducible con bases fijadas por digest, dependencias Python exactas, typecheck,
  frontend y pruebas obligatorias, compilación cruzada en `$BUILDPLATFORM` y usuario no root;
- Compose endurecido con filesystem de sólo lectura, capacidades eliminadas, `no-new-privileges`,
  límite de procesos, `tmpfs` y soporte de secretos montados mediante `*_FILE`;
- réplica limitada por tamaño, restringida a nodos declarados, con validación de esquema,
  respuestas acotadas, HTTPS por defecto y CA privada opcional;
- estado detallado protegido tras login, estado previo mínimo, cabeceras CSP/HSTS y límite
  temporal de intentos de autenticación;
- `react-router-dom` actualizado a `7.18.3` para corregir los avisos de seguridad detectados
  en la dependencia anterior;
- ruta de datos nueva `/mnt/user/appdata/rtfm/data` para altas limpias y procedimiento de
  migración que conserva el volumen anterior y adopta de forma explícita la VIP manual
  existente durante una actualización.

## [0.3.6] - 2026-08-25 · EN DESARROLLO

- ruta de navegación completa para bibliotecas con categorías anidadas;
- cada nivel anterior de la ruta permite volver directamente a esa carpeta;
- compresión automática desde el inicio con puntos suspensivos cuando la ruta desborda;
- conservación de la navegación hacia la categoría padre al volver desde un documento.

## [0.3.5] - 2026-08-25 · EN DESARROLLO

- árbol lateral de bibliotecas contraído por defecto para que una estructura extensa siga
  siendo legible;
- apertura automática exclusiva de la rama que contiene la categoría seleccionada;
- conservación de la carpeta de origen al abrir documentos desde el árbol o el listado;
- retorno estable a la categoría correcta mediante historial, enlace de vuelta y navegación
  entre vista y edición;
- controles de expansión con estado accesible y nombre descriptivo para lectores de pantalla.

## [0.3.4] - 2026-08-21 · EN DESARROLLO

- orden de categorías configurable por biblioteca entre manual y alfabético A–Z;
- reordenación manual independiente en cada nivel mediante arrastre y controles subir/bajar;
- conservación de las posiciones manuales al alternar temporalmente al modo alfabético;
- favoritos personales por cuenta, disponibles también para perfiles de solo lectura;
- estrellas de favorito en documentos, bibliotecas, búsqueda y listados, con confirmación
  visual y una página propia de acceso rápido;
- favoritos y configuración de orden auditados y replicados mediante el esquema HA 6;
- proyección Git atómica del orden completo de categorías sin exponer preferencias personales.

## [0.3.3] - 2026-08-21 · EN DESARROLLO

- edición posterior de nombre, descripción y color de cualquier biblioteca;
- acceso visible a la edición desde la cuadrícula general y la cabecera de cada biblioteca;
- edición de nombre, descripción y ubicación de categorías desde el árbol, sus filas y la
  carpeta seleccionada, sin depender de descubrir una única acción contextual;
- descripciones de categorías visibles en el listado para aportar contexto documental;
- operaciones protegidas por permiso de operador y registradas como `library.update` y
  `category.update` en la auditoría existente.

## [0.3.2] - 2026-08-21 · EN DESARROLLO

- editor Markdown profesional con barra para títulos, negrita, cursiva, tachado, código,
  citas, listas, tareas, enlaces, imágenes, tablas, separadores y bloques de código;
- modos de escritura, pantalla dividida y vista previa en directo, además de edición a
  pantalla completa, contadores, atajos y protección frente a cambios sin guardar;
- enlaces guiados tanto a direcciones externas como a otros documentos de la base;
- estudio Mermaid integrado con nueve plantillas para flujos, arquitectura, secuencias,
  estados, entidad–relación, clases, Gantt, mapas mentales y gráficos circulares;
- edición posterior de diagramas existentes, validación visual inmediata y descarga SVG;
- renderizado Mermaid local, diferido y endurecido con `securityLevel=strict` tanto en la
  vista del documento como en la previsualización;
- carga de imágenes privadas mediante selector, arrastre o pegado desde el portapapeles,
  además de reutilización de imágenes ya asociadas al documento y enlaces remotos;
- validación de firma para PNG, JPEG, WebP y GIF, límite configurable con
  `MAX_IMAGE_SIZE_MB` y servicio exclusivo a identidades autenticadas;
- imágenes incluidas en auditoría, historial Git, vault y esquema 5 de replicación HA;
- documentación técnica, contrato API, arquitectura, seguridad y modelo de datos actualizados.

## [0.3.1] - 2026-08-21 · EN DESARROLLO

- corregida la copia de tokens API cuando el portal se utiliza por HTTP en la red local;
- compatibilidad automática con navegadores que bloquean la API moderna del portapapeles;
- nuevo aviso flotante verde y accesible con el mensaje `Token copiado` tras confirmar la copia;
- aviso de error explícito si el navegador rechaza también el método alternativo.

## [0.3.0] - 2026-08-21 · EN DESARROLLO

- nueva página real `Ajustes > Usuarios` para administrar identidades nominales y
  aplicaciones API sin mezclar ambos tipos de acceso;
- tres niveles globales aplicados por el backend: solo lectura, operador y control total;
- los operadores pueden crear, editar, mover, etiquetar, archivar y desarchivar, pero no
  eliminar contenido ni restaurarlo desde el vault;
- las operaciones destructivas, la restauración y la sincronización manual exigen control total;
- adaptación completa de la interfaz para no ofrecer acciones que el usuario no puede ejecutar;
- alta, desactivación, cambio de permisos y restablecimiento de contraseña de cuentas nominales;
- protección que impide degradar o desactivar la última cuenta humana activa con control total;
- clientes API independientes con permiso, estado, caducidad opcional, último uso, rotación y
  revocación, autenticados mediante tokens individuales;
- el token API se muestra únicamente al crearlo o rotarlo y solo se conserva su HMAC;
- ni siquiera una aplicación con control total puede administrar usuarios, tokens o autenticación;
- las operaciones administrativas reconfirman contraseña y 2FA de la persona administradora;
- auditoría identifica aplicaciones como `api:<nombre>` sin registrar credenciales;
- cuentas y clientes API incluidos en el esquema 4 de replicación HA;
- compatibilidad temporal conservada para `APP_TOKEN` y clientes heredados con `X-Actor`;
- documentación de arquitectura, seguridad, API y modelo de datos actualizada;
- 26 pruebas unitarias, compilación TypeScript de producción y recorrido integral de permisos.

## [0.2.1] - 2026-08-20 · EN DESARROLLO

- eliminado el nombre de usuario predefinido del formulario de acceso: el campo se
  presenta siempre vacío y no sugiere ninguna identidad existente.

## [0.2.0] - 2026-08-20 · EN DESARROLLO

- cuenta propietaria persistente creada de forma segura durante el primer acceso;
- perfil editable con nombre visible y nombre de usuario independiente;
- cambio de contraseña con hash `scrypt`, política configurable e invalidación de las
  sesiones anteriores;
- autenticación TOTP compatible con aplicaciones estándar, alta mediante QR y clave
  manual, desactivación verificada y diez códigos de recuperación de un solo uso;
- secretos TOTP cifrados en disco y códigos de recuperación almacenados únicamente como
  hashes, sin incluir credenciales en auditoría ni en la proyección Git;
- cuentas y estado de seguridad incorporados al esquema 3 de replicación HA;
- nueva página real `/profile`, acceso desde la cabecera y flujo de login en dos pasos;
- escala tipográfica general aumentada y diseños de perfil adaptados a escritorio y móvil;
- plantilla Unraid ampliada con política de contraseña e identificador TOTP;
- pruebas unitarias de contraseñas, cifrado, TOTP, recuperación, sesiones y réplica, más
  un recorrido integral de la migración de cuenta en un contenedor aislado.

## [0.1.2] - 2026-08-20 · EN DESARROLLO

- corregida la inicializacion de sesiones cuando Unraid define `SESSION_SECRET` con
  valor vacio: ahora se aplica correctamente la compatibilidad con `APP_TOKEN`;
- puerto HTTP predeterminado migrado de `8080` a `7400`, comprobado como libre en
  los tres nodos del laboratorio original;
- plantilla de Unraid, imagen, Compose y prueba de humo alineados con el nuevo puerto;
- cobertura automatizada para el secreto de sesion vacio, el secreto independiente y
  el puerto predeterminado.

## [0.1.1] - 2026-08-20 · EN DESARROLLO

- reevaluación automática del rol HA cada 15 segundos en pestañas abiertas;
- transición sin recarga entre el espacio activo y la pantalla pasiva;
- estado conocido de las réplicas visible también desde la pantalla pasiva.

## [0.1.0] - 2026-08-20 · EN DESARROLLO

Reconstrucción de los cimientos de producto:

- frontend React + TypeScript dividido en páginas con rutas reales y enlaces directos;
- navegación profesional separada en documentación, administración y ajustes;
- bibliotecas configurables por el usuario como raíces documentales independientes;
- categorías recursivas, sin profundidad fija, con validación de pertenencia y ciclos;
- documentos permitidos tanto en la raíz como dentro de cualquier categoría;
- visor Markdown, editor independiente, movimiento, etiquetas, archivado y papelera;
- búsqueda global y páginas específicas para archivados, etiquetas y eliminados;
- sesión web firmada con cookie HttpOnly y protección CSRF; la credencial desaparece
  completamente del editor y del modelo documental;
- API estable `/api/v1` organizada por dominios y errores con `request_id`;
- catálogo completo incluido en la réplica HA y en la proyección Git;
- registros movidos a `Ajustes > Registros`, con filtros, cursor, tamaño de página,
  detalle compacto y exportación CSV/JSONL funcional;
- tema claro suave y tema oscuro, ambos adaptativos para escritorio y móvil;
- compatibilidad conservada con los endpoints de Keepalived y la réplica v0.0.6;
- compilación TypeScript, 13 pruebas unitarias y recorrido integral en contenedor aislado.

## [0.0.6] - 2026-08-20 · EN DESARROLLO

Fase 2: historial Git documental:

- repositorio Git persistente y configurable dentro del volumen de datos;
- commits automáticos para crear, modificar, archivar, eliminar y restaurar documentos;
- trailers de operación, evento, actor y nodo en cada commit;
- proyección estable por identificador en documents/<id>/;
- estado Git expuesto en /api/status;
- commits de reconciliación cuando una réplica aplica cambios;
- variables de Git añadidas a la plantilla de Unraid.

## [0.0.5] - 2026-08-20 · EN DESARROLLO

Fase 1: primera renovación de interfaz:

- visor de actividad compacto con columnas horizontales;
- paginación por cursor, filtros y descarga JSONL/CSV por periodo;
- modo claro y oscuro con preferencia persistente;
- navegación lateral preparada para las futuras secciones documentales;
- icono renovado de mayor presencia y PNG real para Unraid;
- pruebas unitarias de paginación y filtros del registro.

## [0.0.4] - 2026-08-20 · EN DESARROLLO

Fase 0: contratos de producto y arquitectura.

## [0.0.3] - 2026-08-20 · EN DESARROLLO

Corrección de detección de rol: la imagen incluye `iproute2` para que `ROLE_MODE=auto`
pueda comprobar la IP flotante desde la red host de Unraid.

## [0.0.2] - 2026-08-20 · EN DESARROLLO

Se eliminó entonces el healthcheck interno de Docker; la línea `0.4.0` lo recupera usando
el contrato seguro de `/api/health`.

## [0.0.1] - 2026-08-20 · EN DESARROLLO

Plantilla nativa de Unraid, red host, icono propio y configuración de pares, tokens,
retención y sincronización desde DockerMan.

## [0.0.0] - 2026-08-20 · EN DESARROLLO

Primera base funcional de la plataforma documental.
