# Contrato de replicación y HA

## Roles

- `active`: propietario de la VIP; acepta mutaciones y origina sincronizaciones.
- `passive`: lectura, recepción de operaciones y estado; no acepta mutaciones.
- `unknown`: no puede decidir con seguridad; bloquea escrituras.

El rol se decide por presencia real de la VIP y no por el nombre del nodo ni por
una preferencia de configuración.

## Operaciones

La unidad de réplica será una operación idempotente, no una copia ciega de la
base de datos. Cada operación incluirá entidad, revisión, reloj lógico, autor,
nodo, tipo de acción y datos necesarios para aplicarla.

El activo enviará lotes cada cinco minutos. El protocolo futuro usará cursor para
no repetir todo el historial. Mientras exista snapshot completo, deberá seguir
siendo reconciliable y no podrá borrar información más nueva del receptor.

El snapshot reconciliable de esquema 6 incluye bibliotecas, categorías, documentos,
imágenes privadas, vault, cuentas humanas, clientes API y auditoría. Los binarios de imagen
viajan codificados dentro del canal interno y siguen la revisión lógica de su documento. Los hashes y secretos cifrados necesarios
para un failover viajan solo por el canal interno autenticado; nunca se proyectan en Git.
Las preferencias de favoritos viajan dentro de la cuenta y el modo de orden dentro de la
biblioteca, ambos con revisión lógica y la misma resolución LWW.

## Conflictos

La comparación se hará por revisión lógica y, en empate, por fecha UTC, nodo y
`operation_id`. Una eliminación produce tombstone con la misma prioridad que una
edición. Un tombstone más nuevo siempre gana a una copia antigua del documento.

## Recuperación

- un pasivo que vuelve debe pedir operaciones desde su cursor;
- si perdió el historial, recibirá snapshot reconciliable;
- el activo nunca aceptará un snapshot pasivo como sustitución completa;
- toda aplicación de réplica quedará auditada;
- la purga física del vault no elimina el tombstone.

## Seguridad de nodo

Los endpoints internos usan credencial propia, identificación de nodo y controles de rol.
El receptor sólo admite bundles de esquema 6 cuyo `node` esté declarado en `PEERS`, limita
el cuerpo mediante `MAX_REPLICATION_MB` y rechaza tipos estructurales incompletos. El emisor
limita también la respuesta y verifica HTTPS con el almacén del sistema o
`REPLICATION_CA_FILE`. HTTP hacia otro host requiere
`REPLICATION_ALLOW_INSECURE_HTTP=true` y no es apto para redes no confiables.

Las respuestas informan si se aplicó, ignoró o rechazó cada operación para poder explicar
la convergencia. La evolución a lotes firmados, cursores y anti-replay granular continúa
pendiente; el snapshot completo actual confía en los nodos que comparten el token.
