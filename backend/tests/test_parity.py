"""Regression-parity gate: the Python FL/ledger port produces IDENTICAL
results to the original verified JavaScript implementation (server/util.js,
server/fl.js, server/blockchain.js) for the same inputs.

This is the 'regression-safe integration' evidence required by the spec —
the verified algorithms were ported, not changed.
"""
import json
import math
import shutil
import subprocess

import pytest

from app.core.hashing import mulberry32, sha256_hex
from app.services.fl_engine import epsilon_per_round

CONSOLE_SERVER = r"C:\Users\visha\Downloads\securehealth\securehealth\server"

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not available")

NODE_SCRIPT = f"""
Promise.all([
  import('file:///{CONSOLE_SERVER.replace(chr(92), '/')}/util.js'),
  import('file:///{CONSOLE_SERVER.replace(chr(92), '/')}/fl.js'),
]).then(([u, fl]) => {{
  const r = u.mulberry32(20260924);
  const seq = []; for (let i = 0; i < 5; i++) seq.push(r());
  const ts = 1727000000000, data = {{ note: 'x', n: 1 }};
  const hash = u.sha256Hex([0, ts, 'GENESIS', JSON.stringify(data), '0'.repeat(64), 42].join('|'));
  console.log(JSON.stringify({{ seq, eps: fl.epsilonPerRound(1.0), eps2: fl.epsilonPerRound(2.0), hash }}));
}})
"""


def _node_reference() -> dict:
    out = subprocess.run([NODE, "-e", NODE_SCRIPT], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_prng_sequence_identical_to_verified_js():
    ref = _node_reference()
    rng = mulberry32(20260924)
    py_seq = [rng() for _ in range(5)]
    for py, js in zip(py_seq, ref["seq"]):
        assert abs(py - js) < 1e-12


def test_epsilon_formula_identical_to_verified_js():
    ref = _node_reference()
    assert abs(epsilon_per_round(1.0) - ref["eps"]) < 1e-12
    assert abs(epsilon_per_round(2.0) - ref["eps2"]) < 1e-12


def test_block_hash_formula_identical_to_verified_js():
    ref = _node_reference()
    data = {"note": "x", "n": 1}
    data_json = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    py_hash = sha256_hex("|".join(["0", "1727000000000", "GENESIS", data_json,
                                   "0" * 64, "42"]))
    assert py_hash == ref["hash"]


def test_sanity_console_epsilon_display():
    # The deployed console shows "ε ≈ 4.84" per round at σ=1.0.
    assert abs(epsilon_per_round(1.0) - 4.84) < 0.01
