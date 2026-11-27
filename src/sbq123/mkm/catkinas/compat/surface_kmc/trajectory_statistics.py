"""Read cumulative Zacros process counters and species-number samples on their native clocks."""
import math


def _number(value):
    number = float(value.replace("D", "E"))
    if not math.isfinite(number):
        raise ValueError("Non-finite trajectory sample")
    return number


def _table(raw, header, tag):
    lines = [line.split() for line in raw.decode("ascii").splitlines() if line.strip()]
    if lines and lines[0][0] == tag:
        labels = lines.pop(0)
        if header is not None and labels != header:
            raise ValueError("Trajectory header differs from checkpoint writer")
    elif header is not None:
        labels = header
    else:
        raise ValueError(f"Missing {tag} trajectory header")
    if len(set(labels)) != len(labels):
        raise ValueError("Duplicate trajectory column")
    return labels, lines


def _ordered(samples):
    for a, b in zip(samples, samples[1:]):
        if b[0] <= a[0] or b[1] < a[1]:
            raise ValueError("Nonmonotone trajectory event index or clock")
    if any(n < 0 or t < 0 for n, t, _ in samples):
        raise ValueError("Invalid trajectory index or time")
    return samples


def process_samples(raw, header=None):
    labels, lines = _table(raw, header, "Overall")
    if labels[0] != "Overall" or len(lines) % 3:
        raise ValueError("Incomplete process statistics block")
    samples = []
    for start in range(0, len(lines), 3):
        cfg, waiting, counters = lines[start:start + 3]
        if len(cfg) != 4 or cfg[0] != "configuration" or len(counters) != len(labels) or len(waiting) != len(labels):
            raise ValueError("Process statistics dimensions differ")
        n, t = int(cfg[2]), _number(cfg[3])
        total, *counts = map(int, counters)
        if n != total or total != sum(counts) or any(v < 0 for v in counts):
            raise ValueError("Inconsistent process counters")
        values = dict(zip(labels[1:], counts, strict=True))
        if samples and any(v < samples[-1][2][k] for k, v in values.items()):
            raise ValueError("Process counter decreased")
        samples.append((n, t, values))
    return _ordered(samples)


def species_samples(raw, names, temperature, header=None):
    labels, lines = _table(raw, header, "Entry")
    if labels[:5] != ["Entry", "Nevents", "Time", "Temperature", "Energy"] or set(labels[5:]) != set(names):
        raise ValueError("Species header differs from native model")
    samples = []
    for row in lines:
        if len(row) != len(labels) or _number(row[3]) != temperature:
            raise ValueError("Species sample dimensions or temperature differ")
        values = {names[k]: int(v) for k, v in zip(labels[5:], row[5:], strict=True)}
        samples.append((int(row[1]), _number(row[2]), values))
    return _ordered(samples)


def sampling_window(samples):
    if not samples:
        return None, None
    first, last = samples[0], samples[-1]
    delta = {k: last[2][k] - v for k, v in first[2].items()}
    window = {"first_event": first[0], "last_event": last[0], "start_s": first[1], "end_s": last[1],
              "duration_s": last[1] - first[1]}
    return window, delta
