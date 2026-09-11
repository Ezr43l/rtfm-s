# Modelo de datos

## Organización implementada

| Entidad | Propósito | Relación |
|---|---|---|
| `library` | raíz documental creada por el usuario | contiene categorías y documentos |
| `category` | carpeta recursiva | pertenece a biblioteca y a un padre opcional |
| `document` | unidad estable de contenido | pertenece a biblioteca y categoría opcional |
| `document_image` | imagen privada versionada | pertenece a un documento y sigue su ciclo de vida |
| `tag` | clasificación transversal | lista normalizada en documento; N:M futura |
| `audit_event` | operación inmutable | actor, nodo, entidad, acción y resultado |
| `vault_item` | contenido eliminado recuperable | pertenece a documento y revisión de borrado |
| `user` | identidad nominal, contraseña, rol y segundo factor | cuenta humana replicada entre nodos |
| `api_client` | identidad de una aplicación y hash de su token | acceso no humano replicado entre nodos |

No existen bibliotecas, nodos, proyectos ni categorías codificados en la aplicación. Una
estructura como `Servidores > Nodo principal > Contenedores` la crea el usuario y puede ser distinta en
cada biblioteca.

## Biblioteca

Campos principales: `id`, `name`, `slug`, `description`, `icon`, `color`, `position`,
`category_sort`, `access`, `status`, autoría, fechas y `version`.

`access` contiene:

- `mode`: `open` o `restricted`;
- `grants`: lista de `{subject_type, subject_id, role}` para `user` o `api_client`;
- una combinación de tipo e identificador sólo puede aparecer una vez.

El rol efectivo es el mínimo entre el rol global y la concesión. Si falta `access` por proceder
de `0.4.0` o anterior, se aplica `{mode: open, grants: []}` sin reescribir el dato. Si el campo
existe pero es inválido, se normaliza de forma conservadora a una política restringida vacía.
La política forma parte de la versión de la biblioteca, la auditoría y el bundle HA 6.

Una biblioteca solo se puede eliminar cuando no contiene categorías ni documentos vivos.

## Categoría

Campos principales: `id`, `library_id`, `parent_id`, `name`, `description`, `position`,
`status`, autoría, fechas y `version`.

Invariantes:

- el padre pertenece a la misma biblioteca;
- una categoría nunca es ancestro de sí misma;
- una categoría con hijos o documentos no se elimina accidentalmente;
- `parent_id=null` significa raíz, no ausencia de organización.

Las posiciones se interpretan entre categorías hermanas. El modo de la biblioteca puede
ser manual o alfabético; cambiar a alfabético no elimina el orden manual guardado.

## Documento

El contenido vive en `docs/{id}.md`; los metadatos en `meta/{id}.json`.

Campos principales: `id`, `library_id`, `category_id`, `title`, `slug`, `summary`, `tags`,
`position`, `status`, autoría, fechas y `version`.

`status` distingue `active`, `archived` y `deleted`. Archivar no mueve contenido al vault.
Eliminar sí conserva una copia recuperable y actualiza el documento a tombstone.

## Imagen documental

Los binarios viven en `images/{document_id}/` junto a metadatos que conservan identificador,
nombre original, tipo MIME, tamaño, autoría, fecha y versión. El Markdown utiliza una URL
autenticada estable; el archivo nunca se publica como estático. Al eliminar el documento,
sus imágenes viajan al mismo elemento del vault y se restauran con él.

## Cuenta

La cuenta vive en `auth/users/{id}.json`. Se replica con la misma revisión lógica que el
catálogo para que un failover acepte las mismas credenciales. Contiene identidad, rol,
estado, hash `scrypt`, versión de sesión, favoritos personales y configuración TOTP. El
secreto TOTP está cifrado;
los códigos de recuperación sólo existen como hashes y se eliminan al usarlos.

La representación pública excluye el hash de contraseña y la estructura TOTP. Es la única
representación permitida en respuestas y eventos de auditoría. Las cuentas no se proyectan
al repositorio Git.

No se permite degradar ni desactivar la última cuenta humana activa con `full_control`.
Las contraseñas restablecidas por un administrador obligan a cambiarlas en el siguiente acceso.

`favorites` es un mapa privado de identificador documental a fecha de marcado. No modifica
el documento ni los favoritos de otras personas. Se replica y audita como preferencia de
cuenta, pero no se proyecta al repositorio Git documental.

## Cliente API

Vive en `auth/api-clients/{id}.json`. Contiene nombre, descripción, rol, estado,
caducidad opcional, prefijo identificativo, HMAC del token y último uso. El token completo
solo existe en la respuesta de alta o rotación; no puede recuperarse desde el servidor.

Los estados son `active`, `disabled` y `revoked`. Revocar elimina el hash utilizable y es
irreversible; rotar invalida la credencial anterior y emite una nueva. Un cliente API con
`full_control` puede operar sobre contenido, pero nunca administrar identidades.

## Versión y conflicto

```json
{
  "clock": 42,
  "timestamp": "2026-08-20T15:00:00Z",
  "node": "node-a"
}
```

Las comparaciones usan reloj, fecha y nodo. Una entidad remota solo sustituye a la local si
su clave de versión es mayor. La operación completa conserva además `event_id` y
`operation_id` para auditoría e idempotencia futura.

## Próximas entidades

Grupos de permisos, fragmentos, adjuntos no visuales y revisiones publicadas
se incorporarán sobre identificadores estables. No se añadirán como
campos inconexos en documentos.
