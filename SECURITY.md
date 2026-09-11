# Seguridad

RTFM almacena documentación privada, cuentas, secretos TOTP cifrados, tokens API con HMAC,
auditoría y una proyección Git. El volumen `/data` debe considerarse información sensible y
quedar fuera de repositorios, copias públicas e imágenes.

## Reglas de despliegue

- Publica la interfaz mediante HTTPS y activa `PUBLIC_SCHEME=https` y
  `SESSION_COOKIE_SECURE=true` antes de exponerla fuera de una LAN o VPN confiable.
- Genera `APP_TOKEN`, `SESSION_SECRET`, `REPLICATION_TOKEN` y `KEEPALIVED_API_KEY` de forma
  independiente. Prefiere `*_FILE` en Compose; en Unraid usa exclusivamente los mounts `ro`
  documentados en [`docs/UNRAID-INSTALLATION.md`](docs/UNRAID-INSTALLATION.md). No los
  incluyas en diagnósticos.
- Retira `APP_TOKEN` después de crear y replicar la cuenta propietaria si no necesitas el
  cliente API heredado.
- No cambies `SESSION_SECRET` sin una rotación planificada: protege sesiones, tokens y TOTP.
- Usa HTTPS entre pares. HTTP remoto requiere un opt-in explícito y expone el token de réplica.
- Restringe el puerto 7400 y los endpoints internos a nodos y proxies autorizados.
- Conserva `/data` con permisos para UID/GID `10001` y realiza copias verificadas.
- Fija la imagen por versión y registra el digest usado en cada instalación.
- No uses `ROLE_MODE=active` en más de un nodo de la misma instalación.

## Comunicación de vulnerabilidades

En el repositorio público utiliza **Security > Report a vulnerability** para abrir un aviso
privado de GitHub. Si ese canal no estuviera disponible, contacta al mantenedor por un medio
privado antes de compartir detalles. No adjuntes bases documentales, bundles de réplica,
contenido de `/data`, variables de entorno, logs con topología ni credenciales a un issue
público.
