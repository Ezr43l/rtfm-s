from __future__ import annotations


ROLE_READER = "reader"
ROLE_OPERATOR = "operator"
ROLE_FULL_CONTROL = "full_control"

LIBRARY_ACCESS_OPEN = "open"
LIBRARY_ACCESS_RESTRICTED = "restricted"
LIBRARY_ACCESS_MODES = (LIBRARY_ACCESS_OPEN, LIBRARY_ACCESS_RESTRICTED)
LIBRARY_SUBJECT_TYPES = ("user", "api_client")

ACCESS_ROLES = (ROLE_READER, ROLE_OPERATOR, ROLE_FULL_CONTROL)
ROLE_LEVEL = {role: level for level, role in enumerate(ACCESS_ROLES)}


def normalize_access_role(value: object) -> str:
    """Map historical owner/admin values to the current access model."""
    role = str(value or "").strip().casefold()
    if role in {"owner", "admin", "administrator", ROLE_FULL_CONTROL}:
        return ROLE_FULL_CONTROL
    if role == ROLE_OPERATOR:
        return ROLE_OPERATOR
    return ROLE_READER


def validate_access_role(value: object) -> str:
    role = str(value or "").strip().casefold()
    if role not in ACCESS_ROLES:
        raise ValueError("El nivel de acceso indicado no es valido")
    return role


def role_allows(current: object, required: str) -> bool:
    return ROLE_LEVEL[normalize_access_role(current)] >= ROLE_LEVEL[required]


def normalize_library_access(value: object, *, legacy_default_open: bool = True) -> dict:
    """Return a deterministic, least-privilege library access policy.

    Libraries written before 0.4.1 have no ``access`` member and remain open so the
    patch upgrade cannot lock out existing installations. An explicitly malformed
    policy is instead treated as restricted with no grants.
    """
    if value is None:
        return {
            "mode": LIBRARY_ACCESS_OPEN if legacy_default_open else LIBRARY_ACCESS_RESTRICTED,
            "grants": [],
        }
    if not isinstance(value, dict):
        return {"mode": LIBRARY_ACCESS_RESTRICTED, "grants": []}
    mode = str(value.get("mode") or "").strip().casefold()
    if mode not in LIBRARY_ACCESS_MODES:
        return {"mode": LIBRARY_ACCESS_RESTRICTED, "grants": []}

    # A duplicated subject is resolved to its lowest valid role. That way a
    # malformed replicated entity cannot accidentally gain more privilege.
    grants_by_subject: dict[tuple[str, str], str] = {}
    raw_grants = value.get("grants")
    if not isinstance(raw_grants, list):
        raw_grants = []
    for raw in raw_grants:
        if not isinstance(raw, dict):
            continue
        subject_type = str(raw.get("subject_type") or "").strip().casefold()
        subject_id = str(raw.get("subject_id") or "").strip()
        role = str(raw.get("role") or "").strip().casefold()
        if subject_type not in LIBRARY_SUBJECT_TYPES or not subject_id or role not in ACCESS_ROLES:
            continue
        key = (subject_type, subject_id)
        previous = grants_by_subject.get(key)
        if previous is None or ROLE_LEVEL[role] < ROLE_LEVEL[previous]:
            grants_by_subject[key] = role
    grants = [
        {"subject_type": subject_type, "subject_id": subject_id, "role": role}
        for (subject_type, subject_id), role in sorted(grants_by_subject.items())
    ]
    return {"mode": mode, "grants": grants}


def validate_library_access(mode: object, grants: object) -> dict:
    normalized_mode = str(mode or "").strip().casefold()
    if normalized_mode not in LIBRARY_ACCESS_MODES:
        raise ValueError("El modo de acceso de la biblioteca no es valido")
    if not isinstance(grants, list):
        raise ValueError("La lista de permisos de la biblioteca no es valida")
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in grants:
        if not isinstance(raw, dict):
            raise ValueError("Hay una concesion de biblioteca no valida")
        subject_type = str(raw.get("subject_type") or "").strip().casefold()
        subject_id = str(raw.get("subject_id") or "").strip()
        if subject_type not in LIBRARY_SUBJECT_TYPES or not subject_id:
            raise ValueError("El destinatario del permiso de biblioteca no es valido")
        key = (subject_type, subject_id)
        if key in seen:
            raise ValueError("Una identidad no puede aparecer dos veces en la misma biblioteca")
        seen.add(key)
        normalized.append({
            "subject_type": subject_type,
            "subject_id": subject_id,
            "role": validate_access_role(raw.get("role")),
        })
    normalized.sort(key=lambda item: (item["subject_type"], item["subject_id"]))
    return {"mode": normalized_mode, "grants": normalized}


def effective_library_role(
    global_role: object,
    identity_type: object,
    user_id: object,
    api_client_id: object,
    library: dict,
) -> str | None:
    """Resolve access with the global role acting as a hard privilege ceiling."""
    global_access = normalize_access_role(global_role)
    identity_kind = str(identity_type or "").strip().casefold()

    # A human full-control account is the recovery authority and cannot be
    # accidentally locked out of an installation by a bad library policy.
    if identity_kind == "person" and user_id and global_access == ROLE_FULL_CONTROL:
        return ROLE_FULL_CONTROL

    policy = normalize_library_access(library.get("access"))
    if policy["mode"] == LIBRARY_ACCESS_OPEN:
        return global_access

    subject_type = "user" if identity_kind == "person" else "api_client" if identity_kind == "api" else ""
    subject_id = str(user_id if subject_type == "user" else api_client_id if subject_type == "api_client" else "")
    if not subject_type or not subject_id:
        return None
    granted = next(
        (item["role"] for item in policy["grants"] if item["subject_type"] == subject_type and item["subject_id"] == subject_id),
        None,
    )
    if granted is None:
        return None
    return ACCESS_ROLES[min(ROLE_LEVEL[global_access], ROLE_LEVEL[granted])]


def library_role_allows(effective_role: str | None, required: str) -> bool:
    return effective_role is not None and ROLE_LEVEL[effective_role] >= ROLE_LEVEL[required]
