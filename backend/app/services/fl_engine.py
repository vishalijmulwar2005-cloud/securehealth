"""Port of the verified console's federated-learning engine (server/fl.js).

Preserved behavior (regression-tested against the original JavaScript):
logistic regression from scratch, local training per hospital on CONSENTING
patients only, L2 clip, Gaussian noise, sample-weighted FedAvg, truthful
epsilon accounting (delta = 1e-5), SHA-256 model/update fingerprints.
Raw patient records NEVER leave the hospital — participants carry counts,
metrics and fingerprints only (spec invariant, enforced by shape below).
"""
import math
import time

from ..core.hashing import mulberry32, randn, sha256_hex

DELTA = 1e-5

DISEASES = [
    {"key": "heart", "name": "Heart disease", "features": ["age", "bmi", "systolicBP", "cholesterol", "fastingGlucose", "smoker"]},
    {"key": "diabetes", "name": "Type 2 diabetes", "features": ["age", "bmi", "fastingGlucose", "fastingInsulin", "familyHistory", "systolicBP"]},
    {"key": "stroke", "name": "Stroke", "features": ["age", "hypertension", "heartDisease", "glucose", "bmi", "smoker"]},
    {"key": "kidney", "name": "Chronic kidney disease", "features": ["age", "systolicBP", "creatinine", "haemoglobin", "urineACR", "diabetic"]},
]
DISEASE_KEYS = [d["key"] for d in DISEASES]
DISEASE_BY_KEY = {d["key"]: d for d in DISEASES}


def disease_by_key(k: str):
    return DISEASE_BY_KEY.get(k)


def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def l2(v) -> float:
    return math.sqrt(sum(x * x for x in v))


def epsilon_per_round(sigma: float) -> float:
    """Gaussian mechanism, basic composition across rounds (verified formula)."""
    if not sigma or sigma <= 0:
        return 0.0
    return math.sqrt(2.0 * math.log(1.25 / DELTA)) / sigma


def compute_scaler(disease_key: str, patients: list) -> dict:
    """Scaler computed once from CONSENTING patients' labeled records only."""
    d = disease_by_key(disease_key)
    rows = [p for p in patients if p["consent_research"] and p["features"].get(disease_key)]
    n = max(len(rows), 1)
    m = len(d["features"])
    mean = [0.0] * m
    sd = [0.0] * m
    for p in rows:
        f = p["features"][disease_key]
        for j in range(m):
            mean[j] += f[j]
    for j in range(m):
        mean[j] /= n
    for p in rows:
        f = p["features"][disease_key]
        for j in range(m):
            sd[j] += (f[j] - mean[j]) ** 2
    for j in range(m):
        sd[j] = math.sqrt(sd[j] / n)
        if sd[j] < 1e-9:
            sd[j] = 1.0
    return {"mean": mean, "sd": sd}


def standardize(f, scaler):
    return [(x - scaler["mean"][j]) / scaler["sd"][j] for j, x in enumerate(f)]


def _to_xy(disease_key: str, patients: list, scaler: dict):
    X, y = [], []
    for p in patients:
        if not p["consent_research"] or p["features"].get(disease_key) is None:
            continue
        X.append([*standardize(p["features"][disease_key], scaler), 1.0])  # + bias
        y.append(p["labels"][disease_key])
    return X, y


def _train_local(X, y, w0, epochs, lr, rng):
    w = list(w0)
    n, d = len(X), len(w)
    batch_size = min(32, n)
    for _ in range(epochs):
        idx = list(range(n))
        for i in range(n - 1, 0, -1):  # Fisher-Yates, same direction as source
            j = int(rng() * (i + 1))
            idx[i], idx[j] = idx[j], idx[i]
        for s in range(0, n, batch_size):
            batch = idx[s:s + batch_size]
            grad = [0.0] * d
            for i in batch:
                err = sigmoid(dot(w, X[i])) - y[i]
                for j in range(d):
                    grad[j] += err * X[i][j]
            for j in range(d):
                w[j] -= (lr / len(batch)) * grad[j]
    return w


def _evaluate(w, X, y) -> dict:
    tp = tn = fp = fn = 0
    loss = 0.0
    for i in range(len(X)):
        p = sigmoid(dot(w, X[i]))
        loss += -(y[i] * math.log(p + 1e-12) + (1 - y[i]) * math.log(1 - p + 1e-12))
        pred = 1 if p >= 0.5 else 0
        if pred == 1 and y[i] == 1:
            tp += 1
        elif pred == 0 and y[i] == 0:
            tn += 1
        elif pred == 1:
            fp += 1
        else:
            fn += 1
    n = len(X) or 1
    accuracy = (tp + tn) / n
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0
    return {"accuracy": accuracy, "loss": loss / n, "precision": precision,
            "recall": recall, "f1": f1, "n": len(X)}


