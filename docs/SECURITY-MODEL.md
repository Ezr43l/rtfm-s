# Modelo de seguridad

## Estado implementado en v0.4.11

- el nodo activo es el único que admite mutaciones;
- el primer acceso transforma la credencial inicial en una cuenta propietaria persistente;
- las contraseñas usan `scrypt` con sal aleatoria y una política mínima configurable;
- el nombre visible, el usuario y la contraseña son editables desde el perfil;
- cambiar la contraseña, activar TOTP o desactivarlo invalida las sesiones anteriores;
- TOTP usa SHA-1, seis dígitos y periodos de 30 segundos conforme al ecosistema estándar;
- el alta TOTP ofrece QR y clave manual; los códigos de recuperación son de un solo uso;
- el secreto TOTP se cifra con una clave derivada de `SESSION_SECRET` y los códigos de
  recuperación se conservan sólo como HMAC;
- la cookie es `HttpOnly`, `SameSite=Strict` y puede marcarse `Secure` tras HTTPS;
- cada sesión tiene expiración y un token CSRF aleatorio;
- las mutaciones con cookie rechazan peticiones sin `X-CSRF-Token`;
- los tokens no forman parte de documentos, metadatos, auditoría ni Git;
- las personas y las aplicaciones usan `reader`, `operator` o `full_control`;
- los permisos se comprueban en la API, además de adaptar los controles visibles;
- `reader` consulta; `operator` crea, edita, mueve, archiva y desarchiva;
- `full_control` añade eliminación al vault, restauración y sincronización manual;
- cada biblioteca puede ser `open` o `restricted`; en modo restringido las concesiones se
  asignan a una persona o cliente API concreto;
- el rol global es siempre el techo de la concesión local y nunca puede elevarse desde una
  biblioteca;
- una identidad sin concesión recibe `404` para no revelar siquiera la existencia de una
  biblioteca restringida;
- las cuentas humanas con `full_control` conservan acceso de recuperación a toda biblioteca;
  los clientes API y `APP_TOKEN` no disfrutan de ese bypass;
- la política alcanza catálogo, categorías, documentos, imágenes, favoritos, búsqueda,
  etiquetas, archivado, papelera y métricas;
- solo una persona con `full_control` administra identidades y debe reconfirmar su
  contraseña y, cuando esté activo, su segundo factor;
- la última persona activa con `full_control` no puede desactivarse ni degradarse;
- cada aplicación tiene token, rol, estado, caducidad opcional, rotación, revocación y
  último uso independientes;
- el token API completo se entrega una vez; se almacena únicamente su HMAC;
- ni un cliente API con `full_control` puede gestionar personas, tokens o autenticación;
- `APP_TOKEN`, `SESSION_SECRET`, `REPLICATION_TOKEN` y `KEEPALIVED_API_KEY` se cargan desde
  variables heredadas o, preferentemente, desde los ficheros indicados por `*_FILE`;
- `KEEPALIVED_API_KEY` se usa solo como Bearer hacia el panel y nunca se escribe en estado,
  auditoría ni respuestas;
- el conector exige HTTPS para hosts remotos salvo opt-in explícito y admite una CA privada;
- el token de réplica es distinto del acceso web/API;
- la réplica sólo acepta esquema 6 desde nodos declarados, limita cuerpos y respuestas,
  exige HTTPS remoto por defecto y admite CA privada;
- los pasivos bloquean escrituras aunque la credencial sea válida;
- los intentos de login se limitan temporalmente por usuario y origen;
- el estado detallado exige identidad y el estado público no expone pares, Git ni rutas;
- las respuestas añaden CSP, Permissions Policy y cabeceras contra MIME sniffing, framing y
  fuga de referrer; HSTS se activa cuando HTTPS y la cookie segura están configurados.
- cualquier cuenta humana, incluida `reader`, puede modificar sus propios favoritos; los
  clientes API no tienen perfil personal y no pueden operar esa colección;
- los registros completos y su exportación sólo son accesibles a una persona con
  `full_control`, pues agregan contexto transversal de varias bibliotecas;

La identidad propietaria histórica se normaliza a `full_control`. Una biblioteca anterior a
`0.4.1`, sin campo `access`, se interpreta como abierta; una política presente pero malformada
falla cerrada como restringida sin concesiones. HTTPS y las validaciones operativas en un host
real siguen siendo necesarios antes de producción.

## Modelo objetivo

Roles globales:

- `reader`: lectura y búsqueda;
- `operator`: creación, edición, movimiento y archivado;
- `full_control`: operaciones destructivas y, solo para personas, administración de accesos.

La evolución prevista incluye sesiones administrables, TOTP obligatorio para administradores
y concesiones por grupos. Se evaluará Argon2id como evolución del hash de contraseñas.

## Secretos

- nunca se escriben en Git, imágenes, logs, documentos ni vault;
- la plantilla Unraid monta cuatro ficheros individuales como solo lectura y únicamente
  expone rutas internas mediante `*_FILE`;
- `SESSION_SECRET` debe ser largo, aleatorio e idéntico en los nodos;
- cambiar `SESSION_SECRET` invalida sesiones y exige un procedimiento de rotación del
  cifrado TOTP; no debe modificarse directamente en un único nodo;
- `SESSION_COOKIE_SECURE=true` solo se activa cuando toda entrada web usa HTTPS;
- los encabezados `X-Forwarded-*` solo se aceptan desde las IPs o redes exactas de
  `FORWARDED_ALLOW_IPS`; el comodín `*` no es una configuración segura;
- los tokens API se muestran una única vez y se guardan como HMAC.
- la clave `fip_…` de Keepalived se guarda en un fichero `0400`, montado como solo lectura, y
  debe tener solo el scope `claims:write` que necesita la instalación.

## Operaciones destructivas

Eliminar un documento crea tombstone y copia de vault. Las categorías y bibliotecas no se
eliminan si contienen elementos. La purga física se limita al contenido del vault una vez
cumplida la retención; el tombstone continúa evitando resurrecciones durante la réplica.

Revocar accesos y cambiar permisos de biblioteca requiere una persona con control total, reconfirmación
de contraseña y segundo factor si lo tiene activo. Cada operación genera auditoría sin secretos.

## Imágenes y diagramas

Las imágenes subidas son privadas: se sirven por un endpoint autenticado, se limita su tamaño,
se comprueba la firma de PNG, JPEG, WebP o GIF y no se admite SVG subido. Siguen el vault,
la réplica y la proyección Git del documento. Mermaid se ejecuta localmente con
`securityLevel=strict`; no habilita HTML ni acciones de clic definidas por el documento.
