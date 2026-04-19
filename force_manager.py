from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd

import wm_unit as wmu


UID_COLUMNS = {
    "battalion": "battalion_uid",
    "company": "company_uid",
    "platoon": "platoon_uid",
    "squad": "squad_uid",
}

LOCAL_ID_COLUMNS = {
    "battalion": "battalion_id",
    "company": "company_id",
    "platoon": "platoon_id",
    "squad": "squad_id",
}

CHILD_LEVEL = {
    "battalion": "company",
    "company": "platoon",
    "platoon": "squad",
    "squad": None,
}

SPLIT_SEQUENCE = ["company", "platoon", "squad"]


@dataclass
class FormationSlice:
    df: pd.DataFrame
    label: str
    source_level: str
    source_uid: str
    split_basis: str

    @property
    def size(self) -> int:
        return len(self.df)

    def can_split(self) -> bool:
        return self._detect_split_level() is not None

    def _detect_split_level(self) -> Optional[str]:
        df = self.df

        # Split only by direct children of one common parent branch.
        if df[UID_COLUMNS["battalion"]].nunique() == 1 and df[UID_COLUMNS["company"]].nunique() > 1:
            return "company"
        if df[UID_COLUMNS["company"]].nunique() == 1 and df[UID_COLUMNS["platoon"]].nunique() > 1:
            return "platoon"
        if df[UID_COLUMNS["platoon"]].nunique() == 1 and df[UID_COLUMNS["squad"]].nunique() > 1:
            return "squad"
        return None

    def split_balanced(self) -> Optional[Tuple["FormationSlice", "FormationSlice"]]:
        split_level = self._detect_split_level()
        if split_level is None:
            return None

        uid_col = UID_COLUMNS[split_level]
        local_col = LOCAL_ID_COLUMNS[split_level]

        groups = []
        for uid, part in self.df.groupby(uid_col, sort=False):
            part = part.copy().reset_index(drop=True)
            # local ids are only unique inside parent, which is exactly what this slice preserves
            local_value = part.iloc[0][local_col]
            groups.append((int(local_value), str(uid), part))

        groups.sort(key=lambda x: x[0])
        if len(groups) < 2:
            return None

        total = sum(len(g[2]) for g in groups)
        target_left = total / 2.0

        left_parts = []
        right_parts = []
        running = 0

        for idx, (_, _, part) in enumerate(groups):
            remaining_groups = len(groups) - idx
            if not left_parts:
                left_parts.append(part)
                running += len(part)
                continue

            # keep at least one group on the right
            if remaining_groups == 1:
                right_parts.append(part)
                continue

            if running < target_left:
                left_parts.append(part)
                running += len(part)
            else:
                right_parts.append(part)

        if not right_parts:
            # move the last left group to the right to keep both non-empty
            right_parts.append(left_parts.pop())

        left_df = pd.concat(left_parts, ignore_index=True)
        right_df = pd.concat(right_parts, ignore_index=True)

        left_label = self._make_child_label(left_df, split_level, part_no=1)
        right_label = self._make_child_label(right_df, split_level, part_no=2)

        left_node = FormationSlice(
            df=left_df,
            label=left_label,
            source_level=self.source_level,
            source_uid=self.source_uid,
            split_basis=split_level,
        )
        right_node = FormationSlice(
            df=right_df,
            label=right_label,
            source_level=self.source_level,
            source_uid=self.source_uid,
            split_basis=split_level,
        )
        return left_node, right_node

    def _make_child_label(self, df: pd.DataFrame, split_level: str, part_no: int) -> str:
        if split_level == "company":
            ids = sorted(df[LOCAL_ID_COLUMNS["company"]].astype(int).unique().tolist())
            return f"{df.iloc[0][UID_COLUMNS['battalion']]}-PART{part_no}[C{ids[0]}..C{ids[-1]}]"
        if split_level == "platoon":
            ids = sorted(df[LOCAL_ID_COLUMNS['platoon']].astype(int).unique().tolist())
            return f"{df.iloc[0][UID_COLUMNS['company']]}-PART{part_no}[P{ids[0]}..P{ids[-1]}]"
        ids = sorted(df[LOCAL_ID_COLUMNS['squad']].astype(int).unique().tolist())
        return f"{df.iloc[0][UID_COLUMNS['platoon']]}-PART{part_no}[S{ids[0]}..S{ids[-1]}]"


