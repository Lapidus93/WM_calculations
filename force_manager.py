from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

import wm_unit as wmu


UID_COLUMNS = {
    "battalion": "battalion_uid",
    "company": "company_uid",
    "platoon": "platoon_uid",
    "squad": "squad_uid",
}

CHILD_LEVEL = {
    "battalion": "company",
    "company": "platoon",
    "platoon": "squad",
    "squad": None,
}


@dataclass(eq=False)
class FormationSlice:
    level: str
    formation_uid: str
    df: pd.DataFrame
    slice_label: str = ""
    split_basis: str = ""

    @property
    def size(self) -> int:
        return len(self.df)

    @property
    def child_level(self) -> Optional[str]:
        return CHILD_LEVEL[self.level]

    def can_split(self) -> bool:
        child_level = self.child_level
        if child_level is None:
            return False
        child_col = UID_COLUMNS[child_level]
        return self.df[child_col].nunique() > 1


class ForceManager:
    """
    Master-state manager for one brigade file.

    Supports:
    - infantry sheet: `inf`
    - armor sheet: `armor`
    - generation of temporary ground units from infantry hierarchy
    - optional attachment of brigade-level armor:
        * 2/3 of selected armor -> one pure arm unit
        * 1/3 of selected armor -> randomly distributed across generated infantry units
          which turns them into mech units
    - writing updated alive/killed status back to both sheets
    """

    def __init__(self, inf_df: pd.DataFrame, armor_df: Optional[pd.DataFrame] = None):
        self.master_df = inf_df.copy()
        self.armor_df = armor_df.copy() if armor_df is not None else pd.DataFrame()
        self._ensure_inf_required_columns()
        self._ensure_inf_uid_columns()
        self._ensure_inf_runtime_columns()
        self._ensure_armor_uid_columns()
        self._ensure_armor_runtime_columns()

    @classmethod
    def from_excel(cls, path: str) -> "ForceManager":
        workbook = pd.ExcelFile(path)
        sheet_names = set(workbook.sheet_names)

        if "inf" in sheet_names:
            inf_df = pd.read_excel(path, sheet_name="inf")
        else:
            inf_df = pd.read_excel(path, sheet_name=workbook.sheet_names[0])

        armor_df = pd.read_excel(path, sheet_name="armor") if "armor" in sheet_names else pd.DataFrame()
        return cls(inf_df=inf_df, armor_df=armor_df)

    def save_to_excel(self, path: str, index: bool = False) -> None:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            self.master_df.to_excel(writer, sheet_name="inf", index=index)
            if not self.armor_df.empty:
                self.armor_df.to_excel(writer, sheet_name="armor", index=index)

    # ------------------------------------------------------------------
    # Infantry sheet setup
    # ------------------------------------------------------------------
    def _ensure_inf_required_columns(self) -> None:
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
            raise ValueError(f"Missing required infantry columns in master_df: {missing}")

    def _ensure_inf_uid_columns(self) -> None:
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

    def _ensure_inf_runtime_columns(self) -> None:
        df = self.master_df

        if "status" not in df.columns:
            df["status"] = "alive"
        if "power" not in df.columns:
            df["power"] = 1
        if "side" not in df.columns:
            df["side"] = ""

        self.master_df = df

    # ------------------------------------------------------------------
    # Armor sheet setup
    # ------------------------------------------------------------------
    def _ensure_armor_uid_columns(self) -> None:
        if self.armor_df.empty:
            return
        df = self.armor_df
        if "armor_id" not in df.columns:
            raise ValueError("Armor sheet must contain column 'armor_id'.")
        if "armor_uid" not in df.columns:
            df["armor_uid"] = df["armor_id"].apply(lambda x: f"A{int(x)}")
        self.armor_df = df

    def _ensure_armor_runtime_columns(self) -> None:
        if self.armor_df.empty:
            return

        df = self.armor_df
        if "type" not in df.columns:
            df["type"] = "apc"
        if "transport" not in df.columns:
            df["transport"] = 9
        if "power" not in df.columns:
            df["power"] = 8
        if "inf_kills" not in df.columns:
            df["inf_kills"] = 0
        if "apc_kills" not in df.columns:
            df["apc_kills"] = 0
        if "status" not in df.columns:
            df["status"] = "alive"
        if "side" not in df.columns:
            df["side"] = ""

        self.armor_df = df

    # ------------------------------------------------------------------
    # Infantry querying / splitting
    # ------------------------------------------------------------------
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
        slices = self._build_balanced_slices(
            level=level,
            formation_uids=formation_uids,
            target_units=target_units,
        )

        units = []
        plan_rows = []

        for i, node in enumerate(slices, start=1):
            unit_id = f"{unit_prefix}_{i}"
            unit = self._build_inf_unit_from_slice(node, unit_id=unit_id, side=side)
            units.append(unit)

            plan_rows.append(
                {
                    "temp_unit_id": unit_id,
                    "source_level": node.level,
                    "source_uid": node.formation_uid,
                    "slice_label": node.slice_label or node.formation_uid,
                    "split_basis": node.split_basis or node.level,
                    "soldiers": len(node.df),
                    "company_uids": ",".join(sorted(node.df["company_uid"].astype(str).unique())),
                    "platoon_uids": ",".join(sorted(node.df["platoon_uid"].astype(str).unique())),
                    "squad_uids": ",".join(sorted(node.df["squad_uid"].astype(str).unique())),
                    "unit_role": "inf_or_mech",
                }
            )

        plan_df = pd.DataFrame(plan_rows)
        if not plan_df.empty:
            plan_df = plan_df.sort_values(
                ["soldiers", "temp_unit_id"], ascending=[False, True]
            ).reset_index(drop=True)

        return units, plan_df

    def generate_ground_units_with_armor(
        self,
        level: str,
        formation_uids: List[str],
        target_units: int = 6,
        armor_count: int = 0,
        side: str = "",
        unit_prefix: str = "TMP",
        rng=None,
    ) -> Tuple[List[wmu.Unit], pd.DataFrame]:
        """
        Build infantry-derived units and optionally add brigade armor.

        Armor rule:
        - select `armor_count` alive vehicles from armor sheet
        - split into 3 near-equal parts, e.g. 10 -> 3 + 3 + 4
        - first two parts are merged into one pure armor unit
        - third part is distributed randomly across the generated infantry units
          which creates mech units
        """
        if rng is None:
            import random as _random
            rng = _random

        units, plan_df = self.generate_ground_units(
            level=level,
            formation_uids=formation_uids,
            target_units=target_units,
            side=side,
            unit_prefix=unit_prefix,
        )

        if armor_count <= 0:
            return units, plan_df

        if self.armor_df.empty:
            raise ValueError(
                f"Armor count {armor_count} requested, but armor sheet is missing or empty."
            )

        alive_armor = self.armor_df[self.armor_df["status"] == "alive"].copy()
        if armor_count > len(alive_armor):
            raise ValueError(
                f"Requested {armor_count} armor units, but only {len(alive_armor)} alive armor rows are available."
            )

        selected_armor = alive_armor.sort_values("armor_uid").head(armor_count).copy().reset_index(drop=True)

        part1, part2, part3 = self._split_armor_count_into_three(armor_count)
        arm_count = part1 + part2
        mech_count = part3

        armor_plan_rows = []
        next_unit_number = len(units) + 1

        # 1) Pure armor unit from first two thirds
        if arm_count > 0:
            arm_rows = selected_armor.iloc[:arm_count].copy().reset_index(drop=True)
            arm_unit_id = f"{unit_prefix}_{next_unit_number}"
            next_unit_number += 1

            arm_unit = self._build_arm_unit_from_rows(arm_rows, unit_id=arm_unit_id, side=side)
            units.append(arm_unit)

            armor_plan_rows.append(
                {
                    "temp_unit_id": arm_unit_id,
                    "unit_role": "arm",
                    "assigned_armor": len(arm_rows),
                    "source_armor_uids": ",".join(arm_rows["armor_uid"].astype(str).tolist()),
                }
            )

        # 2) Remaining third randomly distributed into infantry units -> mech
        if mech_count > 0 and units:
            mech_rows = selected_armor.iloc[arm_count:arm_count + mech_count].copy().reset_index(drop=True)

            inf_like_units = [u for u in units if u.personal_type == "inf"]
            if not inf_like_units:
                raise ValueError("Cannot attach armor to infantry: no infantry units were generated.")

            recipient_map: Dict[str, List[dict]] = {u.unit_id: [] for u in inf_like_units}
            for _, row in mech_rows.iterrows():
                recipient = rng.choice(inf_like_units)
                recipient_map[recipient.unit_id].append(row.to_dict())

            for unit in inf_like_units:
                assigned = recipient_map[unit.unit_id]
                if not assigned:
                    continue
                armor_part_df = pd.DataFrame(assigned).reset_index(drop=True)
                armor_part = self._build_arm_unit_from_rows(
                    armor_part_df,
                    unit_id=f"{unit.unit_id}_ARM",
                    side=side,
                )
                unit.armor_part = armor_part
                unit.update_current_type()

                armor_plan_rows.append(
                    {
                        "temp_unit_id": unit.unit_id,
                        "unit_role": "mech_attachment",
                        "assigned_armor": len(armor_part_df),
                        "source_armor_uids": ",".join(armor_part_df["armor_uid"].astype(str).tolist()),
                    }
                )

        armor_plan_df = pd.DataFrame(armor_plan_rows)

        if plan_df.empty:
            combined_plan = armor_plan_df.copy()
        else:
            combined_plan = plan_df.copy()
            if not armor_plan_df.empty:
                combined_plan = combined_plan.merge(
                    armor_plan_df[["temp_unit_id", "unit_role", "assigned_armor", "source_armor_uids"]],
                    on="temp_unit_id",
                    how="left",
                    suffixes=("", "_armor"),
                )

                role_col = None
                for candidate in ["unit_role", "unit_role_armor", "unit_role_x", "unit_role_y"]:
                    if candidate in combined_plan.columns:
                        role_col = candidate
                        break
                if role_col is None:
                    combined_plan["unit_role"] = "inf"
                else:
                    combined_plan["unit_role"] = combined_plan[role_col].fillna("inf")

                armor_count_col = None
                for candidate in ["assigned_armor", "assigned_armor_armor", "assigned_armor_x", "assigned_armor_y"]:
                    if candidate in combined_plan.columns:
                        armor_count_col = candidate
                        break
                if armor_count_col is None:
                    combined_plan["assigned_armor"] = 0
                else:
                    combined_plan["assigned_armor"] = combined_plan[armor_count_col].fillna(0).astype(int)

                armor_uids_col = None
                for candidate in ["source_armor_uids", "source_armor_uids_armor", "source_armor_uids_x", "source_armor_uids_y"]:
                    if candidate in combined_plan.columns:
                        armor_uids_col = candidate
                        break
                if armor_uids_col is None:
                    combined_plan["source_armor_uids"] = ""
                else:
                    combined_plan["source_armor_uids"] = combined_plan[armor_uids_col].fillna("")

                pure_armor_rows = armor_plan_df[~armor_plan_df["temp_unit_id"].isin(combined_plan["temp_unit_id"])]
                if not pure_armor_rows.empty:
                    pure_armor_rows = pure_armor_rows.copy()
                    pure_armor_rows["source_level"] = "armor"
                    pure_armor_rows["source_uid"] = ""
                    pure_armor_rows["slice_label"] = pure_armor_rows["temp_unit_id"]
                    pure_armor_rows["split_basis"] = "armor"
                    pure_armor_rows["soldiers"] = 0
                    pure_armor_rows["company_uids"] = ""
                    pure_armor_rows["platoon_uids"] = ""
                    pure_armor_rows["squad_uids"] = ""
                    combined_plan = pd.concat([combined_plan, pure_armor_rows], ignore_index=True)
            else:
                combined_plan["unit_role"] = "inf"
                combined_plan["assigned_armor"] = 0
                combined_plan["source_armor_uids"] = ""

        return units, combined_plan.reset_index(drop=True)

    # ------------------------------------------------------------------
    # Apply battle results back to master tables
    # ------------------------------------------------------------------
    def apply_battle_result(self, unit: wmu.Unit) -> None:
        self._apply_infantry_unit_result(unit)
        self._apply_armor_unit_result(unit)

        if getattr(unit, "armor_part", None) not in (None, []):
            if hasattr(unit.armor_part, "alive_df"):
                self._apply_armor_unit_result(unit.armor_part)

    def apply_many_battle_results(self, units: List[wmu.Unit]) -> None:
        for unit in units:
            self.apply_battle_result(unit)

    def _apply_infantry_unit_result(self, unit: wmu.Unit) -> None:
        if getattr(unit, "alive_df", None) is None:
            return
        if "soldier_uid" not in unit.alive_df.columns and "soldier_uid" not in unit.cas_df.columns:
            return

        alive_uids = (
            set(unit.alive_df["soldier_uid"].astype(str).tolist())
            if "soldier_uid" in unit.alive_df.columns and len(unit.alive_df) > 0
            else set()
        )
        killed_uids = (
            set(unit.cas_df["soldier_uid"].astype(str).tolist())
            if unit.cas_df is not None and not unit.cas_df.empty and "soldier_uid" in unit.cas_df.columns
            else set()
        )

        if alive_uids:
            self.master_df.loc[
                self.master_df["soldier_uid"].astype(str).isin(alive_uids), "status"
            ] = "alive"

            sync_cols = [c for c in ["inf_kills", "apc_kills", "side"] if c in unit.alive_df.columns]
            if sync_cols:
                sync_df = unit.alive_df[["soldier_uid"] + sync_cols].copy()
                self.master_df = self._sync_back_by_uid(
                    self.master_df, sync_df, uid_col="soldier_uid", cols_to_sync=sync_cols
                )

        if killed_uids:
            if "status" in unit.cas_df.columns and not unit.cas_df.empty and "soldier_uid" in unit.cas_df.columns:
                status_map = (
                    unit.cas_df[["soldier_uid", "status"]]
                    .drop_duplicates(subset=["soldier_uid"])
                    .set_index("soldier_uid")["status"]
                    .to_dict()
                )
                mask = self.master_df["soldier_uid"].astype(str).isin(
                    {str(k) for k in status_map}
                )
                self.master_df.loc[mask, "status"] = (
                    self.master_df.loc[mask, "soldier_uid"]
                    .astype(str)
                    .map({str(k): v for k, v in status_map.items()})
                )
            else:
                self.master_df.loc[
                    self.master_df["soldier_uid"].astype(str).isin(killed_uids), "status"
                ] = "killed"

            sync_cols = [c for c in ["inf_kills", "apc_kills", "side"] if c in unit.cas_df.columns]
            if sync_cols:
                sync_df = unit.cas_df[["soldier_uid"] + sync_cols].copy()
                self.master_df = self._sync_back_by_uid(
                    self.master_df, sync_df, uid_col="soldier_uid", cols_to_sync=sync_cols
                )

    def _apply_armor_unit_result(self, unit: wmu.Unit) -> None:
        if self.armor_df.empty:
            return
        if getattr(unit, "alive_df", None) is None:
            return

        alive_has_uid = "armor_uid" in unit.alive_df.columns if hasattr(unit.alive_df, "columns") else False
        cas_has_uid = (
            "armor_uid" in unit.cas_df.columns
            if getattr(unit, "cas_df", None) is not None and hasattr(unit.cas_df, "columns")
            else False
        )
        if not alive_has_uid and not cas_has_uid:
            return

        alive_uids = (
            set(unit.alive_df["armor_uid"].astype(str).tolist())
            if alive_has_uid and len(unit.alive_df) > 0
            else set()
        )
        killed_uids = (
            set(unit.cas_df["armor_uid"].astype(str).tolist())
            if cas_has_uid and unit.cas_df is not None and not unit.cas_df.empty
            else set()
        )

        if alive_uids:
            self.armor_df.loc[
                self.armor_df["armor_uid"].astype(str).isin(alive_uids), "status"
            ] = "alive"

            sync_cols = [c for c in ["inf_kills", "apc_kills", "side"] if c in unit.alive_df.columns]
            if sync_cols:
                sync_df = unit.alive_df[["armor_uid"] + sync_cols].copy()
                self.armor_df = self._sync_back_by_uid(
                    self.armor_df, sync_df, uid_col="armor_uid", cols_to_sync=sync_cols
                )

        if killed_uids:
            self.armor_df.loc[
                self.armor_df["armor_uid"].astype(str).isin(killed_uids), "status"
            ] = "killed"

            sync_cols = [c for c in ["inf_kills", "apc_kills", "side"] if c in unit.cas_df.columns]
            if sync_cols:
                sync_df = unit.cas_df[["armor_uid"] + sync_cols].copy()
                self.armor_df = self._sync_back_by_uid(
                    self.armor_df, sync_df, uid_col="armor_uid", cols_to_sync=sync_cols
                )

    @staticmethod
    def _sync_back_by_uid(
        master_df: pd.DataFrame,
        changed_df: pd.DataFrame,
        uid_col: str,
        cols_to_sync: List[str],
    ) -> pd.DataFrame:
        changed_df = changed_df.drop_duplicates(subset=[uid_col], keep="last").copy()
        changed_df = changed_df.set_index(uid_col)

        master = master_df.copy()
        master_indexed = master.set_index(uid_col)

        common_uids = master_indexed.index.intersection(changed_df.index)
        for col in cols_to_sync:
            master_indexed.loc[common_uids, col] = changed_df.loc[common_uids, col]

        return master_indexed.reset_index()

    # ------------------------------------------------------------------
    # Internal splitting helpers
    # ------------------------------------------------------------------
    def _build_balanced_slices(
        self,
        level: str,
        formation_uids: List[str],
        target_units: int,
    ) -> List[FormationSlice]:
        if level not in UID_COLUMNS:
            raise ValueError(f"Unsupported level: {level}")

        root_slices = []
        for formation_uid in formation_uids:
            df = self.get_formation_df(level=level, formation_uids=[formation_uid], alive_only=True)
            if df.empty:
                continue
            root_slices.append(
                FormationSlice(
                    level=level,
                    formation_uid=formation_uid,
                    df=df,
                    slice_label=formation_uid,
                    split_basis=level,
                )
            )

        slices = root_slices[:]
        if target_units <= 0:
            return slices

        while len(slices) < target_units:
            splittable = [s for s in slices if s.can_split()]
            if not splittable:
                break

            splittable = sorted(splittable, key=lambda x: (x.size, x.formation_uid), reverse=True)
            target_slice = splittable[0]

            target_index = next((i for i, s in enumerate(slices) if s is target_slice), None)
            if target_index is None:
                raise RuntimeError("Internal error: target slice was not found by identity in slices list.")
            slices.pop(target_index)

            left, right = self._split_slice_in_two(target_slice)
            slices.extend([left, right])

        slices = sorted(
            slices,
            key=lambda x: (x.size, x.formation_uid, x.slice_label),
            reverse=True,
        )
        return slices

    def _split_slice_in_two(self, node: FormationSlice) -> Tuple[FormationSlice, FormationSlice]:
        child_level = node.child_level
        if child_level is None:
            raise ValueError(f"Cannot split slice at level {node.level}")

        child_col = UID_COLUMNS[child_level]
        child_uids = list(node.df[child_col].drop_duplicates())

        if len(child_uids) < 2:
            raise ValueError(f"Slice {node.formation_uid} at level {node.level} cannot be split further.")

        left_children, right_children = self._partition_child_uids_evenly(node.df, child_col, child_uids)

        left_df = node.df[node.df[child_col].isin(left_children)].copy().reset_index(drop=True)
        right_df = node.df[node.df[child_col].isin(right_children)].copy().reset_index(drop=True)

        basis_label = child_level
        left_label = f"{node.formation_uid}-PART1[{left_children[0]}..{left_children[-1]}]"
        right_label = f"{node.formation_uid}-PART2[{right_children[0]}..{right_children[-1]}]"

        left_level = node.level
        left_uid = node.formation_uid
        if len(left_children) == 1:
            left_level = child_level
            left_uid = str(left_children[0])

        right_level = node.level
        right_uid = node.formation_uid
        if len(right_children) == 1:
            right_level = child_level
            right_uid = str(right_children[0])

        left = FormationSlice(
            level=left_level,
            formation_uid=left_uid,
            df=left_df,
            slice_label=left_label,
            split_basis=basis_label,
        )
        right = FormationSlice(
            level=right_level,
            formation_uid=right_uid,
            df=right_df,
            slice_label=right_label,
            split_basis=basis_label,
        )
        return left, right

    @staticmethod
    def _partition_child_uids_evenly(
        df: pd.DataFrame,
        child_col: str,
        child_uids: List[str],
    ) -> Tuple[List[str], List[str]]:
        counts = (
            df.groupby(child_col)
            .size()
            .reindex(child_uids)
            .fillna(0)
            .astype(int)
            .to_dict()
        )

        left: List[str] = []
        right: List[str] = []
        left_total = 0
        right_total = 0

        for uid in child_uids:
            if left_total <= right_total:
                left.append(uid)
                left_total += counts[uid]
            else:
                right.append(uid)
                right_total += counts[uid]

        if not left or not right:
            mid = max(1, len(child_uids) // 2)
            left = child_uids[:mid]
            right = child_uids[mid:]

        return left, right

    # ------------------------------------------------------------------
    # Unit builders
    # ------------------------------------------------------------------
    @staticmethod
    def _build_inf_unit_from_slice(node: FormationSlice, unit_id: str, side: str) -> wmu.Unit:
        alive_df = node.df.copy().reset_index(drop=True)
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

    @staticmethod
    def _build_arm_unit_from_rows(rows_df: pd.DataFrame, unit_id: str, side: str) -> wmu.Unit:
        alive_df = rows_df.copy().reset_index(drop=True)
        cas_df = pd.DataFrame(columns=alive_df.columns)
        unit = wmu.Unit(
            unit_id=unit_id,
            overall_type="arm",
            personal_type="arm",
            alive_df=alive_df,
            cas_df=cas_df,
            side=side,
        )
        unit.size = "ARMOR"
        return unit

    @staticmethod
    def _split_armor_count_into_three(n: int) -> Tuple[int, int, int]:
        if n <= 0:
            return 0, 0, 0
        base = n // 3
        remainder = n % 3
        return base, base, base + remainder
