# Contrato API

## Convenciones

- prefijo de producto: `/api/v1`;
- JSON UTF-8 y fechas ISO-8601 UTC;
- identificadores opacos y estables;
- listados de operaciones por `limit` y `cursor`;
- `X-Request-ID` en toda respuesta;
- errores con `{error: {code, message, details, request_id}}`;
- mutaciones web con cookie de sesión y `X-CSRF-Token`;
- clientes registrados con Bearer individual; clientes heredados con Bearer y `X-Actor`.

## Permisos

| Nivel | API de contenido |
|---|---|
| `reader` | lectura, búsqueda, etiquetas y estado |
| `operator` | lo anterior más crear, editar, mover, archivar y desarchivar |
| `full_control` | lo anterior más eliminar, restaurar y sincronizar manualmente |

La administración de `/users` exige además que la identidad sea una persona. Todas sus
mutaciones reconfirman contraseña y 2FA si está habilitado. Un token API nunca puede
administrar otras identidades, aunque tenga `full_control`.

El nivel global es un techo. En una biblioteca `open` se usa directamente; en una biblioteca
`restricted`, una persona o cliente API necesita además una concesión individual y su rol
efectivo es el menor de ambos. Una biblioteca o documento restringido no autorizado responde
`404`. Las cuentas humanas con control total conservan acceso de recuperación. `APP_TOKEN` y
los clientes API no lo conservan.

## Recursos implementados

| Recurso | Operaciones |
|---|---|
| `/auth/session` | crear, consultar y cerrar sesión |
| `/profile` | consultar y editar nombre visible y usuario |
| `/profile/password` | cambiar contraseña e invalidar sesiones anteriores |
| `/profile/2fa/setup` | iniciar o cancelar el alta TOTP |
| `/profile/2fa/enable` | verificar TOTP y emitir códigos de recuperación |
| `/profile/2fa/disable` | desactivar TOTP con contraseña y segundo factor |
| `/profile/2fa/recovery-codes` | invalidar y regenerar códigos de recuperación |
| `/favorites` | listar los documentos favoritos del perfil personal |
| `/favorites/{document_id}` | añadir o retirar un favorito personal |
| `/users` | listar, crear, cambiar permisos/estado y restablecer personas |
| `/users/api-clients` | listar, crear y cambiar aplicaciones autorizadas |
| `/users/api-clients/{id}/rotate` | invalidar el token anterior y emitir uno nuevo |
| `/users/api-clients/{id}/revoke` | revocar definitivamente el token actual |
| `/dashboard` | resumen documental y operativo |
| `/libraries` | listar, crear, editar y eliminar vacías |
| `/libraries/{id}/permissions` | consultar y reemplazar la política de acceso; sólo persona con control total |
| `/libraries/{id}/tree` | árbol recursivo completo |
| `/libraries/{id}/categories` | crear categoría en cualquier nivel |
| `/libraries/{id}/categories/order` | guardar el orden manual de un nivel completo |
| `/categories/{id}` | renombrar, mover o eliminar vacía |
| `/documents` | listar, buscar y crear |
| `/documents/{id}` | leer, editar y eliminar al vault |
| `/documents/{id}/images` | listar y subir imágenes privadas del documento |
| `/documents/{id}/images/{image_id}` | servir una imagen autenticada |
| `/documents/{id}/move` | cambiar biblioteca, categoría y posición |
| `/documents/{id}/archive` | marcar contenido histórico |
| `/documents/{id}/unarchive` | devolver a contenido vigente |
| `/documents/{id}/restore` | restaurar desde vault |
| `/logs` | filtros y paginación por cursor; sólo persona con control total |
| `/logs/export` | CSV o JSONL por periodo y filtros; sólo persona con control total |
| `/public-status` | rol y destino activo mínimos antes del login |
| `/status` | rol, réplica, Git y configuración efectiva; requiere identidad |
| `/sync` | reconciliación manual en nodo activo |
| `/internal/receive` | recepción autenticada entre nodos |

`PATCH /libraries/{id}` acepta `category_sort=manual|alphabetical`. El orden alfabético
se aplica automáticamente a todos los niveles sin destruir las posiciones manuales. El
orden manual se envía como la lista completa de identificadores hermanos junto a su
`parent_id`, evitando posiciones duplicadas o árboles parciales.

## Registros

`GET /api/v1/logs` acepta `limit`, `cursor`, `from`, `to`, `level`, `actor`, `node`,
`action`, `source` y `result`.

`GET /api/v1/logs/export` acepta `range=24h|7d|30d|365d|all`, los mismos filtros y
`format=jsonl|csv`. La exportación recorre todos los cursores; no se limita a la primera
página visible.

## Compatibilidad operativa

`/api/version`, `/api/health` y `/api/status` se conservan sin versión para Keepalived y la
convivencia temporal. `/api/status` devuelve el mismo subconjunto mínimo que
`/api/v1/public-status`; la topología completa ya no es pública. `/api/internal/*` exige el
token de réplica y no debe usarse para nuevas integraciones de producto.

## Autenticación de aplicaciones

El alta y la rotación devuelven `token` una sola vez. Las llamadas usan:

```http
Authorization: Bearer rtfm_…
```

La identidad auditada toma la forma `api:<nombre>`. La respuesta pública solo expone el
prefijo identificativo, estado, permiso, caducidad y último uso; nunca el hash ni el token.
Las credenciales históricas `bdapi_…` no se invalidan por el cambio de nombre y siguen
funcionando hasta que un administrador las rote.

`GET /api/v1/status`, una vez autenticado, incluye `floating_ip`, `floating_url` y
`floating_ip_connector`. Este último informa de estado, origen, servicio, reclamación y
último intento sin exponer `KEEPALIVED_API_KEY`.

## Evolución pendiente

La API incorporará `Idempotency-Key`, grupos de permisos,
referencias, fragmentos, adjuntos, búsqueda de contenido completo y réplica incremental.