class ForceManager:
    """
    Works with the master force table and builds temporary ground-level units from it.

    Main rules of this version:
    - The master DataFrame is the source of truth.
    - Generated temporary units are built ONLY from the formations passed in.
    - The manager NEVER mixes platoons from different companies or squads from different platoons.
    - A selected formation may be recursively split INSIDE ITS OWN BRANCH to approach target_units.
      Example: 1 battalion -> 3 companies -> each company may split into 2 groups of its own platoons,
      giving 6 temporary units without mixing platoons from different companies.
    """

    def __init__(self, master_df: pd.DataFrame):
        self.master_df = master_df.copy()
        self._ensure_required_columns()
        self._ensure_uid_columns()
        self._ensure_runtime_columns()

    @classmethod
    def from_excel(cls, path: str, sheet_name: int | str = 0) -> "ForceManager":
        df = pd.read_excel(path, sheet_name=sheet_name)
        return cls(df)

    def _ensure_required_columns(self) -> None:
        required = [
            "soldier_id",
            "squad_id",
            "platoon_id",
            "company_id",
            "battalion_id",
            "inf_kills",
            "apc_kills",
        ]
        missing = [c for c in required if c not in self.master_df.columns]
        if missing:
            raise ValueError(f"Missing required columns in master_df: {missing}")

    def _ensure_uid_columns(self) -> None:
        df = self.master_df

        if "battalion_uid" not in df.columns:
            df["battalion_uid"] = df["battalion_id"].apply(lambda x: f"B{int(x)}")
        if "company_uid" not in df.columns:
            df["company_uid"] = df.apply(
                lambda r: f"{r['battalion_uid']}-C{int(r['company_id'])}", axis=1
            )
        if "platoon_uid" not in df.columns:
            df["platoon_uid"] = df.apply(
                lambda r: f"{r['company_uid']}-P{int(r['platoon_id'])}", axis=1
            )
        if "squad_uid" not in df.columns:
            df["squad_uid"] = df.apply(
                lambda r: f"{r['platoon_uid']}-S{int(r['squad_id'])}", axis=1
            )
        if "soldier_uid" not in df.columns:
            df["soldier_uid"] = df.apply(
                lambda r: f"{r['squad_uid']}-U{int(r['soldier_id'])}", axis=1
            )

        self.master_df = df

    def _ensure_runtime_columns(self) -> None:
        df = self.master_df

        if "status" not in df.columns:
            df["status"] = "alive"
        if "power" not in df.columns:
            df["power"] = 1
        if "side" not in df.columns:
            df["side"] = ""

        self.master_df = df

    def save_to_excel(self, path: str, index: bool = False) -> None:
        self.master_df.to_excel(path, index=index)

    def get_formation_df(
        self,
        level: str,
        formation_uids: List[str],
        alive_only: bool = True,
    ) -> pd.DataFrame:
        if level not in UID_COLUMNS:
            raise ValueError(f"Unsupported level: {level}")

        uid_col = UID_COLUMNS[level]
        df = self.master_df[self.master_df[uid_col].isin(formation_uids)].copy()

        if alive_only:
            df = df[df["status"] == "alive"].copy()

        return df.reset_index(drop=True)

    def get_formation_summary(
        self,
        level: str,
        formation_uids: List[str],
        alive_only: bool = True,
    ) -> pd.DataFrame:
        df = self.get_formation_df(level, formation_uids, alive_only=alive_only)
        uid_col = UID_COLUMNS[level]

        summary = (
            df.groupby(uid_col, as_index=False)
            .agg(
                soldiers=("soldier_uid", "count"),
                inf_kills=("inf_kills", "sum"),
                apc_kills=("apc_kills", "sum"),
            )
            .sort_values(uid_col)
            .reset_index(drop=True)
        )
        return summary

    def generate_ground_units(
        self,
        level: str,
        formation_uids: List[str],
        target_units: int = 6,
        side: str = "",
        unit_prefix: str = "TMP",
    ) -> Tuple[List[wmu.Unit], pd.DataFrame]:
        if level not in UID_COLUMNS:
            raise ValueError(f"Unsupported level: {level}")

        nodes = self._initial_nodes(level, formation_uids)
        if not nodes:
            return [], pd.DataFrame()

        while len(nodes) < target_units:
            splittable = [n for n in nodes if n.can_split()]
            if not splittable:
                break

            # split the largest splittable node first
            node_to_split = sorted(splittable, key=lambda n: (-n.size, n.label))[0]
            split_result = node_to_split.split_balanced()
            if split_result is None:
                break

            left_node, right_node = split_result
            remaining = [n for n in nodes if n is not node_to_split]
            remaining.extend([left_node, right_node])
            nodes = sorted(remaining, key=lambda n: (-n.size, n.label))

        units = []
        plan_rows = []

        for i, node in enumerate(nodes, start=1):
            unit_id = f"{unit_prefix}_{i}"
            unit = self._build_inf_unit_from_slice(node, unit_id=unit_id, side=side)
            units.append(unit)

            plan_rows.append(
                {
                    "temp_unit_id": unit_id,
                    "slice_label": node.label,
                    "source_level": node.source_level,
                    "source_uid": node.source_uid,
                    "split_basis": node.split_basis,
                    "soldiers": len(node.df),
                    "company_uids": ",".join(sorted(node.df["company_uid"].unique())),
                    "platoon_uids": ",".join(sorted(node.df["platoon_uid"].unique())),
                    "squad_uids": ",".join(sorted(node.df["squad_uid"].unique())),
                }
            )

        plan_df = pd.DataFrame(plan_rows)
        if not plan_df.empty:
            plan_df = plan_df.sort_values(
                ["soldiers", "temp_unit_id"],
                ascending=[False, True],
            ).reset_index(drop=True)

        return units, plan_df

    def apply_battle_result(self, unit: wmu.Unit) -> None:
        """
        Push updated unit state back to the master DataFrame.

        Current behavior:
        - alive_df rows -> status = alive
        - cas_df rows   -> status = killed
        - inf_kills / apc_kills are synced back from both alive_df and cas_df
        """
        alive_df = unit.alive_df.copy() if unit.alive_df is not None else pd.DataFrame()
        cas_df = unit.cas_df.copy() if unit.cas_df is not None else pd.DataFrame()

        if not alive_df.empty and "soldier_uid" not in alive_df.columns and "sol_id" in alive_df.columns:
            alive_df["soldier_uid"] = alive_df["sol_id"]

        if not cas_df.empty and "soldier_uid" not in cas_df.columns and "sol_id" in cas_df.columns:
            cas_df["soldier_uid"] = cas_df["sol_id"]

        all_updates = []
        if not alive_df.empty:
            alive_updates = alive_df[["soldier_uid", "inf_kills", "apc_kills"]].copy()
            alive_updates["status"] = "alive"
            all_updates.append(alive_updates)

        if not cas_df.empty:
            cas_updates = cas_df[["soldier_uid", "inf_kills", "apc_kills"]].copy()
            cas_updates["status"] = "killed"
            all_updates.append(cas_updates)

        if not all_updates:
            return

        updates = pd.concat(all_updates, ignore_index=True)
        updates = updates.drop_duplicates(subset=["soldier_uid"], keep="last")

        update_index = updates.set_index("soldier_uid")
        master_index = self.master_df.set_index("soldier_uid")

        common_ids = master_index.index.intersection(update_index.index)
        if len(common_ids) == 0:
            return

        master_index.loc[common_ids, "status"] = update_index.loc[common_ids, "status"]
        master_index.loc[common_ids, "inf_kills"] = update_index.loc[common_ids, "inf_kills"]
        master_index.loc[common_ids, "apc_kills"] = update_index.loc[common_ids, "apc_kills"]

        self.master_df = master_index.reset_index()

    def apply_many_battle_results(self, units: List[wmu.Unit]) -> None:
        for unit in units:
            self.apply_battle_result(unit)

    def _initial_nodes(self, level: str, formation_uids: List[str]) -> List[FormationSlice]:
        uid_col = UID_COLUMNS[level]
        df = self.get_formation_df(level, formation_uids, alive_only=True)

        nodes = []
        for uid in formation_uids:
            part = df[df[uid_col] == uid].copy().reset_index(drop=True)
            if part.empty:
                continue
            nodes.append(
                FormationSlice(
                    df=part,
                    label=uid,
                    source_level=level,
                    source_uid=uid,
                    split_basis=level,
                )
            )
        return nodes

    def _build_inf_unit_from_slice(self, node: FormationSlice, unit_id: str, side: str) -> wmu.Unit:
        alive_df = node.df.copy().reset_index(drop=True)

        alive_df["sol_id"] = alive_df["soldier_uid"]
        if "power" not in alive_df.columns:
            alive_df["power"] = 1
        if "inf_kills" not in alive_df.columns:
            alive_df["inf_kills"] = 0
        if "apc_kills" not in alive_df.columns:
            alive_df["apc_kills"] = 0

        cols = [
            "sol_id",
            "soldier_uid",
            "power",
            "inf_kills",
            "apc_kills",
            "battalion_uid",
            "company_uid",
            "platoon_uid",
            "squad_uid",
        ]
        alive_df = alive_df[cols].copy()

        cas_df = pd.DataFrame(columns=alive_df.columns)

        unit = wmu.Unit(
            unit_id=unit_id,
            overall_type="inf",
            personal_type="inf",
            alive_df=alive_df,
            cas_df=cas_df,
            side=side,
        )
        return unit
