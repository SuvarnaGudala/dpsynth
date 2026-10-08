"""DPSynth epsilon-DP and (epsilon, delta)-DP Synthetic Data Generator.
Supported mechanisms:
- Laplace mechanism for pure epsilon-DP (sensitivity 1)
- Gaussian mechanism for (epsilon, delta)-DP
Features:
- Joint histogram sampling (correlation preservation) & marginal sampling
- Discretization for mixed numeric and categorical schemas
- Total Variation Distance (TVD) calculation
- Per-column fidelity breakdown and cryptographic audit hashing
"""
import math
import random
import itertools
import hashlib
import time

def laplace(scale):
    """Samples from Laplace(0, scale) using inverse CDF method."""
    u = random.random() - 0.5
    return -scale * math.copysign(1, u) * math.log(1 - 2 * abs(u) + 1e-300)

def gaussian(sigma):
    """Samples from Gaussian(0, sigma) using Box-Muller transform."""
    u1 = max(1e-300, random.random())
    u2 = random.random()
    return sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

def discretize(rows, header, bins=8):
    """Discretizes numeric columns into bins and categorical columns into distinct classes."""
    cols, specs = [], []
    for j in range(len(header)):
        v = [r[j] for r in rows]
        try:
            f = [float(x) for x in v]
            lo, hi = min(f), max(f)
            w = (hi - lo) / bins if hi != lo else 1.0
            cols.append([min(int((x - lo) / w), bins - 1) for x in f])
            specs.append(("n", lo, w, bins))
        except (ValueError, TypeError):
            cats = sorted(set(str(x) for x in v))[:20]
            if not cats:
                cats = ["default"]
            cat_map = {x: i for i, x in enumerate(cats)}
            cols.append([cat_map.get(str(x), len(cats) - 1) for x in v])
            specs.append(("c", cats))
    return cols, specs

def generate_detailed(header, rows, eps, n_out, mechanism="laplace", delta=1e-5):
    """
    Synthesizes private dataset with comprehensive privacy metrics, column-level fidelity,
    and cryptographic audit checksum.
    """
    eps = max(0.0001, float(eps))
    n_out = max(1, int(n_out))
    cols, specs = discretize(rows, header)
    k = len(header)
    sizes = [s[3] if s[0] == "n" else len(s[1]) for s in specs]
    
    # Joint product space check
    joint = math.prod(sizes) <= 25000
    
    # Compute noise scale
    is_gaussian = (mechanism.lower() == "gaussian")
    if is_gaussian:
        # Gaussian mechanism scale: sigma = sqrt(2 * ln(1.25/delta)) / eps
        safe_delta = max(1e-9, min(0.01, float(delta)))
        sigma_scale = math.sqrt(2.0 * math.log(1.25 / safe_delta)) / eps
        noise_fn = lambda sens: gaussian(sens * sigma_scale)
        mech_label = f"Gaussian (ε={eps}, δ={safe_delta})"
    else:
        noise_fn = lambda sens: laplace(sens / eps)
        mech_label = f"Laplace (Pure ε={eps})"

    if joint:
        counts = {}
        for key in zip(*cols):
            counts[key] = counts.get(key, 0) + 1
        keys = list(itertools.product(*[range(s) for s in sizes]))
        w = [max(0.0, counts.get(key, 0) + noise_fn(1.0)) for key in keys] or [1.0]
        sum_w = sum(w)
        weights = [x / sum_w for x in w] if sum_w > 0 else [1.0 / len(w)] * len(w)
        picks = random.choices(keys, weights=weights, k=n_out)
        mech_type = f"joint-histogram ({'Gaussian' if is_gaussian else 'Laplace'})"
    else:
        ms = []
        for c, s in zip(cols, sizes):
            h = [max(0.0, c.count(i) + noise_fn(float(k))) for i in range(s)]
            sum_h = sum(h)
            ms.append([x / sum_h for x in h] if sum_h > 0 else [1.0 / s] * s)
        picks = list(zip(*[random.choices(range(s), weights=m, k=n_out) for s, m in zip(sizes, ms)]))
        mech_type = f"marginals ({'Gaussian' if is_gaussian else 'Laplace'})"

    # Reconstruct data from bins
    out = []
    for p in picks:
        row = []
        for sp, b in zip(specs, p):
            if sp[0] == "c":
                cats = sp[1]
                idx = min(max(0, b), len(cats) - 1)
                row.append(cats[idx])
            else:
                lo, w_step, _ = sp[1], sp[2], sp[3]
                val = lo + (b + random.random()) * w_step
                row.append(round(val, 2))
        out.append(row)

    # Discretize synthetic output to calculate Total Variation Distance
    ocols, _ = discretize(out, header)
    col_metrics = []
    tvd_list = []

    for idx, (col_name, sp, c, d, s) in enumerate(zip(header, specs, cols, ocols, sizes)):
        len_c = max(1, len(c))
        len_d = max(1, len(d))
        orig_probs = [c.count(i) / len_c for i in range(s)]
        syn_probs = [d.count(i) / len_d for i in range(s)]
        col_tvd = 0.5 * sum(abs(p1 - p2) for p1, p2 in zip(orig_probs, syn_probs))
        tvd_list.append(col_tvd)
        
        # Build distribution summary for visualization
        if sp[0] == "n":
            labels = [f"{round(sp[1] + i*sp[2], 1)}-{round(sp[1] + (i+1)*sp[2], 1)}" for i in range(min(s, 6))]
        else:
            labels = sp[1][:6]

        col_metrics.append({
            "name": col_name,
            "type": "numeric" if sp[0] == "n" else "categorical",
            "tvd": round(col_tvd, 4),
            "fidelity_pct": round(max(0.0, 1.0 - col_tvd) * 100, 1),
            "categories": labels,
            "orig_dist": [round(p * 100, 1) for p in orig_probs[:len(labels)]],
            "syn_dist": [round(p * 100, 1) for p in syn_probs[:len(labels)]]
        })

    mean_tvd = sum(tvd_list) / max(1, k)
    mean_tvd = min(1.0, max(0.0, mean_tvd))
    fidelity_score = round(max(0.0, 1.0 - mean_tvd) * 100, 1)

    # Generate Cryptographic Audit Hash (SHA-256)
    salt = "dpsynth_audit_v2"
    hash_payload = f"{time.time()}|{eps}|{mech_label}|{len(rows)}x{k}|{n_out}|{round(mean_tvd, 6)}|{salt}"
    audit_hash = hashlib.sha256(hash_payload.encode()).hexdigest()

    metrics = {
        "mean_tvd": round(mean_tvd, 4),
        "fidelity_score": fidelity_score,
        "utility_loss_pct": round(mean_tvd * 100, 2),
        "mechanism": mech_type,
        "mechanism_label": mech_label,
        "column_metrics": col_metrics,
        "audit_hash": audit_hash,
        "joint_preservation": joint
    }

    return out, mean_tvd, mech_type, metrics

def generate(header, rows, eps, n_out):
    """Original signature for backward compatibility and unit tests."""
    out, tvd, mech, _ = generate_detailed(header, rows, eps, n_out, mechanism="laplace")
    return out, tvd, ("joint-histogram" if "joint" in mech else "marginals")
