from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from force_manager import ForceManager
from ground_engine import GroundEngine, BattleContext, GROUND_LOG_COLUMNS
from artillery_engine import artillery_strike


def _read_existing_sheet(path: str | Path, sheet_name: str, columns: list) -> pd.DataFrame:
    """Читает лист из Excel, возвращает DataFrame с заданными колонками."""
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


def _append_to_existing_sheet(
    path: str | Path,
    sheet_name: str,
    new_df: pd.DataFrame,
    columns: list,
) -> pd.DataFrame:
    """Читает существующий лист и аппендит new_df снизу."""
    existing_df = _read_existing_sheet(path, sheet_name, columns)
    if new_df is None or new_df.empty:
        return existing_df
    prepared = new_df.copy()
    for col in columns:
        if col not in prepared.columns:
            prepared[col] = pd.NA
    prepared = prepared[columns]
    if existing_df.empty:
        return prepared.reset_index(drop=True)
    return pd.concat([existing_df, prepared], ignore_index=True)


def tact_battle(
    files,
    player_data,
    enemy_data,
    other_data,
    injury_table=None,
    artillery_table=None,
    arty_usage=None,
    player_arty_assets=None,
    enemy_arty_assets=None,
):

    print('start')

    # ── Валидация арт-ассетов ────────────────────────────────────────
    if (player_arty_assets or enemy_arty_assets) and artillery_table is None:
        raise ValueError(
            "tact_battle: передали arty_assets, но artillery_table=None. "
            "Загрузи artillery_table из Google Sheets и передай в функцию."
        )
    if (player_arty_assets or enemy_arty_assets) and arty_usage is None:
        raise ValueError(
            "tact_battle: передали arty_assets, но arty_usage=None. "
            "Загрузи лист 'arty_usage' из Google Sheets и передай в функцию."
        )

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
    PLAYER_ELEVATION_RANGE = player_data['PLAYER_ELEVATION_RANGE']
    PLAYER_EVAC_TIME = player_data.get('PLAYER_EVAC_TIME', 0)

    ENEMY_LEVEL = enemy_data['ENEMY_LEVEL']
    ENEMY_FORMATIONS = enemy_data['ENEMY_FORMATIONS']
    ENEMY_ARMOR_COUNT = enemy_data['ENEMY_ARMOR_COUNT']
    ENEMY_COVER_RANGE = enemy_data['ENEMY_COVER_RANGE']
    ENEMY_ELEVATION_RANGE = enemy_data['ENEMY_ELEVATION_RANGE']
    ENEMY_EVAC_TIME = enemy_data.get('ENEMY_EVAC_TIME', 0)

    TARGET_UNITS_PER_SIDE = other_data['TARGET_UNITS_PER_SIDE']

    MIN_BATTLES = other_data['MIN_BATTLES']
    MAX_BATTLES = other_data['MAX_BATTLES']

    DISTANCE_RANGE = other_data['DISTANCE_RANGE']

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
        'blue_cas_inf_ground',
        'blue_cas_inf_arty',
        'blue_cas_armor_total',
        'red_cas_inf_total',
        'red_cas_inf_ground',
        'red_cas_inf_arty',
        'red_cas_armor_total',
    ]

    WIN_RESULTS = {"победа", "разгром"}
    LOSS_RESULTS = {"поражение", "засада"}

    class TacticalArmorTestRunner:
        def __init__(self, player_file: str, enemy_file: str, injury_table=None):
            self.player_manager = ForceManager.from_excel(player_file)
            self.enemy_manager = ForceManager.from_excel(enemy_file)
            self.engine = GroundEngine(injury_table=injury_table)
            self.logs = pd.DataFrame(columns=LOG_COLUMNS)
            self.unit_next_time: dict[str, datetime] = {}

        @staticmethod
        def _run_evac_checks(units, evac_time):
            """Roll d6 per heavy casualty, evac_time times. Roll of 1 → died_from_injury."""
            died_total = 0
            for _ in range(evac_time):
                for unit in units:
                    if unit.cas_df is None or unit.cas_df.empty:
                        continue
                    heavy_idx = unit.cas_df.index[unit.cas_df['status'] == 'heavy']
                    for idx in heavy_idx:
                        if random.randint(1, 6) == 1:
                            unit.cas_df.loc[idx, 'status'] = 'died_from_injury'
                            died_total += 1
            return died_total

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
                attacker_elevation=random.randint(*PLAYER_ELEVATION_RANGE),
                defender_elevation=random.randint(*ENEMY_ELEVATION_RANGE),
                distance=random.randint(*DISTANCE_RANGE),
                defender_returns_fire=True,
                attacker_berserk=False,
                defender_berserk=False,
            )

        @staticmethod
        def _parse_chance(raw) -> float:
            """Parse '80%' → 0.80, or float/int → return as float."""
            if isinstance(raw, str):
                return float(raw.strip().rstrip('%')) / 100
            return float(raw)

        def _fire_artillery_phase(
            self,
            firing_assets,
            target_units,
            cover_range,
            phase_time,
            fire_type: str = 'close',
        ):
            """Fire salvos in firing_assets at random alive targets.

            Hit chance per salvo is looked up from arty_usage table by
            (Type=fire_type, missions=total_salvos). Only successful rolls
            actually call artillery_strike.

            Args:
                firing_assets: list of asset dicts:
                               [{'weapon': 'mortar', 'salvos_left': 3, 'shells_per_salvo': 5}]
                               salvos_left is NOT mutated — caller manages ammo state.
                target_units:  list of Unit objects to pick targets from.
                cover_range:   (min, max) — random cover level for each target.
                phase_time:    datetime timestamp for the log rows.
                fire_type:     'close' or 'distant' — row selector in arty_usage table.
            """
            if not firing_assets:
                return

            # ── Look up hit chance from arty_usage ──────────────────────
            total_salvos = sum(a.get('salvos_left', 0) for a in firing_assets)
            if total_salvos == 0:
                return

            if arty_usage is not None:
                missions = min(total_salvos, 8)
                row = arty_usage[
                    (arty_usage['Type'] == fire_type) &
                    (arty_usage['missions'] == missions)
                ]
                if row.empty:
                    print(f"  [Арт {fire_type}] Нет строки в arty_usage для missions={missions}. Стреляем всем.")
                    chance = 1.0
                else:
                    chance = self._parse_chance(row.iloc[0]['chance'])
            else:
                chance = 1.0   # обратная совместимость: всё попадает

            alive = self._alive_units(target_units)
            if not alive:
                return

            hits = 0
            for asset in firing_assets:
                for _ in range(asset.get('salvos_left', 0)):
                    if random.random() < chance:
                        hits += 1
                        target = random.choice(alive)
                        cover  = random.randint(*cover_range)
                        arty_result = artillery_strike(
                            target_unit=target,
                            cover_level=cover,
                            shells_cnt=asset['shells_per_salvo'],
                            weapon=asset['weapon'],
                            artillery_table=artillery_table,
                            logs=self.logs,
                            current_time=phase_time,
                        )
                        if 'logs' in arty_result:
                            self.logs = arty_result['logs']
                        alive = self._alive_units(target_units)
                        if not alive:
                            break

            print(
                f"  [Арт {fire_type}] {hits}/{total_salvos} залпов попали в цель"
                f" (chance={chance:.0%})"
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
        def _build_overall_stats(summary_df: pd.DataFrame, logs_df: pd.DataFrame) -> pd.DataFrame:
            # ── Потери от артиллерии — из ground_log ────────────────────
            arty_rows = logs_df[logs_df["log_attack_type"] == "art_air_fire"]
            blue_arty = int(
                pd.to_numeric(arty_rows["log_blue_cas_inf"], errors="coerce").fillna(0).sum()
            )
            red_arty = int(
                pd.to_numeric(arty_rows["log_red_cas_inf"], errors="coerce").fillna(0).sum()
            )

            if len(summary_df) == 0:
                return pd.DataFrame([{
                    "total_battles": 0,
                    "blue_victories": 0,
                    "blue_defeats": 0,
                    "draws_or_other": 0,
                    "blue_cas_inf_total": blue_arty,
                    "blue_cas_inf_ground": 0,
                    "blue_cas_inf_arty": blue_arty,
                    "blue_cas_armor_total": 0,
                    "red_cas_inf_total": red_arty,
                    "red_cas_inf_ground": 0,
                    "red_cas_inf_arty": red_arty,
                    "red_cas_armor_total": 0,
                }])

            result_series = summary_df["result"].astype(str)
            blue_victories = int(result_series.isin(WIN_RESULTS).sum())
            blue_defeats   = int(result_series.isin(LOSS_RESULTS).sum())
            blue_ground    = int(summary_df["blue_cas_inf"].sum())
            red_ground     = int(summary_df["red_cas_inf"].sum())

            return pd.DataFrame([{
                "total_battles":      int(len(summary_df)),
                "blue_victories":     blue_victories,
                "blue_defeats":       blue_defeats,
                "draws_or_other":     int(len(summary_df) - blue_victories - blue_defeats),
                "blue_cas_inf_total": blue_ground + blue_arty,
                "blue_cas_inf_ground": blue_ground,
                "blue_cas_inf_arty":   blue_arty,
                "blue_cas_armor_total": int(summary_df["blue_cas_armor"].sum()),
                "red_cas_inf_total":   red_ground + red_arty,
                "red_cas_inf_ground":  red_ground,
                "red_cas_inf_arty":    red_arty,
                "red_cas_armor_total": int(summary_df["red_cas_armor"].sum()),
            }])

        def run(self):
            player_units, enemy_units, player_plan, enemy_plan = self.build_forces()
            self._initialize_unit_times(player_units, enemy_units)

            # ── Артиллерийская фаза (до наземных боёв) ──────────────────
            arty_time = START_TIME
            self._fire_artillery_phase(
                player_arty_assets, enemy_units, ENEMY_COVER_RANGE, arty_time
            )
            self._fire_artillery_phase(
                enemy_arty_assets, player_units, PLAYER_COVER_RANGE, arty_time
            )
            # ────────────────────────────────────────────────────────────

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

            blue_evac_died = self._run_evac_checks(player_units, PLAYER_EVAC_TIME)
            red_evac_died  = self._run_evac_checks(enemy_units,  ENEMY_EVAC_TIME)
            print(f"  Эвакуация: blue умерли от ранений — {blue_evac_died}, red — {red_evac_died}")

            self.player_manager.apply_many_battle_results(player_units)
            self.enemy_manager.apply_many_battle_results(enemy_units)

            self.player_manager.save_to_excel(PLAYER_OUTPUT_FILE)
            self.enemy_manager.save_to_excel(ENEMY_OUTPUT_FILE)

            summary_df = pd.DataFrame(tactical_summary)
            overall_stats_df = self._build_overall_stats(summary_df, self.logs)

            s = overall_stats_df.iloc[0]
            tactical_log_df = pd.DataFrame([{
                'tactical_buttle_num':  TACTICAL_BUTTLE_NUM,
                'time':                 TACTICAL_BATTLE_TIME,
                'comment':              TACTICAL_COMMENT,
                'total_battles':        int(s['total_battles']),
                'blue_victories':       int(s['blue_victories']),
                'blue_defeats':         int(s['blue_defeats']),
                'draws_or_other':       int(s['draws_or_other']),
                'blue_cas_inf_total':   int(s['blue_cas_inf_total']),
                'blue_cas_inf_ground':  int(s['blue_cas_inf_ground']),
                'blue_cas_inf_arty':    int(s['blue_cas_inf_arty']),
                'blue_cas_armor_total': int(s['blue_cas_armor_total']),
                'red_cas_inf_total':    int(s['red_cas_inf_total']),
                'red_cas_inf_ground':   int(s['red_cas_inf_ground']),
                'red_cas_inf_arty':     int(s['red_cas_inf_arty']),
                'red_cas_armor_total':  int(s['red_cas_armor_total']),
            }], columns=TACTICAL_LOG_COLUMNS)

            ground_log_df = self.logs.copy()
            ground_log_df['tactical_buttle_num'] = TACTICAL_BUTTLE_NUM

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
        s = overall_stats.iloc[0]

        blue_total  = int(s['blue_cas_inf_total'])
        blue_ground = int(s['blue_cas_inf_ground'])
        blue_arty   = int(s['blue_cas_inf_arty'])
        red_total   = int(s['red_cas_inf_total'])
        red_ground  = int(s['red_cas_inf_ground'])
        red_arty    = int(s['red_cas_inf_arty'])

        print('=' * 60)
        print(f"Тактическая битва #{TACTICAL_BUTTLE_NUM}")
        print(f"Проведено наземных боёв: {int(s['total_battles'])}")
        print('-' * 60)
        print(
            'Общая статистика | '
            f"победы blue: {int(s['blue_victories'])} | "
            f"поражения blue: {int(s['blue_defeats'])} | "
            f"прочее: {int(s['draws_or_other'])}"
        )
        print(
            f"  потери blue inf: {blue_total} всего / {blue_ground} в боях / {blue_arty} от арты"
            f"  | armor: {int(s['blue_cas_armor_total'])}"
        )
        print(
            f"  потери red  inf: {red_total} всего / {red_ground} в боях / {red_arty} от арты"
            f"  | armor: {int(s['red_cas_armor_total'])}"
        )

    runner = TacticalArmorTestRunner(PLAYER_FILE, ENEMY_FILE, injury_table=injury_table)
    result_bundle = runner.run()
    print_short_summary(result_bundle)
    print("\nФайлы сохранены:")
    print(f"- {PLAYER_OUTPUT_FILE}")
    print(f"- {ENEMY_OUTPUT_FILE}")
    print(f"- {LOG_OUTPUT_FILE}")


# ===========================================================================
# Distant Fire Support — артиллерия по врагу без наземного боя
# ===========================================================================

def distant_fire_support(
    enemy_file: str,
    enemy_data: dict,
    fire_assets: list,
    artillery_table: pd.DataFrame,
    arty_usage: pd.DataFrame,
    current_time=None,
    target_units: int = 6,
    injury_table=None,
    enemy_output_file: str = None,
) -> dict:
    """Артиллерийский удар по вражеским позициям без наземного боя.

    Дробит вражеское подразделение на target_units частей, определяет шанс
    попадания из таблицы arty_usage (Type='distant'), стреляет успешными залпами,
    опционально сохраняет потери обратно в Excel.

    Args:
        enemy_file:        Путь к Excel-файлу бригады врага.
        enemy_data:        Словарь с ключами:
                               ENEMY_LEVEL       — 'battalion' / 'company' / ...
                               ENEMY_FORMATIONS  — список uid, например ['B3']
                               ENEMY_COVER_RANGE — (min, max) укрытия целей
                           Опционально: 'side' (default 'red'), 'unit_prefix' (default 'TGT')
        fire_assets:       Список ассетов:
                               [{'weapon': 'mortar', 'salvos_left': 5, 'shells_per_salvo': 5}]
                           salvos_left НЕ мутируется функцией.
        artillery_table:   DataFrame из листа 'artillery' (Google Sheets).
        arty_usage:        DataFrame из листа 'arty_usage' (Google Sheets).
        current_time:      Время удара (datetime) для логов.
        target_units:      На сколько частей дробить подразделение (default 6).
        injury_table:      Не используется — зарезервировано для совместимости.
        enemy_output_file: Если задан — применить потери и сохранить Excel обратно.

    Returns:
        dict:
            'hits'          — int: сколько залпов попало
            'total_salvos'  — int: сколько залпов всего
            'chance'        — float: шанс попадания каждого залпа
            'logs'          — pd.DataFrame: строки ground_log этого удара
            'sub_units'     — list[Unit]: временные юниты с учётом потерь
            'plan'          — pd.DataFrame: как дробились подразделения
    """
    # ── Валидация ──────────────────────────────────────────────────────────
    if not fire_assets:
        raise ValueError("distant_fire_support: fire_assets пуст — нечем стрелять.")

    # ── Загрузка и нарезка подразделения ──────────────────────────────────
    enemy_manager = ForceManager.from_excel(enemy_file)
    armor_count = enemy_data.get('ENEMY_ARMOR_CNT', 0)
    if armor_count > 0:
        sub_units, plan_df = enemy_manager.generate_ground_units_with_armor(
            level=enemy_data['ENEMY_LEVEL'],
            formation_uids=enemy_data['ENEMY_FORMATIONS'],
            target_units=target_units,
            armor_count=armor_count,
            side=enemy_data.get('side', 'red'),
            unit_prefix=enemy_data.get('unit_prefix', 'TGT'),
        )
    else:
        sub_units, plan_df = enemy_manager.generate_ground_units(
            level=enemy_data['ENEMY_LEVEL'],
            formation_uids=enemy_data['ENEMY_FORMATIONS'],
            target_units=target_units,
            side=enemy_data.get('side', 'red'),
            unit_prefix=enemy_data.get('unit_prefix', 'TGT'),
        )

    # ── Lookup шанса из arty_usage ─────────────────────────────────────────
    def _parse_chance(raw) -> float:
        if isinstance(raw, str):
            return float(raw.strip().rstrip('%')) / 100
        return float(raw)

    total_salvos = sum(a.get('salvos_left', 0) for a in fire_assets)
    missions = min(total_salvos, 8)
    row = arty_usage[
        (arty_usage['Type'] == 'distant') &
        (arty_usage['missions'] == missions)
    ]
    if row.empty:
        print(f"[distant_fire_support] Нет строки в arty_usage для missions={missions}. chance=1.0")
        chance = 1.0
    else:
        chance = _parse_chance(row.iloc[0]['chance'])

    # ── Стрельба ───────────────────────────────────────────────────────────
    cover_range = enemy_data.get('ENEMY_COVER_RANGE', (0, 2))
    logs = pd.DataFrame(columns=GROUND_LOG_COLUMNS)
    alive = [u for u in sub_units if len(u.alive_df) > 0]
    hits = 0

    for asset in fire_assets:
        for _ in range(asset.get('salvos_left', 0)):
            if not alive:
                break
            if random.random() < chance:
                hits += 1
                target = random.choice(alive)
                cover  = random.randint(*cover_range)
                arty_result = artillery_strike(
                    target_unit=target,
                    cover_level=cover,
                    shells_cnt=asset['shells_per_salvo'],
                    weapon=asset['weapon'],
                    artillery_table=artillery_table,
                    logs=logs,
                    current_time=current_time,
                )
                if 'logs' in arty_result:
                    logs = arty_result['logs']
                alive = [u for u in sub_units if len(u.alive_df) > 0]

    # ── Суммируем потери ───────────────────────────────────────────────────
    arty_rows = logs[logs['log_attack_type'] == 'art_air_fire']
    red_cas_inf = int(
        pd.to_numeric(arty_rows['log_red_cas_inf'], errors='coerce').fillna(0).sum()
    )
    red_cas_armor = int(
        pd.to_numeric(arty_rows['log_red_cas_armor'], errors='coerce').fillna(0).sum()
    )

    # ── Печать результата ──────────────────────────────────────────────────
    print('=' * 50)
    print(f"Distant Fire Support")
    print(f"  Залпов: {hits}/{total_salvos} попали (chance={chance:.0%})")
    print(f"  Потери врага: {red_cas_inf} чел. (inf), {red_cas_armor} единиц техники")
    print('=' * 50)

    # ── Опционально: сохраняем потери в Excel ────────────────────────────
    if enemy_output_file is not None:
        enemy_manager.apply_many_battle_results(sub_units)
        enemy_manager.save_to_excel(enemy_output_file)
        print(f"  Потери применены → {enemy_output_file}")

    return {
        'hits':         hits,
        'total_salvos': total_salvos,
        'chance':       chance,
        'logs':         logs,
        'sub_units':    sub_units,
        'plan':         plan_df,
        'cas_inf':      red_cas_inf,
        'cas_armor':    red_cas_armor,
    }


# ===========================================================================
# save_ground_log — сохранить ground-уровневые бои в tactical_battle_log.xlsx
# ===========================================================================

def save_ground_log(
    engine,
    tactical_buttle_num: int,
    comment: str,
    current_time,
    log_file: str = 'tactical_battle_log.xlsx',
) -> None:
    """Аппендит engine.logs в tactical_battle_log.xlsx и добавляет сводку в tactical_log.

    Совместим с форматом который пишет tact_battle — те же листы и колонки.

    Args:
        engine:              GroundEngine с заполненным engine.logs.
        tactical_buttle_num: Номер тактического боя (int).
        comment:             Описание боя (str).
        current_time:        Время боя (datetime).
        log_file:            Путь к файлу лога (default 'tactical_battle_log.xlsx').
    """
    WIN_RESULTS  = {'победа', 'разгром'}
    LOSS_RESULTS = {'поражение', 'засада'}

    def _num(series):
        return int(pd.to_numeric(series, errors='coerce').fillna(0).sum())

    # ── Готовим ground_log ────────────────────────────────────────────────
    ground_log = engine.logs.copy()
    ground_log.insert(0, 'tactical_buttle_num', tactical_buttle_num)

    GROUND_COLS = list(ground_log.columns)

    # ── Считаем статистику ────────────────────────────────────────────────
    ground_rows = ground_log[ground_log['log_attack_type'] != 'art_air_fire']
    arty_rows   = ground_log[ground_log['log_attack_type'] == 'art_air_fire']

    total_battles  = len(ground_rows)
    blue_victories = int(ground_rows['log_result'].isin(WIN_RESULTS).sum())
    blue_defeats   = int(ground_rows['log_result'].isin(LOSS_RESULTS).sum())

    TACTICAL_COLS = [
        'tactical_buttle_num', 'time', 'comment',
        'total_battles', 'blue_victories', 'blue_defeats', 'draws_or_other',
        'blue_cas_inf_total', 'blue_cas_inf_ground', 'blue_cas_inf_arty', 'blue_cas_armor_total',
        'red_cas_inf_total',  'red_cas_inf_ground',  'red_cas_inf_arty',  'red_cas_armor_total',
    ]

    tactical_row = pd.DataFrame([{
        'tactical_buttle_num': tactical_buttle_num,
        'time':                str(current_time),
        'comment':             comment,
        'total_battles':       total_battles,
        'blue_victories':      blue_victories,
        'blue_defeats':        blue_defeats,
        'draws_or_other':      total_battles - blue_victories - blue_defeats,
        'blue_cas_inf_total':  _num(ground_rows['log_blue_cas_inf']) + _num(arty_rows['log_blue_cas_inf']),
        'blue_cas_inf_ground': _num(ground_rows['log_blue_cas_inf']),
        'blue_cas_inf_arty':   _num(arty_rows['log_blue_cas_inf']),
        'blue_cas_armor_total': _num(ground_rows['log_blue_cas_armor']),
        'red_cas_inf_total':   _num(ground_rows['log_red_cas_inf']) + _num(arty_rows['log_red_cas_inf']),
        'red_cas_inf_ground':  _num(ground_rows['log_red_cas_inf']),
        'red_cas_inf_arty':    _num(arty_rows['log_red_cas_inf']),
        'red_cas_armor_total': _num(ground_rows['log_red_cas_armor']),
    }])

    # ── Аппендим в файл ───────────────────────────────────────────────────
    final_ground   = _append_to_existing_sheet(log_file, 'ground_log',   ground_log,   GROUND_COLS)
    final_tactical = _append_to_existing_sheet(log_file, 'tactical_log', tactical_row, TACTICAL_COLS)

    with pd.ExcelWriter(log_file, engine='openpyxl') as writer:
        final_tactical.to_excel(writer, sheet_name='tactical_log', index=False)
        final_ground.to_excel(writer,   sheet_name='ground_log',   index=False)

    print(f"Лог сохранён: {log_file}")
    print(f"  ground_log:   {len(final_ground)} строк")
    print(f"  tactical_log: {len(final_tactical)} строк")
