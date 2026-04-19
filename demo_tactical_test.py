from __future__ import annotations

import random
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from force_manager import ForceManager
from ground_engine import GroundEngine, BattleContext


# ============================================================
# CONFIG
# ============================================================
PLAYER_FILE = "player_brigade.xlsx"
ENEMY_FILE = "enemy_brigade.xlsx"

# Какие подразделения отправляем на бой.
# level может быть: "battalion", "company", "platoon", "squad"
PLAYER_LEVEL = "battalion"
PLAYER_FORMATIONS = ["B1"]

ENEMY_LEVEL = "battalion"
ENEMY_FORMATIONS = ["B1"]

# Сколько временных ground-юнитов собрать на сторону
TARGET_UNITS_PER_SIDE = 6

# Диапазон количества боёв за один тактический прогон
MIN_BATTLES = 3
MAX_BATTLES = 15

# Диапазоны случайных параметров столкновения
DISTANCE_RANGE = (1, 3)
COVER_RANGE = (1, 2)
ELEVATION_RANGE = (0, 0)  # пока высоту не рандомим

# Сохранять результаты в новые файлы
PLAYER_OUTPUT_FILE = "player_brigade_after_battle.xlsx"
ENEMY_OUTPUT_FILE = "enemy_brigade_after_battle.xlsx"
LOG_OUTPUT_FILE = "tactical_battle_log.xlsx"

# Время старта тактического прогона
START_TIME = datetime(2026, 4, 19, 8, 0)
TIME_STEP_MINUTES = 15
# ============================================================


LOG_COLUMNS = [
    'current_time', 'initiator',
    'log_blue_id', 'log_blue_type', 'log_blue_inf_force', 'log_blue_arm_force',
    'log_blue_cas_inf', 'log_blue_cas_armor',
    'log_red_id', 'log_red_type', 'log_red_inf_force', 'log_red_arm_force',
    'log_red_cas_inf', 'log_red_cas_armor',
    'log_attack_type', 'log_result'
]


