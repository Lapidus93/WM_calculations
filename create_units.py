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


def build_brigade_template(config: dict):
    soldiers_per_squad = config["soldier_id"]
    squads_per_platoon = config["squad_id"]
    platoons_per_company = config["platoon_id"]
    companies_per_battalion = config["company_id"]
    battalions_per_brigade = config["battalion_id"]
    armor_cnt = config["armor_cnt"]

    inf_rows = []

    soldier_global_id = 1

    for battalion_id in range(1, battalions_per_brigade + 1):
        for company_id in range(1, companies_per_battalion + 1):
            for platoon_id in range(1, platoons_per_company + 1):
                for squad_id in range(1, squads_per_platoon + 1):
                    for soldier_local_id in range(1, soldiers_per_squad + 1):

                        battalion_uid = f"B{battalion_id}"
                        company_uid = f"{battalion_uid}-C{company_id}"
                        platoon_uid = f"{company_uid}-P{platoon_id}"
                        squad_uid = f"{platoon_uid}-S{squad_id}"
                        soldier_uid = f"{squad_uid}-U{soldier_local_id}"

                        inf_rows.append({
                            "global_soldier_id": soldier_global_id,

                      
                            "soldier_id": soldier_local_id,
                            "squad_id": squad_id,
                            "platoon_id": platoon_id,
                            "company_id": company_id,
                            "battalion_id": battalion_id,

                            # uid
                            "battalion_uid": battalion_uid,
                            "company_uid": company_uid,
                            "platoon_uid": platoon_uid,
                            "squad_uid": squad_uid,
                            "soldier_uid": soldier_uid,

              
                            "status": "alive",
                            "power": 1,
                            "side": "",
                            "inf_kills": 0,
                            "apc_kills": 0,
                        })

                        soldier_global_id += 1

    inf_df = pd.DataFrame(inf_rows)

    armor_rows = []

    for armor_id in range(1, armor_cnt + 1):
        armor_rows.append({
            "armor_id": armor_id,
            "armor_uid": f"A{armor_id}",
            "type": "apc",
            "transport": 9,
            "power": 8,
            "status": "alive",
            "side": "",
            "inf_kills": 0,
            "apc_kills": 0,
        })

    armor_df = pd.DataFrame(armor_rows)

    return inf_df, armor_df



if __name__ == "__main__":
    src = Path("/mnt/data/brigade_template.xlsx")
    dst = Path("/mnt/data/brigade_template_with_uids.xlsx")
    process_workbook(src, dst)
    print(f"Saved: {dst}")
