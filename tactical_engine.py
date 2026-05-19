from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from force_manager import ForceManager
from ground_engine import GroundEngine, BattleContext


def tact_battle(files, player_data, enemy_data, other_data, injury_table=None):

    print('start')

    TIME_STEP_MINUTES = 15

    # ============================================================
    # CONFIG
    # ============================================================
    PLAYER_FILE = files['PLAYER_FILE']
    ENEMY_FILE = files['ENEMY_FILE']

    PLAYER_LEVEL = player_data['PLAYER_LEVEL']
    PLAYER_FORMATIONS = player_data['PLAYER_FORMATIONS']
    PLAYER_ARMOR_COUNT = player_data['PLAYER_ARMOR_COUNT']
    PLAYER_COVER_RANGE = player_data['PLAYER_COVER_RANGE']

    ENEMY_LEVEL = enemy_data['ENEMY_LEVEL']
    ENEMY_FORMATIONS = enemy_data['ENEMY_FORMATIONS']
    ENEMY_ARMOR_COUNT = enemy_data['ENEMY_ARMOR_COUNT']
    ENEMY_COVER_RANGE = enemy_data['ENEMY_COVER_RANGE']

    TARGET_UNITS_PER_SIDE = other_data['TARGET_UNITS_PER_SIDE']

    MIN_BATTLES = other_data['MIN_BATTLES']
    MAX_BATTLES = other_data['MAX_BATTLES']

    DISTANCE_RANGE = other_data['DISTANCE_RANGE']
    ELEVATION_RANGE = other_data['ELEVATION_RANGE']

    START_TIME = other_data['START_TIME']

    TACTICAL_BUTTLE_NUM = other_data.get('TACTICAL_BUTTLE_NUM', 1)
    TACTICAL_BATTLE_TIME = other_data.get('TACTICAL_BATTLE_TIME', START_TIME)
    TACTICAL_COMMENT = other_data.get('TACTICAL_COMMENT', '')

    PLAYER_OUTPUT_FILE = files.get('PLAYER_OUTPUT_FILE', PLAYER_FILE)
    ENEMY_OUTPUT_FILE = files.get('ENEMY_OUTPUT_FILE', ENEMY_FILE)
    LOG_OUTPUT_FILE = files.get('LOG_OUTPUT_FILE', 'tactical_battle_log.xlsx')

    # ============================================================

    LOG_COLUMNS = [
        'tactical_buttle_num',
        'current_time', 'initiator',
        'log_blue_id', 'log_blue_type', 'log_blue_inf_force', 'log_blue_arm_force',
        'log_blue_cas_inf', 'log_blue_cas_armor',
        'log_red_id', 'log_red_type', 'log_red_inf_force', 'log_red_arm_force',
        'log_red_cas_inf', 'log_red_cas_armor',
        'log_attack_type', 'log_result'
    ]

    TACTICAL_LOG_COLUMNS = [
        'tactical_buttle_num',
        'time',
        'comment',
        'total_battles',
        'blue_victories',
        'blue_defeats',
        'draws_or_other',
        'blue_cas_inf_total',
        'blue_cas_armor_total',
        'red_cas_inf_total',
        'red_cas_armor_total',
    ]

    WIN_RESULTS = {"победа", "разгром"}
    LOSS_RESULTS = {"поражение", "засада"}

    def _read_existing_sheet(path: str | Path, sheet_name: str, columns: list[str]) -> pd.DataFrame:
        path = Path(path)
        if not path.exists():
            return pd.DataFrame(columns=columns)

        try:
            xls = pd.ExcelFile(path)
            if sheet_name not in xls.sheet_names:
                return pd.DataFrame(columns=columns)
            df = pd.read_excel(path, sheet_name=sheet_name)
        except Exception:
            return pd.DataFrame(columns=columns)

        for col in columns:
            if col not in df.columns:
                df[col] = pd.NA

        return df[columns].copy()

    def _append_to_existing_sheet(path: str | Path, sheet_name: str, new_df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        existing_df = _read_existing_sheet(path, sheet_name, columns)

        if new_df is None or new_df.empty:
            return existing_df

        prepared_new_df = new_df.copy()
        for col in columns:
            if col not in prepared_new_df.columns:
                prepared_new_df[col] = pd.NA
        prepared_new_df = prepared_new_df[columns]

        if existing_df.empty:
            return prepared_new_df.reset_index(drop=True)

        return pd.concat([existing_df, prepared_new_df], ignore_index=True)

    class TacticalArmorTestRunner:
        def __init__(self, player_file: str, enemy_file: str, injury_table=None):
            self.player_manager = ForceManager.from_excel(player_file)
            self.enemy_manager = ForceManager.from_excel(enemy_file)
            self.engine = GroundEngine(injury_table=injury_table)
            self.logs = pd.DataFrame(columns=LOG_COLUMNS)
            self.unit_next_time: dict[str, datetime] = {}

        @staticmethod
        def _alive_units(units):
            alive = []
            for u in units:
                has_inf = getattr(u, "alive_df", pd.DataFrame()).shape[0] > 0
                has_arm = (
                    getattr(getattr(u, "armor_part", None), "alive_df", pd.DataFrame()).shape[0] > 0
                    if getattr(u, "armor_part", None) not in (None, [])
                    else False
                )
                if has_inf or has_arm:
                    alive.append(u)
            return alive

        @staticmethod
        def _sample_cover_values() -> tuple[int, int]:
            defender_min = ENEMY_COVER_RANGE[0]
            defender_max = ENEMY_COVER_RANGE[1]
            attacker_min = PLAYER_COVER_RANGE[0]
            attacker_max = PLAYER_COVER_RANGE[1]

            attacker_cover = random.randint(attacker_min, attacker_max)
            defender_cover = random.randint(defender_min, defender_max)
            return attacker_cover, defender_cover

        @classmethod
        def _choose_random_context(cls) -> BattleContext:
            attacker_cover, defender_cover = cls._sample_cover_values()
            return BattleContext(
                attacker_cover=attacker_cover,
                defender_cover=defender_cover,
                attacker_elevation=random.randint(*ELEVATION_RANGE),
                defender_elevation=random.randint(*ELEVATION_RANGE),
                distance=random.randint(*DISTANCE_RANGE),
                defender_returns_fire=True,
                attacker_berserk=False,
                defender_berserk=False,
            )

        def build_forces(self):
            player_units, player_plan = self.player_manager.generate_ground_units_with_armor(
                level=PLAYER_LEVEL,
                formation_uids=PLAYER_FORMATIONS,
                target_units=TARGET_UNITS_PER_SIDE,
                armor_count=PLAYER_ARMOR_COUNT,
                side="blue",
                unit_prefix="BLU",
                rng=random,
            )

            enemy_units, enemy_plan = self.enemy_manager.generate_ground_units_with_armor(
                level=ENEMY_LEVEL,
                formation_uids=ENEMY_FORMATIONS,
                target_units=TARGET_UNITS_PER_SIDE,
                armor_count=ENEMY_ARMOR_COUNT,
                side="red",
                unit_prefix="RED",
                rng=random,
            )

            player_plan = player_plan.copy()
            enemy_plan = enemy_plan.copy()
            player_plan.insert(0, 'tactical_buttle_num', TACTICAL_BUTTLE_NUM)
            enemy_plan.insert(0, 'tactical_buttle_num', TACTICAL_BUTTLE_NUM)

            return player_units, enemy_units, player_plan, enemy_plan

        def _initialize_unit_times(self, player_units, enemy_units):
            for unit in list(player_units) + list(enemy_units):
                self.unit_next_time[unit.unit_id] = START_TIME

        def _choose_battle_time(self, attacker, defender) -> datetime:
            return max(self.unit_next_time[attacker.unit_id], self.unit_next_time[defender.unit_id])

        def _advance_unit_times(self, attacker, defender, battle_time: datetime):
            next_time = battle_time + timedelta(minutes=TIME_STEP_MINUTES)
            self.unit_next_time[attacker.unit_id] = next_time
            self.unit_next_time[defender.unit_id] = next_time

        @staticmethod
        def _build_overall_stats(summary_df: pd.DataFrame) -> pd.DataFrame:
            if len(summary_df) == 0:
                return pd.DataFrame([{
                    "total_battles": 0,
                    "blue_victories": 0,
                    "blue_defeats": 0,
                    "draws_or_other": 0,
                    "blue_cas_inf_total": 0,
                    "blue_cas_armor_total": 0,
                    "red_cas_inf_total": 0,
                    "red_cas_armor_total": 0,
                }])

            result_series = summary_df["result"].astype(str)
            blue_victories = int(result_series.isin(WIN_RESULTS).sum())
            blue_defeats = int(result_series.isin(LOSS_RESULTS).sum())

            return pd.DataFrame([{
                "total_battles": int(len(summary_df)),
                "blue_victories": blue_victories,
                "blue_defeats": blue_defeats,
                "draws_or_other": int(len(summary_df) - blue_victories - blue_defeats),
                "blue_cas_inf_total": int(summary_df["blue_cas_inf"].sum()),
                "blue_cas_armor_total": int(summary_df["blue_cas_armor"].sum()),
                "red_cas_inf_total": int(summary_df["red_cas_inf"].sum()),
                "red_cas_armor_total": int(summary_df["red_cas_armor"].sum()),
            }])

        def run(self):
            player_units, enemy_units, player_plan, enemy_plan = self.build_forces()
            self._initialize_unit_times(player_units, enemy_units)

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
                battle_time = self._choose_battle_time(attacker, defender)

                result = self.engine.resolve_engagement(
                    attacker=attacker,
                    defender=defender,
                    context=context,
                    logs=self.logs,
                    current_time=battle_time,
                )

                self.logs = result.logs
                self._advance_unit_times(attacker, defender, battle_time)
                last_log = result.logs.iloc[-1]

                tactical_summary.append({
                    "battle_no": battle_no,
                    "time": last_log["current_time"],
                    "blue_unit": last_log["log_blue_id"],
                    "red_unit": last_log["log_red_id"],
                    "attack_type": last_log["log_attack_type"],
                    "result": last_log["log_result"],
                    "blue_force_before": last_log["log_blue_inf_force"],
                    "blue_arm_before": last_log["log_blue_arm_force"],
                    "blue_cas_inf": last_log["log_blue_cas_inf"],
                    "blue_cas_armor": last_log["log_blue_cas_armor"],
                    "red_force_before": last_log["log_red_inf_force"],
                    "red_arm_before": last_log["log_red_arm_force"],
                    "red_cas_inf": last_log["log_red_cas_inf"],
                    "red_cas_armor": last_log["log_red_cas_armor"],
                    "distance": context.distance,
                    "blue_cover": context.attacker_cover,
                    "red_cover": context.defender_cover,
                })

            self.player_manager.apply_many_battle_results(player_units)
            self.enemy_manager.apply_many_battle_results(enemy_units)

            self.player_manager.save_to_excel(PLAYER_OUTPUT_FILE)
            self.enemy_manager.save_to_excel(ENEMY_OUTPUT_FILE)

            summary_df = pd.DataFrame(tactical_summary)
            overall_stats_df = self._build_overall_stats(summary_df)

            tactical_log_df = pd.DataFrame([{
                'tactical_buttle_num': TACTICAL_BUTTLE_NUM,
                'time': TACTICAL_BATTLE_TIME,
                'comment': TACTICAL_COMMENT,
                'total_battles': int(overall_stats_df.iloc[0]['total_battles']),
                'blue_victories': int(overall_stats_df.iloc[0]['blue_victories']),
                'blue_defeats': int(overall_stats_df.iloc[0]['blue_defeats']),
                'draws_or_other': int(overall_stats_df.iloc[0]['draws_or_other']),
                'blue_cas_inf_total': int(overall_stats_df.iloc[0]['blue_cas_inf_total']),
                'blue_cas_armor_total': int(overall_stats_df.iloc[0]['blue_cas_armor_total']),
                'red_cas_inf_total': int(overall_stats_df.iloc[0]['red_cas_inf_total']),
                'red_cas_armor_total': int(overall_stats_df.iloc[0]['red_cas_armor_total']),
            }], columns=TACTICAL_LOG_COLUMNS)

            ground_log_df = self.logs.copy()
            if 'tactical_buttle_num' not in ground_log_df.columns:
                ground_log_df.insert(0, 'tactical_buttle_num', TACTICAL_BUTTLE_NUM)

            player_plan_columns = ['tactical_buttle_num'] + [c for c in player_plan.columns if c != 'tactical_buttle_num']
            enemy_plan_columns = ['tactical_buttle_num'] + [c for c in enemy_plan.columns if c != 'tactical_buttle_num']

            tactical_log_final = _append_to_existing_sheet(
                LOG_OUTPUT_FILE,
                'tactical_log',
                tactical_log_df,
                TACTICAL_LOG_COLUMNS,
            )
            ground_log_final = _append_to_existing_sheet(
                LOG_OUTPUT_FILE,
                'ground_log',
                ground_log_df,
                LOG_COLUMNS,
            )
            player_plan_final = _append_to_existing_sheet(
                LOG_OUTPUT_FILE,
                'player_plan',
                player_plan,
                player_plan_columns,
            )
            enemy_plan_final = _append_to_existing_sheet(
                LOG_OUTPUT_FILE,
                'enemy_plan',
                enemy_plan,
                enemy_plan_columns,
            )

            with pd.ExcelWriter(LOG_OUTPUT_FILE, engine='openpyxl') as writer:
                tactical_log_final.to_excel(writer, sheet_name='tactical_log', index=False)
                ground_log_final.to_excel(writer, sheet_name='ground_log', index=False)
                player_plan_final.to_excel(writer, sheet_name='player_plan', index=False)
                enemy_plan_final.to_excel(writer, sheet_name='enemy_plan', index=False)

            return {
                'battle_count': len(tactical_summary),
                'logs': self.logs,
                'summary': summary_df,
                'overall_stats': overall_stats_df,
                'tactical_log': tactical_log_df,
                'player_plan': player_plan,
                'enemy_plan': enemy_plan,
                'player_units': player_units,
                'enemy_units': enemy_units,
            }

    def print_short_summary(result_bundle: dict):
        overall_stats = result_bundle['overall_stats']
        stats = overall_stats.iloc[0]

        print('=' * 60)
        print(f"Тактическая битва #{TACTICAL_BUTTLE_NUM}")
        print(f"Проведено наземных боёв: {int(stats['total_battles'])}")
        print('-' * 60)
        print(
            'Общая статистика | '
            f"победы blue: {int(stats['blue_victories'])} | "
            f"поражения blue: {int(stats['blue_defeats'])} | "
            f"прочее: {int(stats['draws_or_other'])} | "
            f"потери blue: {int(stats['blue_cas_inf_total'])} inf / {int(stats['blue_cas_armor_total'])} arm | "
            f"потери red: {int(stats['red_cas_inf_total'])} inf / {int(stats['red_cas_armor_total'])} arm"
        )

    runner = TacticalArmorTestRunner(PLAYER_FILE, ENEMY_FILE, injury_table=injury_table)
    result_bundle = runner.run()
    print_short_summary(result_bundle)
    print("\nФайлы сохранены:")
    print(f"- {PLAYER_OUTPUT_FILE}")
    print(f"- {ENEMY_OUTPUT_FILE}")
    print(f"- {LOG_OUTPUT_FILE}")
