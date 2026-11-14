"""Plot only the native development cache; never imply new model predictions."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

from scripts.artifact_io import load_json_object, source_file_manifest, write_json_exclusive
from .prepare import OUT


def run():
    data = load_json_object(OUT / "cached_development_role_metrics.json")
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = FontProperties(fname=str(font_path))
    plt.rcParams["axes.unicode_minus"] = False
    figure, axis = plt.subplots(figsize=(9.5, 5.6), dpi=160)
    values = [r["vector_MAE_eV_A"] for r in data["roles"]]
    bars = axis.bar(range(5), values, width=.62, color=["#ce6339", "#d18c38", "#b7a061", "#337b92", "#81a9b4"])
    axis.set_xticks(range(5), [r["label"] for r in data["roles"]], fontproperties=font)
    axis.set_ylabel("每原子力向量MAE（eV/Å）", fontproperties=font)
    axis.set_title("冻结536候选：原78帧开发集缓存", fontproperties=font, fontsize=15, pad=18)
    axis.set_ylim(0, .125)
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", alpha=.18)
    axis.set_axisbelow(True)
    for bar, row in zip(bars, data["roles"], strict=True):
        axis.text(bar.get_x() + bar.get_width()/2, bar.get_height() + .003,
                  f"{row['vector_MAE_eV_A']:.4f}\nn={row['atom_observations']}", ha="center", fontsize=10)
    figure.text(.5, .035, "仅展示已有汇总；未运行新预测。含18帧严格证据、60帧原force-only范围，无法分层拆分。",
                fontproperties=font, ha="center", fontsize=9, color="#555555")
    figure.tight_layout(rect=(0, .08, 1, 1))
    target = OUT / "cached_development_role_MAE.png"
    if target.exists():
        raise FileExistsError(target)
    figure.savefig(target)
    plt.close(figure)
    write_json_exclusive(OUT / "plot_binding.json", {"plot_path": str(target), "cache_only": True,
                         "source_files": source_file_manifest([Path(__file__), OUT / "cached_development_role_metrics.json", font_path, target])})


if __name__ == "__main__":
    run()
