# Arquitectura de la aplicación

## Unidad de despliegue

RTFM se entrega como un único contenedor. El Dockerfile tiene dos etapas:

1. Node compila React y TypeScript a recursos estáticos.
2. Python ejecuta FastAPI, sirve la interfaz compilada, la API, Git y la réplica.

Node y las dependencias de construcción no forman parte de la imagen final.

## Capas

```text
navegador
  └── React Router · páginas y componentes
          └── /api/v1
                └── routers FastAPI por dominio
                      ├── autenticación y sesión
                      ├── perfil, contraseña y TOTP
                      ├── usuarios, roles y clientes API
                      ├── bibliotecas y categorías
                      ├── documentos
                      ├── registros
                      ├── sistema y HA
                      └── réplica interna
                            └── DocumentStore
                                  ├── cuentas y seguridad replicables
                                  ├── Markdown + JSON atómico
                                  ├── auditoría JSONL
                                  ├── vault + tombstones
                                  └── proyección Git
```

`app/main.py` compone la aplicación. No contiene el dominio documental. Los routers viven
en `app/api/routes/`, los esquemas de entrada en `app/api/schemas.py`, la sesión firmada en
`app/auth.py` y la persistencia en `app/storage.py`.

## Navegación

La interfaz usa rutas reales con historial del navegador y acceso directo. Recargar
`/libraries/{id}` o `/documents/{id}` devuelve el mismo frontend y React resuelve la página.
Los logs no se cargan en el dashboard: pertenecen a `/settings/logs`.

## Rol del nodo

- `active`: la VIP está presente y se aceptan mutaciones.
- `passive`: el servicio responde y recibe réplicas, pero muestra solo su estado.
- `unknown`: no puede decidir con seguridad y bloquea escrituras.

La detección se ejecuta en cada operación relevante. La red `host` permite observar la IP
real del servidor. `ROLE_MODE=active|passive` queda reservado a instalaciones aisladas,
pruebas y diagnóstico.

## Aprovisionamiento de la IP flotante

Cada réplica presenta una clave de aplicación a Keepalived y repite la misma operación
idempotente `POST /api/claims`. La respuesta aporta la VIP efectiva que usa la detección de
rol. La reclamación se confirma durante el ciclo de fondo y se conserva al apagar un nodo,
porque pertenece a la instalación completa y no a una réplica concreta.

El conector no persiste ni expone la credencial. HTTPS se verifica con las autoridades del
sistema o con `KEEPALIVED_CA_FILE`; HTTP solo se admite automáticamente contra loopback y
requiere un opt-in explícito hacia otros hosts. `FLOATING_IP` es un fallback manual, no una
segunda autoridad cuando la API responde correctamente.

## Catálogo recursivo

Una biblioteca es una raíz independiente. Las categorías usan `parent_id`; `null` significa
raíz de biblioteca. Antes de crear o mover se valida que el padre pertenezca a la misma
biblioteca y que la cadena de ancestros no alcance la propia categoría. No existe una
profundidad fijada en código.

Los documentos conservan `library_id` y `category_id`. `category_id=null` representa un
documento situado directamente en la biblioteca.

Cada biblioteca contiene una política `access` aditiva. `mode=open` aplica el rol global de la
identidad; `mode=restricted` exige una concesión para `user` o `api_client`. El rol efectivo es
el menor entre rol global y concesión. Las cuentas humanas con control total constituyen la vía
de recuperación. Las lecturas públicas de biblioteca sólo incluyen `access_mode` y rol
efectivo; la lista de identidades y concesiones queda en el endpoint administrativo.

## Replicación

El activo envía un bundle reconciliable cada cinco minutos. El esquema 6 incluye
bibliotecas —incluida su política de acceso—, categorías, cuentas, clientes API, documentos,
imágenes privadas, vault y auditoría. Cada entidad tiene revisión lógica,
fecha y nodo. Se aplica únicamente una revisión más nueva; los tombstones compiten con la
misma regla que las ediciones.

El transporte exige un token independiente, sólo admite como origen un nodo declarado en
`PEERS`, valida el esquema y acota el tamaño de peticiones y respuestas. Las URLs HTTP de
hosts remotos se rechazan salvo opt-in explícito; el modo normal usa HTTPS y puede verificar
una CA privada mediante `REPLICATION_CA_FILE`.

Durante la actualización progresiva se mantienen los endpoints `/api/internal/*`. Un nodo
v0.0.6 ignora el catálogo nuevo, pero conserva los metadatos documentales hasta recibir la
versión actualizada.

## Exportación de documentos a PDF

La vista de lectura ofrece la exportación de cualquier documento mediante el motor de
impresión del navegador. Antes de abrir el diálogo espera las imágenes privadas ya
autenticadas y los diagramas Mermaid renderizados en el DOM. Una hoja de impresión A4
oculta la interfaz del portal y adapta tablas, bloques de código, imágenes y diagramas.

El PDF se genera en el equipo del usuario: el contenido no se envía a un conversor
externo y RTFM no necesita otro proceso, servicio ni contenedor para esta función.

## Historial Git

Git es una proyección portable, no el bloqueo transaccional. Registra:

- `catalog/libraries/*.json`;
- `catalog/categories/*.json`;
- `documents/{id}/metadata.json`;
- `documents/{id}/content.md` mientras el contenido no esté eliminado.
- `documents/{id}/images/*` con binario y metadatos mientras el documento no esté eliminado.

La auditoría JSONL sigue siendo la fuente operativa para búsquedas, filtros y réplica.

## Límites de v0.4.9

- `APP_TOKEN` continúa habilitado como compatibilidad heredada hasta completar su retirada;
- las concesiones son individuales; todavía no existen grupos ni directorios externos;
- Mermaid se representa de forma local y estricta; los fragmentos reutilizables entre
  documentos siguen pendientes;
- la ordenación se persiste, pero la interacción drag-and-drop queda pendiente;
- la réplica sigue enviando snapshots completos y deberá evolucionar a lotes por cursor.