def model_fingerprint(disease_key: str, weights) -> str:
    return sha256_hex(disease_key + "|" + ",".join(format(w, ".10f") for w in weights))


def update_fingerprint(hospital_code: str, values) -> str:
    return sha256_hex(hospital_code + "|" + ",".join(format(v, ".10f") for v in values))


def fresh_model(disease_key: str) -> dict:
    dim = len(disease_by_key(disease_key)["features"]) + 1  # features + bias
    return {"weights": [0.0] * dim, "version": 0, "cumulative_epsilon": 0.0,
            "fingerprint": None, "prev_fingerprint": None, "scaler": None}


def run_round(*, disease_key: str, config: dict, model: dict, patients: list,
              active_hospitals: list, seed: int | None = None) -> dict:
    """One federated round — faithful port of fl.js runRound.

    `patients` items: {hospital: code, consent_research: bool,
    features: {disease: [...]}, labels: {disease: 0|1}} — locally held synthetic
    records. Nothing leaves except counts, metrics and fingerprints.
    """
    t0 = time.time()
    w_global = list(model["weights"])
    rng = mulberry32(seed if seed is not None else int(time.time() * 1000) % 2147483647)

    if model.get("scaler") is None:
        model["scaler"] = compute_scaler(disease_key, patients)

    participants = []
    total_samples = 0
    privatized = []

    for h in active_hospitals:
        hp = [p for p in patients if p["hospital"] == h["code"]]
        X, y = _to_xy(disease_key, hp, model["scaler"])
        if not X:
            continue
        w_local = _train_local(X, y, w_global, config["epochs"], config["learningRate"], rng)
        local_eval = _evaluate(w_local, X, y)
        delta = [v - w_global[j] for j, v in enumerate(w_local)]
        norm = l2(delta)
        clipped = False
        d_clip = delta
        if config["dpEnabled"] and norm > config["clipNorm"]:
            clipped = True
            d_clip = [v * config["clipNorm"] / norm for v in delta]
        d_priv = d_clip
        if config["dpEnabled"]:
            d_priv = [v + randn(rng) * config["noiseMultiplier"] * config["clipNorm"] for v in d_clip]
        participants.append({
            "hospital": h["code"], "samples": len(X),
            "localAccuracy": round(local_eval["accuracy"], 4),
            "localLoss": round(local_eval["loss"], 4),
            "updateNorm": round(norm, 4), "clipped": clipped,
            "updateHash": update_fingerprint(h["code"], d_priv),
        })
        total_samples += len(X)
        privatized.append({"n": len(X), "d_priv": d_priv})

    # FedAvg: sample-weighted average of privatized updates.
    dim = len(w_global)
    w_new = list(w_global)
    if total_samples > 0:
        for j in range(dim):
            agg = sum((p["n"] / total_samples) * p["d_priv"][j] for p in privatized)
            w_new[j] = w_global[j] + agg

    # Evaluate on the pooled CONSENTING set (v3.1 correction, preserved).
    Xe, ye = _to_xy(disease_key, patients, model["scaler"])
    metrics = _evaluate(w_new, Xe, ye)

    eps = epsilon_per_round(config["noiseMultiplier"]) if config["dpEnabled"] else 0.0
    model["prev_fingerprint"] = model["fingerprint"]
    model["weights"] = w_new
    model["version"] += 1
    model["cumulative_epsilon"] += eps
    model["fingerprint"] = model_fingerprint(disease_key, w_new)

    return {
        "participants": participants,
        "total_samples": total_samples,
        "metrics": {**metrics, "epsilon": round(eps, 4),
                    "cumulativeEpsilon": round(model["cumulative_epsilon"], 4)},
        "model_hash": model["fingerprint"],
        "previous_model_hash": model["prev_fingerprint"],
        "version": model["version"],
        "duration_ms": int((time.time() - t0) * 1000),  # real elapsed time — never simulated
    }


def predict_risk(disease_key: str, model: dict, raw_features: list):
    if model.get("scaler") is None or model["version"] == 0:
        return None
    x = [*standardize(raw_features, model["scaler"]), 1.0]
    return sigmoid(dot(model["weights"], x))
