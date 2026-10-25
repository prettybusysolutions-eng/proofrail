"""Provider-side authorization: real localhost HTTP writes must require pinned capabilities.

Synthetic keys and provider stores only. Default insecure simulator mode stays
available for fault-injection exercises, but enforce mode rejects direct writes.
"""
from __future__ import annotations

import base64
import copy
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from fixtures import World
from provider_simulator import FIELDS, serve
from proofrail_gateway import expected_parameters


def post(url, tenant, body, *, key="envelope-digest-1", client="gateway-tenant-a", capability=None):
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": key,
        "X-Client-Id": client,
    }
    if capability is not None:
        headers["X-ProofRail-Capability"] = capability
    req = urllib.request.Request(
        url + f"/v1/tenants/{tenant}/work-orders",
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def post_admin(url, path, payload):
    req = urllib.request.Request(url + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=5)
    return err.value.code


@pytest.fixture
def enforced_provider(tmp_path):
    # This is provider-owned trust configuration, not a key obtained from the
    # incoming request or its untrusted evidence bundle.
    provider_keys = {}
    server, state = serve(tmp_path / "provider-enforced.sqlite3", trusted_gateways=provider_keys)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        world = World(tmp_path / "world", url, provider_timeout=2.0)
        for tenant in ("tenant-a", "tenant-b"):
            state.trusted_gateways[tenant] = world.ids[f"gateway-{tenant[-1]}"].principal.describe()
        yield world, state, url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_enforced_provider_rejects_direct_http_bypass_and_admin_mutation(enforced_provider):
    world, state, url = enforced_provider
    body = {field: f"test-{field}" for field in FIELDS}
    body["scope_revision"] = 1
    body["max_cost"] = 32000

    code, reason = post(url, "tenant-a", body)
    assert code == 403 and reason["error"] == "capability_required"
    code, reason = post(url, "tenant-a", body, capability="not-a-valid-token")
    assert code == 403 and reason["error"] == "invalid_capability"
    assert post_admin(url, "/admin/fault", {"mode": "no_idempotency"}) == 403
    assert post_admin(url, "/admin/status", {"tenant_id": "tenant-a",
                                            "work_order_id": "WO-00001",
                                            "status": "completed"}) == 403
    assert state.count() == 0


def test_real_gateway_consumes_then_provider_checks_exact_signed_scope(enforced_provider):
    world, state, url = enforced_provider
    problem = world.report("a")
    plan, approval = world.plan_and_approve(problem, "a")
    envelope = world.authorize(problem, plan, approval, "a")

    result = world.pilot.admit("tenant-a", envelope)
    assert result["authority_state"] == "RECONCILED"
    assert state.count() == 1

    params = expected_parameters(problem, plan, approval, envelope["envelope_id"])
    gateway = world.pilot.gateways["tenant-a"]
    token = gateway._provider_capability("tenant-a", envelope, params)

    # A valid capability can be replayed as an identical idempotent HTTP
    # request; the provider returns the original order, never creates a second.
    status, order = post(url, "tenant-a", params, key=envelope["record_hash"],
                         client=gateway.provider.client_id, capability=token)
    assert status == 200 and order["tenant_id"] == "tenant-a" and state.count() == 1

    for override in [
        {"tenant": "tenant-b"},
        {"client": "untrusted-caller"},
        {"key": "another-envelope"},
        {"body": {**params, "area_id": "UNAUTHORIZED"}},
    ]:
        code, reason = post(
            url, override.get("tenant", "tenant-a"), override.get("body", params),
            key=override.get("key", envelope["record_hash"]),
            client=override.get("client", gateway.provider.client_id),
            capability=token,
        )
        assert code == 403, (override, code, reason)
        assert state.count() == 1

    # Malformed but otherwise correctly scoped signed-record content must
    # fail cryptographic verification, not be accepted as a client header.
    forged = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    forged["signature"]["value"] = "A" * 86
    forged_token = base64.urlsafe_b64encode(
        json.dumps(forged, separators=(",", ":")).encode()).rstrip(b"=").decode()
    code, reason = post(url, "tenant-a", params, key=envelope["record_hash"],
                        client=gateway.provider.client_id, capability=forged_token)
    assert code == 403 and reason["error"] == "invalid_capability"
    assert state.count() == 1

    # Provider pins are authoritative. A valid gateway signature fails once
    # the provider's separately configured trusted key disagrees with it.
    original_pin = state.trusted_gateways["tenant-a"]["public_key"]
    try:
        state.trusted_gateways["tenant-a"]["public_key"] = (
            world.ids["gateway-b"].principal.public_key
        )
        code, reason = post(url, "tenant-a", params, key=envelope["record_hash"],
                            client=gateway.provider.client_id, capability=token)
        assert code == 403 and reason["error"] == "invalid_capability"
        assert state.count() == 1
    finally:
        state.trusted_gateways["tenant-a"]["public_key"] = original_pin

    # A real gateway signature over stale authority is still expired at the
    # provider. Gateway identity alone cannot override the wall-clock bound.
    signed = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    unsigned = {k: copy.deepcopy(v) for k, v in signed.items()
                if k not in ("record_hash", "signature")}
    before = datetime.now(timezone.utc) - timedelta(minutes=15)
    unsigned["issued_at"] = before.strftime("%Y-%m-%dT%H:%M:%SZ")
    unsigned["expires_at"] = (before + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_signature = gateway.identity.sign(unsigned)
    stale_token = base64.urlsafe_b64encode(
        json.dumps(old_signature, separators=(",", ":")).encode()).rstrip(b"=").decode()
    code, reason = post(url, "tenant-a", params, key=envelope["record_hash"],
                        client=gateway.provider.client_id, capability=stale_token)
    assert code == 403 and reason["error"] == "capability_expired_or_future"
    assert state.count() == 1
