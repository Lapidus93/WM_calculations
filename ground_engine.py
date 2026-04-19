from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
import math
import random

import pandas as pd

from wm_unit import Unit


@dataclass
class BattleContext:
    """Parameters of one ground-level engagement.

    Notes:
    - cover: 0..4
    - distance: your existing abstract distance scale
    - elevation: relative terrain advantage scale
    - defender_returns_fire: False means side attack / attack without answer
    - attacker_berserk / defender_berserk: True means berserk bonus is active
    - armor_is_moving / armor_is_far are only used in infantry-vs-armor RPG attack
    """

    attacker_cover: int = 0
    defender_cover: int = 0
    attacker_elevation: int = 0
    defender_elevation: int = 0
    distance: int = 0
    defender_returns_fire: bool = True
    attacker_berserk: bool = False
    defender_berserk: bool = False
    armor_is_moving: bool = False
    armor_is_far: bool = False


@dataclass
class EngagementResult:
    attacker: Unit
    defender: Unit
    logs: pd.DataFrame
    attack_type: str
    result: str
    attacker_inf_losses: int = 0
    attacker_armor_losses: int = 0
    defender_inf_losses: int = 0
    defender_armor_losses: int = 0
    meta: Dict[str, object] = field(default_factory=dict)


class GroundEngine:
    """Refactored ground combat resolver.

    This engine is intentionally conservative:
    - keeps your current combat model and result labels,
    - removes direct input() from combat resolution,
    - splits base_attack logic into small resolvers.
    """

    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def resolve_engagement(
        self,
        attacker: Unit,
        defender: Unit,
        context: BattleContext,
        logs: pd.DataFrame,
        current_time,
    ) -> EngagementResult:
        self._apply_context(attacker, defender, context)
        attacker.update_current_type()
        defender.update_current_type()

        pre_battle_snapshot = self._make_force_snapshot(attacker, defender)
        battle_type = (attacker.overall_type, defender.overall_type)

        if battle_type == ("inf", "arm"):
            result = self._resolve_inf_vs_arm(attacker, defender, logs, current_time, pre_battle_snapshot, context)
        elif battle_type == ("arm", "arm"):
            result = self._resolve_arm_vs_arm(attacker, defender, logs, current_time, pre_battle_snapshot)
        elif battle_type == ("arm", "mech"):
            result = self._resolve_arm_vs_mech(attacker, defender, logs, current_time, pre_battle_snapshot)
        elif battle_type == ("mech", "inf"):
            result = self._resolve_mech_vs_inf(attacker, defender, logs, current_time, pre_battle_snapshot)
        elif battle_type == ("mech", "mech"):
            result = self._resolve_mech_vs_mech(attacker, defender, logs, current_time, pre_battle_snapshot)
        elif battle_type == ("mech", "arm"):
            result = self._resolve_mech_vs_arm(attacker, defender, logs, current_time, pre_battle_snapshot)
        elif battle_type == ("arm", "inf"):
            result = self._resolve_arm_vs_inf(attacker, defender, logs, current_time, pre_battle_snapshot)
        elif battle_type == ("inf", "mech"):
            result = self._resolve_inf_vs_mech(attacker, defender, logs, current_time, pre_battle_snapshot)
        else:
            result = self._resolve_inf_vs_inf(attacker, defender, logs, current_time, pre_battle_snapshot)

        result.attacker.update_current_type()
        result.defender.update_current_type()
        return result

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    def _apply_context(self, attacker: Unit, defender: Unit, context: BattleContext) -> None:
        attacker.last_parameters = {
            "elev_pos": int(context.attacker_elevation),
            "cover_level": int(context.attacker_cover),
            "target_distance": int(context.distance),
            "enemy_unit_id": defender.unit_id if context.defender_returns_fire else "",
            "berserk_mode": "1" if context.attacker_berserk else 0,
        }
        defender.last_parameters = {
            "elev_pos": int(context.defender_elevation),
            "cover_level": int(context.defender_cover),
            "target_distance": int(context.distance),
            "enemy_unit_id": attacker.unit_id if context.defender_returns_fire else "",
            "berserk_mode": "1" if context.defender_berserk else 0,
        }

    # ------------------------------------------------------------------
    # Small reusable helpers
    # ------------------------------------------------------------------
    def _build_result(
        self,
        attacker: Unit,
        defender: Unit,
        logs: pd.DataFrame,
        current_time,
        attack_type: str,
        result: str,
        attacker_inf_losses: int = 0,
        attacker_armor_losses: int = 0,
        defender_inf_losses: int = 0,
        defender_armor_losses: int = 0,
        meta: Optional[Dict[str, object]] = None,
        pre_battle_snapshot: Optional[Dict[str, object]] = None,
    ) -> EngagementResult:
        updated_logs = self._append_log(
            logs=logs,
            current_time=current_time,
            attacker=attacker,
            defender=defender,
            attack_type=attack_type,
            result=result,
            attacker_inf_losses=attacker_inf_losses,
            attacker_armor_losses=attacker_armor_losses,
            defender_inf_losses=defender_inf_losses,
            defender_armor_losses=defender_armor_losses,
            pre_battle_snapshot=pre_battle_snapshot,
        )
        return EngagementResult(
            attacker=attacker,
            defender=defender,
            logs=updated_logs,
            attack_type=attack_type,
            result=result,
            attacker_inf_losses=attacker_inf_losses,
            attacker_armor_losses=attacker_armor_losses,
            defender_inf_losses=defender_inf_losses,
            defender_armor_losses=defender_armor_losses,
            meta=meta or {},
        )

    @staticmethod
    def _count_force(unit: Unit) -> Tuple[int, int]:
        inf_force = len(unit.alive_df) if unit.overall_type in ["inf", "mech"] else 0
        armor_force = 0
        if unit.overall_type == "arm":
            armor_force = len(unit.alive_df)
        elif unit.overall_type == "mech" and unit.armor_part not in (None, []):
            armor_force = len(unit.armor_part.alive_df)
        return inf_force, armor_force

    def _make_force_snapshot(self, attacker: Unit, defender: Unit) -> Dict[str, object]:
        attacker_inf_force, attacker_armor_force = self._count_force(attacker)
        defender_inf_force, defender_armor_force = self._count_force(defender)
        return {
            "attacker_id": attacker.unit_id,
            "attacker_type": attacker.overall_type,
            "attacker_inf_force": attacker_inf_force,
            "attacker_armor_force": attacker_armor_force,
            "defender_id": defender.unit_id,
            "defender_type": defender.overall_type,
            "defender_inf_force": defender_inf_force,
            "defender_armor_force": defender_armor_force,
        }

    def _append_log(
        self,
        logs: pd.DataFrame,
        current_time,
        attacker: Unit,
        defender: Unit,
        attack_type: str,
        result: str,
        attacker_inf_losses: int,
        attacker_armor_losses: int,
        defender_inf_losses: int,
        defender_armor_losses: int,
        pre_battle_snapshot: Optional[Dict[str, object]] = None,
    ) -> pd.DataFrame:
        snapshot = pre_battle_snapshot or self._make_force_snapshot(attacker, defender)
        attacker_inf_force = snapshot["attacker_inf_force"]
        attacker_armor_force = snapshot["attacker_armor_force"]
        defender_inf_force = snapshot["defender_inf_force"]
        defender_armor_force = snapshot["defender_armor_force"]

        if attacker.side == "blue":
            new_row = [
                str(current_time),
                attacker.side,
                snapshot["attacker_id"],
                snapshot["attacker_type"],
                attacker_inf_force,
                attacker_armor_force,
                attacker_inf_losses,
                attacker_armor_losses,
                snapshot["defender_id"],
                snapshot["defender_type"],
                defender_inf_force,
                defender_armor_force,
                defender_inf_losses,
                defender_armor_losses,
                attack_type,
                result,
            ]
        else:
            new_row = [
                str(current_time),
                attacker.side,
                snapshot["defender_id"],
                snapshot["defender_type"],
                defender_inf_force,
                defender_armor_force,
                defender_inf_losses,
                defender_armor_losses,
                snapshot["attacker_id"],
                snapshot["attacker_type"],
                attacker_inf_force,
                attacker_armor_force,
                attacker_inf_losses,
                attacker_armor_losses,
                attack_type,
                result,
            ]

        row_df = pd.DataFrame(
            [new_row],
            columns=[
                "current_time",
                "initiator",
                "log_blue_id",
                "log_blue_type",
                "log_blue_inf_force",
                "log_blue_arm_force",
                "log_blue_cas_inf",
                "log_blue_cas_armor",
                "log_red_id",
                "log_red_type",
                "log_red_inf_force",
                "log_red_arm_force",
                "log_red_cas_inf",
                "log_red_cas_armor",
                "log_attack_type",
                "log_result",
            ],
        )
        return pd.concat([logs, row_df], ignore_index=True)

    @staticmethod
    def _armor_alive(unit: Unit) -> bool:
        return unit.armor_part not in (None, []) and len(unit.armor_part.alive_df) > 0

    def _manage_kills_safe(self, unit_df: pd.DataFrame, kills: int, cas_type: str) -> None:
        if kills <= 0 or len(unit_df) == 0 or cas_type not in unit_df.columns:
            return
        for _ in range(kills):
            rnd_index = unit_df.sample(n=1, replace=False).index[0]
            unit_df.loc[rnd_index, cas_type] += 1

    @staticmethod
    def _get_size_decrease(unit: Unit) -> float:
        if unit.overall_type == "arm":
            return 1.0
        size = str(unit.size)
        if size == "CM":
            return 0.6
        if size == "PT":
            return 0.8
        if size == "SQ":
            return 0.9
        return 1.0

    @staticmethod
    def _cover_safer(cover: int) -> float:
        if cover == 0:
            return 1.0
        if cover == 1:
            return 0.5
        return 0.3

    def _calculate_attack_power(self, unit: Unit) -> int:
        size_decrease = self._get_size_decrease(unit)
        berserk_mode = 1.5 if str(unit.last_parameters.get("berserk_mode")) == "1" else 1.0

        cover_level = int(unit.last_parameters.get("cover_level", 0))
        cover_attack_bonus = pow(1.1, cover_level + 1)

        elev_pos = int(unit.last_parameters.get("elev_pos", 0))
        elevation_bonus = pow(1.4, elev_pos + 1)

        base_power = unit.alive_df["power"].sum() if "power" in unit.alive_df.columns else len(unit.alive_df)
        attack_power = (base_power - len(unit.cas_df) / 5) * size_decrease * cover_attack_bonus * berserk_mode * elevation_bonus

        if self._armor_alive(unit):
            attack_power += unit.armor_part.alive_df["power"].sum()

        return int(round(attack_power, 0))

    def _calculate_cas_amount(self, attacker: Unit, defender: Unit, koef: float, result_label: str) -> int:
        attack_power = attacker.alive_df["power"].sum() if "power" in attacker.alive_df.columns else len(attacker.alive_df)

        distance = int(attacker.last_parameters.get("target_distance", 0))
        distance_factor = pow(0.75, distance + 1)

        defender_cover = int(defender.last_parameters.get("cover_level", 0))

        elev_diff = int(attacker.last_parameters.get("elev_pos", 0)) - int(defender.last_parameters.get("elev_pos", 0))
        elevation_bonus = pow(1.4, elev_diff)

        enemy_cas = attack_power * koef * distance_factor * elevation_bonus

        if result_label in ["засада", "поражение"] and str(defender.last_parameters.get("berserk_mode")) == "1":
            berserk_koef = self.rng.choice([1, 1.5, 2])
            enemy_cas *= berserk_koef

        enemy_cas = max(3, int(round(enemy_cas, 0)))

        casualties = 0
        for _ in range(3):
            casualties += self.rng.randint(1, enemy_cas)
        casualties = casualties - 3 - defender_cover * 2
        casualties = max(0, casualties)

        max_casualties = int(round(self._cover_safer(defender_cover) * len(defender.alive_df), 0))
        return min(casualties, max_casualties)

    def _calculate_side_attack_cas_amount(self, attacker: Unit, defender: Unit) -> int:
        distance = int(attacker.last_parameters.get("target_distance", 0))
        cover = int(defender.last_parameters.get("cover_level", 0))
        attack_power = attacker.alive_df["power"].sum() if "power" in attacker.alive_df.columns else len(attacker.alive_df)

        final_power = int(round(5 * math.sqrt(max(1, attack_power)) * (0.72 ** distance) * (0.75 ** cover)))

        attack_roll = 0
        defence_roll = 0

        for _ in range(3):
            attack_roll += self.rng.randint(1, max(1, final_power))
        attack_roll -= 3

        for _ in range(3):
            defence_roll += self.rng.randint(1, 10)

        casualties = max(0, attack_roll - defence_roll)
        max_casualties = int(round(self._cover_safer(cover) * len(defender.alive_df), 0))
        return min(casualties, max_casualties)

    def _resolve_direct_attack(self, attacker: Unit, defender: Unit, attack_scale: str) -> Tuple[str, int, int]:
        def calculate_result(team1: int, team2: int) -> Tuple[str, str]:
            t1 = 1 if team1 < 2 else self.rng.randint(1, team1)
            t2 = 1 if team2 < 2 else self.rng.randint(1, team2)
            ratio = round(t1 / t2, 1)
            if ratio <= 0.3:
                return "засада", "разгром"
            if ratio < 0.8:
                return "поражение", "победа"
            if ratio <= 1.25:
                return "ничья", "ничья"
            if ratio < 3.33:
                return "победа", "поражение"
            return "разгром", "засада"

        def calculate_koef(result_label: str) -> float:
            mapping = {
                "засада": 0.03,
                "поражение": 0.03,
                "ничья": 0.06,
                "победа": 0.18,
                "разгром": 0.65,
            }
            return mapping[result_label]

        team1_power = self._calculate_attack_power(attacker)
        team2_power = self._calculate_attack_power(defender)

        if attacker.overall_type == "arm" and attack_scale == "short":
            team1_power = int(round(team1_power / 2, 0))

        result1, result2 = calculate_result(team1_power, team2_power)
        enemy_koef = calculate_koef(result1)
        friendly_koef = calculate_koef(result2)

        if str(defender.last_parameters.get("enemy_unit_id", "")) != str(attacker.unit_id):
            enemy_losses = self._calculate_side_attack_cas_amount(attacker, defender)
            self._manage_kills_safe(attacker.alive_df, enemy_losses, "inf_kills")

            alive_df, cas_df = Unit.manage_casualties(defender.alive_df, defender.cas_df, enemy_losses)
            defender.alive_df = alive_df
            defender.cas_df = cas_df
            return "side_attack", 0, enemy_losses

        enemy_losses = self._calculate_cas_amount(attacker, defender, enemy_koef, result2)
        friendly_losses = self._calculate_cas_amount(defender, attacker, friendly_koef, result1)

        self._manage_kills_safe(attacker.alive_df, enemy_losses, "inf_kills")
        self._manage_kills_safe(defender.alive_df, friendly_losses, "inf_kills")

        alive_df, cas_df = Unit.manage_casualties(attacker.alive_df, attacker.cas_df, friendly_losses)
        attacker.alive_df = alive_df
        attacker.cas_df = cas_df

        alive_df, cas_df = Unit.manage_casualties(defender.alive_df, defender.cas_df, enemy_losses)
        defender.alive_df = alive_df
        defender.cas_df = cas_df

        return result1, friendly_losses, enemy_losses

    def _inf_armor_attack(self, infantry_unit: Unit, armor_unit: Unit, context: BattleContext) -> Tuple[Unit, int]:
        shots = 3 if infantry_unit.size == "CM" else 1
        casualties = 0

        for _ in range(shots):
            chance = 70
            if context.armor_is_far:
                chance *= 0.5
            if context.armor_is_moving:
                chance *= 0.25
            shot_result = self.rng.randint(1, 100)
            if shot_result <= int(round(chance, 0)):
                casualties += 1

        casualties = min(casualties, len(armor_unit.alive_df))

        alive_df, cas_df = Unit.manage_casualties(armor_unit.alive_df, armor_unit.cas_df, casualties)
        armor_unit.alive_df = alive_df
        armor_unit.cas_df = cas_df

        self._manage_kills_safe(infantry_unit.alive_df, casualties, "apc_kills")
        return armor_unit, casualties

    def _armor_to_armor_attack(self, attacker_armor: Unit, defender_armor: Unit) -> Tuple[Unit, int]:
        distance = int(attacker_armor.last_parameters.get("target_distance", 0))
        casualties = 0
        for _ in range(len(attacker_armor.alive_df)):
            chance = 5 + distance
            shoot = self.rng.randint(1, 10)
            if shoot > chance:
                casualties += 1

        casualties = min(casualties, len(defender_armor.alive_df))
        alive_df, cas_df = Unit.manage_casualties(defender_armor.alive_df, defender_armor.cas_df, casualties)
        defender_armor.alive_df = alive_df
        defender_armor.cas_df = cas_df

        self._manage_kills_safe(attacker_armor.alive_df, casualties, "apc_kills")
        return defender_armor, casualties

    # ------------------------------------------------------------------
    # Battle type resolvers
    # ------------------------------------------------------------------
    def _resolve_inf_vs_arm(self, attacker: Unit, defender: Unit, logs: pd.DataFrame, current_time, pre_battle_snapshot, context: BattleContext) -> EngagementResult:
        defender, armor_losses = self._inf_armor_attack(attacker, defender, context)
        return self._build_result(
            attacker=attacker,
            defender=defender,
            logs=logs,
            current_time=current_time,
            attack_type="inf_attacks_armor",
            result="anti_armor_attack",
            defender_armor_losses=armor_losses,
            pre_battle_snapshot=pre_battle_snapshot,
        )

    def _resolve_arm_vs_arm(self, attacker: Unit, defender: Unit, logs: pd.DataFrame, current_time, pre_battle_snapshot) -> EngagementResult:
        defender, armor_losses = self._armor_to_armor_attack(attacker, defender)
        return self._build_result(
            attacker=attacker,
            defender=defender,
            logs=logs,
            current_time=current_time,
            attack_type="armor_attacks_armor",
            result="armor_duel",
            defender_armor_losses=armor_losses,
            pre_battle_snapshot=pre_battle_snapshot,
        )

    def _resolve_arm_vs_mech(self, attacker: Unit, defender: Unit, logs: pd.DataFrame, current_time, pre_battle_snapshot) -> EngagementResult:
        defender.armor_part, armor_losses = self._armor_to_armor_attack(attacker, defender.armor_part)
        result_label, attacker_inf_losses, defender_inf_losses = self._resolve_direct_attack(attacker, defender, attack_scale="short")
        return self._build_result(
            attacker=attacker,
            defender=defender,
            logs=logs,
            current_time=current_time,
            attack_type="armor_attacks_mech",
            result=result_label,
            attacker_armor_losses=0,
            attacker_inf_losses=attacker_inf_losses,
            defender_inf_losses=defender_inf_losses,
            defender_armor_losses=armor_losses,
            pre_battle_snapshot=pre_battle_snapshot,
        )

    def _resolve_mech_vs_inf(self, attacker: Unit, defender: Unit, logs: pd.DataFrame, current_time, pre_battle_snapshot) -> EngagementResult:
        _, armor_fire_back_losses, armor_inf_losses = self._resolve_direct_attack(attacker.armor_part, defender, attack_scale="full")
        result_label, attacker_inf_losses, defender_inf_losses = self._resolve_direct_attack(attacker, defender, attack_scale="full")

        attacker_armor_losses = 0
        if result_label in ["засада", "поражение"] and self._armor_alive(attacker):
            attacker.armor_part, attacker_armor_losses = self._inf_armor_attack(defender, attacker.armor_part, BattleContext())

        return self._build_result(
            attacker=attacker,
            defender=defender,
            logs=logs,
            current_time=current_time,
            attack_type="mech_attacks_inf",
            result=result_label,
            attacker_inf_losses=attacker_inf_losses + armor_fire_back_losses,
            attacker_armor_losses=attacker_armor_losses,
            defender_inf_losses=defender_inf_losses + armor_inf_losses,
            pre_battle_snapshot=pre_battle_snapshot,
        )

    def _resolve_mech_vs_mech(self, attacker: Unit, defender: Unit, logs: pd.DataFrame, current_time, pre_battle_snapshot) -> EngagementResult:
        defender.armor_part, defender_armor_losses = self._armor_to_armor_attack(attacker.armor_part, defender.armor_part)

        attacker_armor_losses = 0
        if len(defender.armor_part.alive_df) > 0:
            attacker.armor_part, attacker_armor_losses = self._armor_to_armor_attack(defender.armor_part, attacker.armor_part)

        result_label, attacker_inf_losses, defender_inf_losses = self._resolve_direct_attack(attacker, defender, attack_scale="short")

        if result_label in ["победа", "разгром"] and self._armor_alive(defender):
            defender.armor_part, extra_losses = self._inf_armor_attack(attacker, defender.armor_part, BattleContext())
            defender_armor_losses += extra_losses
        elif result_label in ["засада", "поражение"] and self._armor_alive(attacker):
            attacker.armor_part, extra_losses = self._inf_armor_attack(defender, attacker.armor_part, BattleContext())
            attacker_armor_losses += extra_losses

        return self._build_result(
            attacker=attacker,
            defender=defender,
            logs=logs,
            current_time=current_time,
            attack_type="mech_attacks_mech",
            result=result_label,
            attacker_inf_losses=attacker_inf_losses,
            attacker_armor_losses=attacker_armor_losses,
            defender_inf_losses=defender_inf_losses,
            defender_armor_losses=defender_armor_losses,
            pre_battle_snapshot=pre_battle_snapshot,
        )

    def _resolve_mech_vs_arm(self, attacker: Unit, defender: Unit, logs: pd.DataFrame, current_time, pre_battle_snapshot) -> EngagementResult:
        defender, defender_armor_losses = self._armor_to_armor_attack(attacker.armor_part, defender)
        extra_losses = 0
        if int(attacker.last_parameters.get("target_distance", 0)) <= 1:
            defender, extra_losses = self._inf_armor_attack(attacker, defender, BattleContext())
            defender_armor_losses += extra_losses

        return self._build_result(
            attacker=attacker,
            defender=defender,
            logs=logs,
            current_time=current_time,
            attack_type="mech_attacks_arm",
            result="combined_arms_attack",
            defender_armor_losses=defender_armor_losses,
            pre_battle_snapshot=pre_battle_snapshot,
        )

    def _resolve_arm_vs_inf(self, attacker: Unit, defender: Unit, logs: pd.DataFrame, current_time, pre_battle_snapshot) -> EngagementResult:
        result_label, attacker_inf_losses, defender_inf_losses = self._resolve_direct_attack(attacker, defender, attack_scale="full")
        return self._build_result(
            attacker=attacker,
            defender=defender,
            logs=logs,
            current_time=current_time,
            attack_type="arm_attacks_inf",
            result=result_label,
            attacker_inf_losses=attacker_inf_losses,
            defender_inf_losses=defender_inf_losses,
            pre_battle_snapshot=pre_battle_snapshot,
        )

    def _resolve_inf_vs_mech(self, attacker: Unit, defender: Unit, logs: pd.DataFrame, current_time, pre_battle_snapshot) -> EngagementResult:
        result_label, attacker_inf_losses, defender_inf_losses = self._resolve_direct_attack(attacker, defender, attack_scale="full")
        defender_armor_losses = 0
        if result_label in ["победа", "разгром"] and self._armor_alive(defender):
            defender.armor_part, defender_armor_losses = self._inf_armor_attack(attacker, defender.armor_part, BattleContext())

        return self._build_result(
            attacker=attacker,
            defender=defender,
            logs=logs,
            current_time=current_time,
            attack_type="inf_attacks_mech",
            result=result_label,
            attacker_inf_losses=attacker_inf_losses,
            defender_inf_losses=defender_inf_losses,
            defender_armor_losses=defender_armor_losses,
            pre_battle_snapshot=pre_battle_snapshot,
        )

    def _resolve_inf_vs_inf(self, attacker: Unit, defender: Unit, logs: pd.DataFrame, current_time, pre_battle_snapshot) -> EngagementResult:
        result_label, attacker_inf_losses, defender_inf_losses = self._resolve_direct_attack(attacker, defender, attack_scale="full")
        return self._build_result(
            attacker=attacker,
            defender=defender,
            logs=logs,
            current_time=current_time,
            attack_type="inf_attacks_inf",
            result=result_label,
            attacker_inf_losses=attacker_inf_losses,
            defender_inf_losses=defender_inf_losses,
            pre_battle_snapshot=pre_battle_snapshot,
        )
