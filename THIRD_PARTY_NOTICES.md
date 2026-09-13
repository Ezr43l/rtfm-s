# Avisos de terceros

El código y la documentación propios de RTFM se distribuyen bajo Apache-2.0 conforme a
`LICENSE`. La imagen OCI es una distribución colectiva que también contiene programas,
bibliotecas y recursos web de terceros; la etiqueta OCI `org.opencontainers.image.licenses`
describe RTFM y no sustituye las licencias de esos componentes.

## Dónde se conservan los términos

- `/app/NPM_THIRD_PARTY_LICENSES.txt` contiene el inventario y los textos de licencia/NOTICE de
  todos los paquetes npm de producción instalados desde `web/package-lock.json`. El build lo
  genera de forma determinista y falla si un paquete no aporta un texto.
- `/app/PYTHON_THIRD_PARTY_LICENSES.txt` contiene el inventario y los textos suministrados por
  todas las distribuciones Python instaladas. Los originales permanecen además en sus
  directorios `*.dist-info` bajo `/usr/local/lib/python3.12/site-packages`.
- `/app/licenses/git-COPYING` y `/app/licenses/iproute2-COPYING` son copias fijadas por
  checksum de los términos upstream de Git e iproute2 incluidos en la imagen.
- Cada release adjunta SBOM SPDX separados para `linux/amd64` y `linux/arm64`, sus sumas
  SHA-256 y un archivo reproducible con las fuentes, recetas y parches correspondientes de
  ambas arquitecturas para las dependencias con licencias recíprocas, incluida MPL-2.0.

## Componentes directos principales

| Componente | Versión fijada | Licencia declarada |
| --- | --- | --- |
| RTFM (código y documentación propios) | `0.4.10` | `Apache-2.0` |
| Git (paquete Alpine) | `2.54.0-r0` | `GPL-2.0-only` |
| iproute2 (paquetes Alpine) | `7.0.0-r0` | `GPL-2.0-or-later` |
| FastAPI y dependencias Python | versiones exactas en `requirements.txt`, artefactos fijados por SHA-256 en `requirements.lock` | MIT, BSD, Apache-2.0, MIT-0 y PSF-2.0 según metadatos de cada wheel |
| React, Mermaid y dependencias web | versiones exactas en `web/package-lock.json` | inventario y textos exactos en `NPM_THIRD_PARTY_LICENSES.txt` |
| Alpine Linux y paquetes base | inventario exacto en los SBOM de release | licencias declaradas por cada APK |

Fuentes y recetas de empaquetado de los dos programas GPL usados directamente por RTFM:

- Git 2.54.0: <https://github.com/git/git/tree/v2.54.0>
- receta Alpine exacta de Git (commit `b3ed5f8f4ce6b2ef13adeaf7494557add6546bda`):
  <https://gitlab.alpinelinux.org/alpine/aports/-/tree/b3ed5f8f4ce6b2ef13adeaf7494557add6546bda/main/git>
- iproute2 7.0.0: <https://github.com/iproute2/iproute2/tree/v7.0.0>
- receta Alpine exacta de iproute2 (commit `3ee752ad0c8445c8105177cd5cebdd730789bcd8`):
  <https://gitlab.alpinelinux.org/alpine/aports/-/tree/3ee752ad0c8445c8105177cd5cebdd730789bcd8/main/iproute2>

Los enlaces facilitan la inspección, pero no reemplazan el artefacto de fuentes que debe
acompañar a cada release pública. Los avisos, autorías y condiciones de cada componente
siguen perteneciendo a sus respectivos titulares.
