"""Three-node split-brain conflict and stale-node reconciliation gate."""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


TOKEN = os.environ["APP_TOKEN"]
CONTROL_FILE = Path("/control/state.json")
NODES = {
    "node-a": "http://node-a:7400",
    "node-b": "http://node-b:7400",
    "node-c": "http://node-c:7400",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def call(
    node: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    expected: int = 200,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        NODES[node] + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "X-Actor": "ha-conflict-gate",
            "Content-Type": "application/json",
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=15)  # nosec B310
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:1000]
        raise AssertionError(
            f"{node} {method} {path}: HTTP {error.code}, expected {expected}: {body}"
        ) from error
    with response:
        require(response.status == expected, f"{node} {path}: unexpected HTTP {response.status}")
        raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else {}


def document(node: str, document_id: str) -> dict[str, Any]:
    return call(node, "GET", f"/api/v1/documents/{document_id}")


def sync_a() -> dict[str, Any]:
    response = call("node-a", "POST", "/api/v1/sync")
    require(response.get("status") == "completed", "manual sync was not completed")
    peers = response.get("peers") or {}
    require(set(peers) == {"node-b", "node-c"}, "manual sync did not address both peers")
    require(all(item.get("ok") is True for item in peers.values()), "a peer rejected sync")
    return response


def version_key(document_payload: dict[str, Any]) -> tuple[int, str, str]:
    version = document_payload["meta"]["version"]
    return int(version["clock"]), str(version["timestamp"]), str(version["node"])


def seed() -> None:
    library = call(
        "node-a",
        "POST",
        "/api/v1/libraries",
        {"name": "HA conflict gate library"},
        expected=201,
    )
    created = call(
        "node-a",
        "POST",
        "/api/v1/documents",
        {
            "library_id": library["id"],
            "title": "Deliberate concurrent conflict",
            "content": "# Shared seed\n\nBefore the stale interval.",
        },
        expected=201,
    )
    sync_a()
    document_id = str(created["meta"]["id"])
    snapshots = [document(node, document_id) for node in NODES]
    require(len({item["content"] for item in snapshots}) == 1, "seed content did not replicate")
    require(
        len({version_key(item) for item in snapshots}) == 1,
        "seed version did not replicate exactly",
    )
    CONTROL_FILE.write_text(
        json.dumps(
            {
                "document_id": document_id,
                "seed_content": created["content"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def conflict() -> None:
    state = json.loads(CONTROL_FILE.read_text(encoding="utf-8"))
    document_id = state["document_id"]
    contents = {
        "node-a": "# Concurrent winner candidate A\n\nWritten while node C is offline.",
        "node-b": "# Concurrent winner candidate B\n\nWritten while node C is offline.",
    }
    barrier = threading.Barrier(3)
    responses: dict[str, dict[str, Any]] = {}
    failures: list[BaseException] = []

    def update(node: str) -> None:
        try:
            barrier.wait(timeout=10)
            responses[node] = call(
                node,
                "PATCH",
                f"/api/v1/documents/{document_id}",
                {"content": contents[node]},
            )
        except BaseException as error:  # pragma: no cover - propagated below
            failures.append(error)

    threads = [threading.Thread(target=update, args=(node,)) for node in ("node-a", "node-b")]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=10)
    for thread in threads:
        thread.join(timeout=20)
    require(not failures, f"concurrent write failed: {failures}")
    require(set(responses) == {"node-a", "node-b"}, "one concurrent write did not finish")
    require(
        responses["node-a"]["content"] != responses["node-b"]["content"],
        "the isolated writers did not diverge",
    )
    winner_node = max(responses, key=lambda node: version_key(responses[node]))
    state.update(
        {
            "winner_node": winner_node,
            "winner_content": responses[winner_node]["content"],
            "winner_version": list(version_key(responses[winner_node])),
        }
    )
    CONTROL_FILE.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")


def reconcile() -> None:
    state = json.loads(CONTROL_FILE.read_text(encoding="utf-8"))
    document_id = state["document_id"]
    stale = document("node-c", document_id)
    require(stale["content"] == state["seed_content"], "node C was not demonstrably stale")

    sync_a()
    sync_a()
    snapshots = {node: document(node, document_id) for node in NODES}
    require(
        {item["content"] for item in snapshots.values()} == {state["winner_content"]},
        "the three nodes did not converge on deterministic content",
    )
    require(
        {version_key(item) for item in snapshots.values()} == {tuple(state["winner_version"])},
        "the three nodes did not converge on the exact winning version",
    )
    print(
        "HA conflict gate: concurrent divergence, deterministic merge and stale-node rejoin OK"
    )


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) == 2 else ""
    actions = {"seed": seed, "conflict": conflict, "reconcile": reconcile}
    action = actions.get(phase)
    if action is None:
        print("usage: ha_conflict_rejoin_smoke.py seed|conflict|reconcile", file=sys.stderr)
        return 2
    action()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
