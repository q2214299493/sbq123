"""Plot actual remaining DFT work from the frozen comparison checkpoint."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from scripts.artifact_io import load_json_object
from .analyze import OUTPUT


def plot():
    analysis = load_json_object(OUTPUT / "analysis.json")
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharey=True, constrained_layout=True)
    for column, name in enumerate(["10_A", "C3_05"]):
        for case in [c for c in analysis["cases"] if c["name"] == name]:
            frames = case["frames"]
            force = [f["DFT_movable_fmax_eV_A"] for f in frames]
            label = "Old" if case["model"] == "control" else "New512"
            color = "#2563eb" if case["model"] == "control" else "#d95f02"
            if not case["normal_completion"]:
                label += " (running; audited prefix)"
            axes[0, column].plot([f["ionic_step"] for f in frames], force, label=label, color=color)
            axes[1, column].plot([f["cumulative_SCF_iterations"] for f in frames], force, label=label, color=color)
        axes[0, column].set_title("C2H3, same raw start" if name == "10_A" else "C3-source CO + C2H2 diagnostic")
        for row in range(2):
            ax = axes[row, column]
            ax.axhline(.02, color="black", linestyle="--", label="DFT target 0.02")
            ax.set_yscale("log")
            ax.set_ylim(.015, 1)
            ax.grid(alpha=.2)
            ax.set_xlabel("DFT ionic force evaluations" if row == 0 else "Cumulative electronic (SCF) iterations")
        axes[0, column].legend(fontsize=8)
    axes[0, 0].set_ylabel("Movable-atom DFT max force (eV / Å)")
    axes[1, 0].set_ylabel("Movable-atom DFT max force (eV / Å)")
    fig.suptitle("No audited run has reached the fixed DFT convergence target", fontsize=12)
    for suffix in ["png", "pdf"]:
        target = OUTPUT / ("remaining_dft_work." + suffix)
        if target.exists():
            raise FileExistsError("preserve existing figure")
        fig.savefig(target, dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    plot()
