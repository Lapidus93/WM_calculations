from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


def add_hierarchy_uids(
    df: pd.DataFrame,
    battalion_col: str = "battalion_id",
    company_col: str = "company_id",
    platoon_col: str = "platoon_id",
    squad_col: str = "squad_id",
    soldier_col: str = "soldier_id",
) -> pd.DataFrame:
    """Return a copy of df with hierarchical unique IDs added.

    Expected raw template columns:
      - battalion_id
      - company_id
      - platoon_id
      - squad_id
      - soldier_id

    New columns:
      - battalion_uid: B1
      - company_uid: B1-C1
      - platoon_uid: B1-C1-P1
      - squad_uid: B1-C1-P1-S1
      - soldier_uid: B1-C1-P1-S1-U1

    Notes:
      - This keeps your original local IDs unchanged.
      - The generated UID columns are what the engine should use.
    """
    required = [battalion_col, company_col, platoon_col, squad_col, soldier_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    out = df.copy()

    # Keep source IDs as integers where possible so generated strings are clean.
    for col in required:
        out[col] = pd.to_numeric(out[col], errors="raise").astype("Int64")

    out["battalion_uid"] = "B" + out[battalion_col].astype(str)
    out["company_uid"] = (
        out["battalion_uid"]
        + "-C"
        + out[company_col].astype(str)
    )
    out["platoon_uid"] = (
        out["company_uid"]
        + "-P"
        + out[platoon_col].astype(str)
    )
    out["squad_uid"] = (
        out["platoon_uid"]
        + "-S"
        + out[squad_col].astype(str)
    )
    out["soldier_uid"] = (
        out["squad_uid"]
        + "-U"
        + out[soldier_col].astype(str)
    )

    return out


def process_workbook(input_path: str | Path, output_path: str | Path, sheet_name: str | None = None) -> None:
    input_path = Path(input_path)
    output_path = Path(output_path)

    xls = pd.ExcelFile(input_path)
    target_sheets: Iterable[str]
    if sheet_name is None:
        target_sheets = xls.sheet_names
    else:
        target_sheets = [sheet_name]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for current_sheet in xls.sheet_names:
            df = pd.read_excel(input_path, sheet_name=current_sheet)
            if current_sheet in target_sheets:
                df = add_hierarchy_uids(df)
            df.to_excel(writer, sheet_name=current_sheet, index=False)


if __name__ == "__main__":
    src = Path("/mnt/data/brigade_template.xlsx")
    dst = Path("/mnt/data/brigade_template_with_uids.xlsx")
    process_workbook(src, dst)
    print(f"Saved: {dst}")