class TacticalTestRunner:
    def __init__(self, player_file: str, enemy_file: str):
        self.player_manager = ForceManager.from_excel(player_file)
        self.enemy_manager = ForceManager.from_excel(enemy_file)
        self.engine = GroundEngine()
        self.logs = pd.DataFrame(columns=LOG_COLUMNS)
        self.current_time = START_TIME

    @staticmethod
    def _alive_units(units):
        return [u for u in units if len(u.alive_df) > 0]

    @staticmethod
    def _choose_random_context() -> BattleContext:
        attacker_cover = random.randint(*COVER_RANGE)
        defender_cover = random.randint(*COVER_RANGE)
        attacker_elevation = random.randint(*ELEVATION_RANGE)
        defender_elevation = random.randint(*ELEVATION_RANGE)
        distance = random.randint(*DISTANCE_RANGE)

        # В большинстве столкновений предполагаем ответный огонь
        defender_returns_fire = True

        return BattleContext(
            attacker_cover=attacker_cover,
            defender_cover=defender_cover,
            attacker_elevation=attacker_elevation,
            defender_elevation=defender_elevation,
            distance=distance,
            defender_returns_fire=defender_returns_fire,
            attacker_berserk=False,
            defender_berserk=False,
        )

    def build_forces(self):
        player_units, player_plan = self.player_manager.generate_ground_units(
            level=PLAYER_LEVEL,
            formation_uids=PLAYER_FORMATIONS,
            target_units=TARGET_UNITS_PER_SIDE,
            side="blue",
            unit_prefix="BLU",
        )

        enemy_units, enemy_plan = self.enemy_manager.generate_ground_units(
            level=ENEMY_LEVEL,
            formation_uids=ENEMY_FORMATIONS,
            target_units=TARGET_UNITS_PER_SIDE,
            side="red",
            unit_prefix="RED",
        )

        return player_units, enemy_units, player_plan, enemy_plan

    def run(self):
        player_units, enemy_units, player_plan, enemy_plan = self.build_forces()

        battle_count = random.randint(MIN_BATTLES, MAX_BATTLES)
        tactical_summary = []

        for battle_no in range(1, battle_count + 1):
            alive_blue = self._alive_units(player_units)
            alive_red = self._alive_units(enemy_units)

            if not alive_blue or not alive_red:
                print("Одна из сторон больше не имеет боеспособных временных юнитов. Прогон завершён раньше.")
                break

            attacker = random.choice(alive_blue)
            defender = random.choice(alive_red)
            context = self._choose_random_context()

            result = self.engine.resolve_engagement(
                attacker=attacker,
                defender=defender,
                context=context,
                logs=self.logs,
                current_time=self.current_time,
            )

            self.logs = result.logs
            self.current_time += timedelta(minutes=TIME_STEP_MINUTES)

            tactical_summary.append({
                "battle_no": battle_no,
                "time": result.log_row["current_time"],
                "blue_unit": result.log_row["log_blue_id"],
                "red_unit": result.log_row["log_red_id"],
                "attack_type": result.log_row["log_attack_type"],
                "result": result.log_row["log_result"],
                "blue_force_before": result.log_row["log_blue_inf_force"],
                "blue_cas_inf": result.log_row["log_blue_cas_inf"],
                "blue_cas_armor": result.log_row["log_blue_cas_armor"],
                "red_force_before": result.log_row["log_red_inf_force"],
                "red_cas_inf": result.log_row["log_red_cas_inf"],
                "red_cas_armor": result.log_row["log_red_cas_armor"],
                "distance": context.distance,
                "blue_cover": context.attacker_cover,
                "red_cover": context.defender_cover,
            })

        # Применяем итоговые изменения временных юнитов обратно в master tables
        self.player_manager.apply_many_battle_results(player_units)
        self.enemy_manager.apply_many_battle_results(enemy_units)

        # Сохраняем обновлённые таблицы и лог
        self.player_manager.save_to_excel(PLAYER_OUTPUT_FILE)
        self.enemy_manager.save_to_excel(ENEMY_OUTPUT_FILE)

        summary_df = pd.DataFrame(tactical_summary)
        with pd.ExcelWriter(LOG_OUTPUT_FILE, engine="openpyxl") as writer:
            self.logs.to_excel(writer, sheet_name="battle_log", index=False)
            summary_df.to_excel(writer, sheet_name="summary", index=False)
            player_plan.to_excel(writer, sheet_name="player_plan", index=False)
            enemy_plan.to_excel(writer, sheet_name="enemy_plan", index=False)

        return {
            "battle_count": len(tactical_summary),
            "logs": self.logs,
            "summary": summary_df,
            "player_plan": player_plan,
            "enemy_plan": enemy_plan,
            "player_units": player_units,
            "enemy_units": enemy_units,
        }


def print_short_summary(result_bundle: dict):
    summary = result_bundle["summary"]
    print("=" * 60)
    print(f"Проведено боёв: {len(summary)}")
    print("=" * 60)

    if len(summary) == 0:
        print("Боёв не было.")
        return

    for _, row in summary.iterrows():
        blue_after = row["blue_force_before"] - row["blue_cas_inf"]
        red_after = row["red_force_before"] - row["red_cas_inf"]
        print(
            f"Бой #{row['battle_no']} | {row['time']} | "
            f"{row['blue_unit']} vs {row['red_unit']} | "
            f"dist={row['distance']} | cover {row['blue_cover']}:{row['red_cover']} | "
            f"{row['result']} | "
            f"blue {row['blue_force_before']} -> {blue_after} (-{row['blue_cas_inf']}) | "
            f"red {row['red_force_before']} -> {red_after} (-{row['red_cas_inf']})"
        )


if __name__ == "__main__":
    # Проверяем, что входные файлы существуют
    for file_path in [PLAYER_FILE, ENEMY_FILE]:
        if not Path(file_path).exists():
            raise FileNotFoundError(
                f"Не найден файл: {file_path}. Положи файлы рядом со скриптом или поправь CONFIG."
            )

    runner = TacticalTestRunner(PLAYER_FILE, ENEMY_FILE)
    result_bundle = runner.run()
    print_short_summary(result_bundle)
    print("\nФайлы сохранены:")
    print(f"- {PLAYER_OUTPUT_FILE}")
    print(f"- {ENEMY_OUTPUT_FILE}")
    print(f"- {LOG_OUTPUT_FILE}")
