from __future__ import annotations

import math
import random
from typing import Optional

import pandas as pd

from wm_unit import Unit

# ---------------------------------------------------------------------------
# Grid constants
# ---------------------------------------------------------------------------
ALL_SIZE  = 400        # total grid side
UNIT_HALF = 50         # half-side of unit_territory (100×100 total)
CENTER    = ALL_SIZE // 2   # = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upgrade_status(current: str, hit_zone: str) -> str:
    """Return upgraded status after soldier is hit in hit_zone.

    Rules:
        alive  + any hit  -> hit_zone
        light  + killed   -> killed
        light  + heavy    -> killed
        light  + light    -> heavy
        heavy  + any hit  -> killed
    """
    if current == "alive":
        return hit_zone
    if current == "light":
        return "killed" if hit_zone in ("killed", "heavy") else "heavy"
    # heavy or killed -> killed
    return "killed"


def _build_arty_log_row(
    current_time,
    initiator: str,
    weapon: str,
    shells_cnt: int,
    total_cas: int,
    target_unit_id: str,
    target_side: str,
    cover_level: int = 0,
    arm_cas: int = 0,
) -> pd.DataFrame:
    """Build a single-row DataFrame in the standard battle log format.

    cover_level is stored in log_result so analysts can filter by target cover.
    Both cas_inf fields are always numeric (0 for the non-targeted side).
    """
    if initiator == "blue":
        # blue fires at red — weapon/shells in blue columns, cas+id in red columns
        row = {
            "current_time":       str(current_time),
            "initiator":          initiator,
            "log_blue_id":        "",
            "log_blue_type":      weapon,
            "log_blue_inf_force": shells_cnt,
            "log_blue_arm_force": "",
            "log_blue_cas_inf":   0,
            "log_blue_cas_armor": "",
            "log_red_id":         target_unit_id,
            "log_red_type":       "",
            "log_red_inf_force":  "",
            "log_red_arm_force":  "",
            "log_red_cas_inf":    total_cas,
            "log_red_cas_armor":  arm_cas,
            "log_attack_type":    "art_air_fire",
            "log_result":         cover_level,
        }
    else:
        # red fires at blue — weapon/shells in red columns, cas+id in blue columns
        row = {
            "current_time":       str(current_time),
            "initiator":          initiator,
            "log_blue_id":        target_unit_id,
            "log_blue_type":      "",
            "log_blue_inf_force": "",
            "log_blue_arm_force": "",
            "log_blue_cas_inf":   total_cas,
            "log_blue_cas_armor": arm_cas,
            "log_red_id":         "",
            "log_red_type":       weapon,
            "log_red_inf_force":  shells_cnt,
            "log_red_arm_force":  "",
            "log_red_cas_inf":    0,
            "log_red_cas_armor":  "",
            "log_attack_type":    "art_air_fire",
            "log_result":         cover_level,
        }
    return pd.DataFrame([row])


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def artillery_strike(
    target_unit: Unit,
    cover_level: int,
    shells_cnt: int,
    weapon: str,
    artillery_table: pd.DataFrame,
    logs=None,
    current_time=None,
) -> dict:
    """Simulate an artillery/bombing salvo against target_unit.

    The function:
    1. Looks up balance row (weapon + cover_level) from artillery_table.
    2. Places soldiers randomly inside a 100×100 unit_territory at the centre
       of a 400×400 grid (one soldier per cell).
    3. For each shell: picks a random landing point inside the
       accuracy×accuracy damage_territory (also centred), then checks every
       soldier's distance and applies/upgrades their injury status.
    4. Moves all non-alive soldiers from alive_df to cas_df with their final
       status set (killed / heavy / light).
    5. If logs and current_time are provided, appends a log row in the standard
       battle log format.

    Args:
        target_unit:     Unit object (infantry). alive_df and cas_df updated in-place.
        cover_level:     0-3 — must match a row in artillery_table.
        shells_cnt:      Number of shells in the salvo.
        weapon:          Weapon type string matching artillery_table['weapon'].
        artillery_table: DataFrame with columns: weapon, cover, killed, heavy, light, accuracy.
        logs:            Optional. Pass either:
                           - an object with a .logs attribute (e.g. EngagementResult /
                             battle_result) — its .logs is updated IN PLACE, just like
                             target_unit is mutated;
                           - or a plain pd.DataFrame — the updated copy is returned
                             under key 'logs' in the result dict.
        current_time:    Timestamp / datetime for the log row.

    Returns:
        dict with keys:
            'killed', 'heavy', 'light' — integer casualty counts.
            'logs'                      — updated log DataFrame (only present when a
                                          plain DataFrame was passed as logs).
    """

    # ------------------------------------------------------------------
    # 1. Fetch balance row
    # ------------------------------------------------------------------
    row = artillery_table[
        (artillery_table["weapon"] == weapon) &
        (artillery_table["cover"]  == cover_level)
    ]
    if row.empty:
        raise ValueError(
            f"No artillery_table row for weapon='{weapon}', cover={cover_level}"
        )

    r_kill    = int(row.iloc[0]["killed"])
    r_heavy   = int(row.iloc[0]["heavy"])
    r_light   = int(row.iloc[0]["light"])
    accuracy  = int(row.iloc[0]["accuracy"])
    r_arm_kill = int(row.iloc[0]["arm_kill"]) if "arm_kill" in row.columns else 0

    # ------------------------------------------------------------------
    # 2. Determine infantry and armor components of the target
    # ------------------------------------------------------------------
    if target_unit.overall_type == "arm":
        inf_unit   = None
        armor_unit = target_unit
    elif (
        target_unit.overall_type == "mech"
        and target_unit.armor_part not in (None, [])
        and len(target_unit.armor_part.alive_df) > 0
    ):
        inf_unit   = target_unit
        armor_unit = target_unit.armor_part
    else:
        inf_unit   = target_unit
        armor_unit = None

    # Validate that there is something to shoot at
    inf_alive   = inf_unit is not None and inf_unit.alive_df is not None and not inf_unit.alive_df.empty
    armor_alive = armor_unit is not None and armor_unit.alive_df is not None and not armor_unit.alive_df.empty

    if not inf_alive and not armor_alive:
        return {"killed": 0, "heavy": 0, "light": 0, "arm_killed": 0}

    if inf_alive and "soldier_uid" not in inf_unit.alive_df.columns:
        raise ValueError("target_unit.alive_df must contain 'soldier_uid' column")

    # ------------------------------------------------------------------
    # 3. Collect UIDs for both infantry and armor
    # ------------------------------------------------------------------
    soldier_uids = list(inf_unit.alive_df["soldier_uid"]) if inf_alive else []

    # Armor UID column: prefer 'armor_id', fall back to index-based label
    if armor_alive:
        armor_df = armor_unit.alive_df
        if "armor_id" in armor_df.columns:
            armor_uids = list(armor_df["armor_id"])
        else:
            armor_uids = [f"__arm_{i}" for i in range(len(armor_df))]
    else:
        armor_uids = []

    total_entities = len(soldier_uids) + len(armor_uids)

    # ------------------------------------------------------------------
    # 4. Place all entities randomly in unit_territory (no two on same cell)
    # ------------------------------------------------------------------
    all_cells = [
        (x, y)
        for x in range(CENTER - UNIT_HALF, CENTER + UNIT_HALF)
        for y in range(CENTER - UNIT_HALF, CENTER + UNIT_HALF)
    ]

    if total_entities > len(all_cells):
        raise ValueError(
            f"Too many entities ({total_entities}) for unit_territory "
            f"({len(all_cells)} cells). Increase UNIT_HALF."
        )

    chosen_cells  = random.sample(all_cells, total_entities)
    inf_positions   = dict(zip(soldier_uids, chosen_cells[:len(soldier_uids)]))
    armor_positions = dict(zip(armor_uids,   chosen_cells[len(soldier_uids):]))

    # ------------------------------------------------------------------
    # 5. Initialise status trackers
    # ------------------------------------------------------------------
    soldier_status: dict[str, str] = {uid: "alive" for uid in soldier_uids}
    armor_status:   dict[str, str] = {uid: "alive" for uid in armor_uids}

    # ------------------------------------------------------------------
    # 6. Compute damage_territory bounds
    # ------------------------------------------------------------------
    half_acc  = accuracy // 2
    dmg_x_min = CENTER - half_acc
    dmg_x_max = CENTER + half_acc
    dmg_y_min = CENTER - half_acc
    dmg_y_max = CENTER + half_acc

    # ------------------------------------------------------------------
    # 7. Fire each shell
    # ------------------------------------------------------------------
    for _ in range(shells_cnt):
        lx = random.randint(dmg_x_min, dmg_x_max)
        ly = random.randint(dmg_y_min, dmg_y_max)

        # Infantry checks
        for uid, (sx, sy) in inf_positions.items():
            if soldier_status[uid] == "killed":
                continue

            dist = math.sqrt((lx - sx) ** 2 + (ly - sy) ** 2)

            if dist <= r_kill:
                hit_zone = "killed"
            elif dist <= r_heavy:
                hit_zone = "heavy"
            elif dist <= r_light:
                hit_zone = "light"
            else:
                continue

            soldier_status[uid] = _upgrade_status(soldier_status[uid], hit_zone)

        # Armor checks
        if r_arm_kill > 0:
            for uid, (ax, ay) in armor_positions.items():
                if armor_status[uid] == "killed":
                    continue

                dist = math.sqrt((lx - ax) ** 2 + (ly - ay) ** 2)
                if dist <= r_arm_kill:
                    armor_status[uid] = "killed"

    # ------------------------------------------------------------------
    # 8. Apply infantry results back to inf_unit
    # ------------------------------------------------------------------
    if inf_alive:
        alive_df = inf_unit.alive_df
        casualties = {uid: st for uid, st in soldier_status.items() if st != "alive"}
        if casualties:
            cas_mask = alive_df["soldier_uid"].isin(casualties)
            cas_rows = alive_df[cas_mask].copy()
            cas_rows["status"] = cas_rows["soldier_uid"].map(casualties)
            inf_unit.cas_df   = pd.concat([inf_unit.cas_df, cas_rows], ignore_index=True)
            inf_unit.alive_df = alive_df[~cas_mask].reset_index(drop=True)

    # ------------------------------------------------------------------
    # 9. Apply armor results back to armor_unit
    # ------------------------------------------------------------------
    arm_killed = 0
    if armor_alive:
        arm_killed = sum(1 for st in armor_status.values() if st == "killed")
        if arm_killed > 0:
            armor_df = armor_unit.alive_df
            uid_col  = "armor_id" if "armor_id" in armor_df.columns else None
            if uid_col is not None:
                killed_uids = {uid for uid, st in armor_status.items() if st == "killed"}
                cas_mask    = armor_df[uid_col].isin(killed_uids)
            else:
                # fallback: kill first arm_killed rows
                cas_mask = armor_df.index < arm_killed
            cas_rows = armor_df[cas_mask].copy()
            if "status" in armor_unit.cas_df.columns or len(armor_unit.cas_df) == 0:
                if "status" not in cas_rows.columns:
                    cas_rows["status"] = "killed"
                else:
                    cas_rows["status"] = "killed"
            armor_unit.cas_df   = pd.concat([armor_unit.cas_df, cas_rows], ignore_index=True)
            armor_unit.alive_df = armor_df[~cas_mask].reset_index(drop=True)

    # ------------------------------------------------------------------
    # 10. Build summary counts and print
    # ------------------------------------------------------------------
    counts: dict[str, int] = {"killed": 0, "heavy": 0, "light": 0}
    for st in soldier_status.values():
        if st in counts:
            counts[st] += 1
    counts["arm_killed"] = arm_killed

    inf_alive_after  = len(inf_unit.alive_df)  if inf_alive  else 0
    arm_alive_after  = len(armor_unit.alive_df) if armor_alive else 0

    print(
        f"  Залп [{weapon}] cover={cover_level} shells={shells_cnt}: "
        f"killed={counts['killed']}, heavy={counts['heavy']}, light={counts['light']}, "
        f"arm_killed={arm_killed} "
        f"| inf alive={inf_alive_after}, arm alive={arm_alive_after}"
    )

    # ------------------------------------------------------------------
    # 11. Append log row
    # ------------------------------------------------------------------
    if logs is not None and current_time is not None:
        initiator = "blue" if target_unit.side == "red" else "red"
        total_cas = counts["killed"] + counts["heavy"] + counts["light"]

        log_row = _build_arty_log_row(
            current_time=current_time,
            initiator=initiator,
            weapon=weapon,
            shells_cnt=shells_cnt,
            total_cas=total_cas,
            target_unit_id=target_unit.unit_id,
            target_side=target_unit.side,
            cover_level=cover_level,
            arm_cas=arm_killed,
        )

        if hasattr(logs, "logs"):
            logs.logs = pd.concat([logs.logs, log_row], ignore_index=True)
        else:
            counts["logs"] = pd.concat([logs, log_row], ignore_index=True)

    return counts
