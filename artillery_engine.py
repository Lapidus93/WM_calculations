from __future__ import annotations

import math
import random

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


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def artillery_strike(
    target_unit: Unit,
    cover_level: int,
    shells_cnt: int,
    weapon: str,
    artillery_table: pd.DataFrame,
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

    Args:
        target_unit:      Unit object (infantry). alive_df and cas_df are
                          updated in-place.
        cover_level:      0-3 — must match a row in artillery_table.
        shells_cnt:       Number of shells in the salvo.
        weapon:           Weapon type string matching artillery_table['weapon'].
        artillery_table:  DataFrame with columns:
                          weapon, cover, killed, heavy, light, accuracy.

    Returns:
        dict with keys 'killed', 'heavy', 'light' (integer counts).
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

    r_kill   = int(row.iloc[0]["killed"])
    r_heavy  = int(row.iloc[0]["heavy"])
    r_light  = int(row.iloc[0]["light"])
    accuracy = int(row.iloc[0]["accuracy"])

    # ------------------------------------------------------------------
    # 2. Validate target unit
    # ------------------------------------------------------------------
    alive_df = target_unit.alive_df
    if alive_df is None or alive_df.empty:
        return {"killed": 0, "heavy": 0, "light": 0}

    if "soldier_uid" not in alive_df.columns:
        raise ValueError("target_unit.alive_df must contain 'soldier_uid' column")

    soldier_uids = list(alive_df["soldier_uid"])

    # ------------------------------------------------------------------
    # 3. Place soldiers randomly in unit_territory (no two on same cell)
    # ------------------------------------------------------------------
    all_cells = [
        (x, y)
        for x in range(CENTER - UNIT_HALF, CENTER + UNIT_HALF)
        for y in range(CENTER - UNIT_HALF, CENTER + UNIT_HALF)
    ]

    if len(soldier_uids) > len(all_cells):
        raise ValueError(
            f"Too many soldiers ({len(soldier_uids)}) for unit_territory "
            f"({len(all_cells)} cells). Increase UNIT_HALF."
        )

    chosen_cells = random.sample(all_cells, len(soldier_uids))
    positions    = dict(zip(soldier_uids, chosen_cells))

    # ------------------------------------------------------------------
    # 4. Initialise per-soldier status tracker
    # ------------------------------------------------------------------
    soldier_status: dict[str, str] = {uid: "alive" for uid in soldier_uids}

    # ------------------------------------------------------------------
    # 5. Compute damage_territory bounds
    # ------------------------------------------------------------------
    half_acc  = accuracy // 2
    dmg_x_min = CENTER - half_acc
    dmg_x_max = CENTER + half_acc
    dmg_y_min = CENTER - half_acc
    dmg_y_max = CENTER + half_acc

    # ------------------------------------------------------------------
    # 6. Fire each shell
    # ------------------------------------------------------------------
    for _ in range(shells_cnt):
        lx = random.randint(dmg_x_min, dmg_x_max)
        ly = random.randint(dmg_y_min, dmg_y_max)

        for uid, (sx, sy) in positions.items():
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
                continue  # shell missed this soldier

            soldier_status[uid] = _upgrade_status(soldier_status[uid], hit_zone)

    # ------------------------------------------------------------------
    # 7. Apply results back to target_unit
    # ------------------------------------------------------------------
    casualties = {uid: st for uid, st in soldier_status.items() if st != "alive"}

    if casualties:
        cas_mask = alive_df["soldier_uid"].isin(casualties)
        cas_rows = alive_df[cas_mask].copy()
        cas_rows["status"] = cas_rows["soldier_uid"].map(casualties)

        target_unit.cas_df = pd.concat(
            [target_unit.cas_df, cas_rows], ignore_index=True
        )
        target_unit.alive_df = alive_df[~cas_mask].reset_index(drop=True)

    # ------------------------------------------------------------------
    # 8. Build and print summary
    # ------------------------------------------------------------------
    counts: dict[str, int] = {"killed": 0, "heavy": 0, "light": 0}
    for st in soldier_status.values():
        if st in counts:
            counts[st] += 1

    print(
        f"  Залп [{weapon}] cover={cover_level} shells={shells_cnt}: "
        f"killed={counts['killed']}, heavy={counts['heavy']}, light={counts['light']} "
        f"| alive after={len(target_unit.alive_df)}"
    )
    return counts
