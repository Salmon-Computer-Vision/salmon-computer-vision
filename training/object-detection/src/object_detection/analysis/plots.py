from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
import matplotlib.pyplot as plt


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _save_bar_plot(
    df: pd.DataFrame,
    value_col: str,
    title: str,
    ylabel: str,
    out_path: Path,
    logy: bool = False,
) -> None:
    pivot = df.pivot(index="class_name", columns="site", values=value_col).fillna(0.0)
    pivot = pivot.sort_index()

    fig, ax = plt.subplots(figsize=(14, 7))
    pivot.plot(kind="bar", ax=ax)

    if logy:
        ax.set_yscale("log")

    ax.set_title(title)
    ax.set_xlabel("Class")
    ax.set_ylabel(ylabel)
    ax.legend(title="Site")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_site_class_stats(
    *,
    stats_dir: Path,
    out_dir: Path,
) -> List[Path]:
    """
    Reads:
      - site_class_frame_counts.csv
      - site_class_box_counts.csv

    Writes:
      - frame_counts_by_site_class.png
      - frame_pct_within_class_by_site.png
      - box_counts_by_site_class.png
      - box_pct_within_class_by_site.png
    """
    _ensure_dir(out_dir)

    frame_csv = stats_dir / "site_class_frame_counts.csv"
    box_csv = stats_dir / "site_class_box_counts.csv"

    frame_df = pd.read_csv(frame_csv)
    box_df = pd.read_csv(box_csv)

    outputs: List[Path] = []

    p1 = out_dir / "frame_counts_by_site_class.png"
    _save_bar_plot(
        frame_df,
        value_col="frame_count",
        title="Frame Count by Site and Class",
        ylabel="Frame Count",
        out_path=p1,
        logy=True,
    )
    outputs.append(p1)

    p2 = out_dir / "frame_pct_within_class_by_site.png"
    _save_bar_plot(
        frame_df,
        value_col="frame_pct_within_class",
        title="Frame Percentage Within Class by Site",
        ylabel="Percent of Class Frames",
        out_path=p2,
    )
    outputs.append(p2)

    p3 = out_dir / "box_counts_by_site_class.png"
    _save_bar_plot(
        box_df,
        value_col="box_count",
        title="Box Count by Site and Class",
        ylabel="Box Count",
        out_path=p3,
        logy=True,
    )
    outputs.append(p3)

    p4 = out_dir / "box_pct_within_class_by_site.png"
    _save_bar_plot(
        box_df,
        value_col="box_pct_within_class",
        title="Box Percentage Within Class by Site",
        ylabel="Percent of Class Boxes",
        out_path=p4,
    )
    outputs.append(p4)

    return outputs
