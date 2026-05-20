# WM_calculations — Симулятор боевых действий

## Общее описание

Пошаговый варгейм-симулятор на Python. Три уровня боёв:
- **Ground (тактический мини)**: стычки 10–100 солдат, территория ~2 км²
- **Tactical**: бригада vs бригада, 1–4 тыс. чел., территория 10–20 км²
- **Operational (в разработке)**: группировки 20–50 тыс., территория 40–100 км², единица — бригада

Интерфейс — Jupyter-ноутбуки. Python-логика — в `.py` файлах.

---

## Структура файлов

| Файл | Назначение |
|---|---|
| `wm_unit.py` | Класс `Unit` — хранит `alive_df` / `cas_df`, методы расчёта потерь |
| `ground_engine.py` | `GroundEngine` — разрешает бой между двумя `Unit`. `BattleContext` — параметры боя |
| `tactical_engine.py` | `tact_battle()` — серия боёв между двумя подразделениями, запись в Excel |
| `force_manager.py` | `ForceManager` — читает Excel-файлы бригад, генерирует временные юниты, записывает статусы обратно |
| `create_units.py` | Утилиты для создания шаблонов бригад |
| `wm_tac_ops.py` | Вспомогательные тактические операции |
| `artillery_engine.py` | `artillery_strike()` — симуляция артиллерийского/бомбового удара по юниту |

---

## Ключевые структуры данных

### Unit
```python
unit = Unit(
    unit_id='pc1',
    overall_type='inf',   # inf / arm / mech
    personal_type='inf',  # inf / arm
    alive_df=df,          # DataFrame живых бойцов
    cas_df=df_empty,      # DataFrame выбывших
    side='blue',          # blue / red
)
```

### alive_df / cas_df (infantry)
Колонки: `soldier_uid`, `squad_uid`, `platoon_uid`, `company_uid`, `battalion_uid`,
`status`, `power`, `side`, `inf_kills`, `apc_kills`

**Значения `status`:**
- `alive` — боец в строю (только в `alive_df`)
- `killed` — погиб
- `heavy` — тяжёлое ранение
- `light` — лёгкое ранение
- `died_from_injury` — умер от ранения позже

### BattleContext
```python
BattleContext(
    attacker_cover=0, defender_cover=0,      # 0-4
    attacker_elevation=0, defender_elevation=0,
    distance=0,                               # 0-4
    defender_returns_fire=True,               # False = атака без ответа
    attacker_berserk=False, defender_berserk=False,
    armor_is_moving=False, armor_is_far=False,
)
```

---

## Система ранений (реализовано)

### Боевые ранения (ground-уровень)
Источник данных: лист `injuries` в Google Sheets.
Колонки: `distance`, `caliber` (`smal_arms` / `arm 2`), `instant_death_perc`, `bad_injury_perc`, `light_injury_perc` (float, 0.0–1.0).

Передаётся в движок при создании:
```python
engine = GroundEngine(injury_table=injury_table)
```

### Артиллерийские ранения
Источник данных: лист `artillery` в Google Sheets.
Колонки: `weapon`, `cover`, `killed`, `heavy`, `light`, `accuracy`.

Типы weapon: `mortar`, `cannon`, `mlrs`, `rocket`, `bomb_250`, `bomb_1000`

```python
from artillery_engine import artillery_strike
result = artillery_strike(target_unit, cover_level=1, shells_cnt=5, weapon='mortar', artillery_table=artillery_table)
```

### Evac-проверка тяжелораненых
В `next_turn` и в `tact_battle` (через `PLAYER_EVAC_TIME` / `ENEMY_EVAC_TIME`):
- d6 за каждого `heavy`-бойца
- При `1` → `died_from_injury`

---

## Ноутбуки

### Ноутбук "ground module"
Используется для ручных стычек (отделение–рота). Содержит:
- Загрузку Google Sheets (injuries, artillery, who_is_contact, enemy_action)
- `engine = GroundEngine(injury_table=injury_table)`
- `create_ground_unit()` — конструктор юнита из DataFrame
- `run_ground_battle()` — один бой
- `next_turn(current_time, side_a, side_b)` — +15 мин + evac-проверка

### Ноутбук "tactical module"  
Используется для батальонных/бригадных операций. Содержит вызов `tact_battle()`.

---

## ForceManager — работа с Excel-файлами бригад

```python
player_manager = ForceManager.from_excel('player_brigade.xlsx')
enemy_manager  = ForceManager.from_excel('enemy_brigade.xlsx')

# Генерация временных юнитов для боя
units, plan = player_manager.generate_ground_units_with_armor(
    level='company', formation_uids=['B5-C1'],
    target_units=6, armor_count=3, side='blue'
)

# Запись результатов обратно в Excel
player_manager.apply_many_battle_results(units)
player_manager.save_to_excel('player_brigade.xlsx')
```

Excel-файл бригады содержит листы `inf` и `armor`.

---

## tact_battle — параметры

```python
from tactical_engine import tact_battle

files = {
    'PLAYER_FILE': 'player_brigade.xlsx',
    'ENEMY_FILE': 'enemy_brigade.xlsx',
    'PLAYER_OUTPUT_FILE': 'player_brigade.xlsx',
    'ENEMY_OUTPUT_FILE': 'enemy_brigade.xlsx',
    'LOG_OUTPUT_FILE': 'tactical_battle_log.xlsx',
}

player_data = {
    'PLAYER_LEVEL': 'battalion',
    'PLAYER_FORMATIONS': ['B5'],
    'PLAYER_ARMOR_COUNT': 6,
    'PLAYER_COVER_RANGE': [0, 2],
    'PLAYER_ELEVATION_RANGE': [0, 1],
    'PLAYER_EVAC_TIME': 3,       # кол-во d6-проверок тяжелораненых после боёв
}

enemy_data = {
    'ENEMY_LEVEL': 'battalion',
    'ENEMY_FORMATIONS': ['B2'],
    'ENEMY_ARMOR_COUNT': 0,
    'ENEMY_COVER_RANGE': [1, 3],
    'ENEMY_ELEVATION_RANGE': [0, 1],
    'ENEMY_EVAC_TIME': 2,
}

other_data = {
    'TARGET_UNITS_PER_SIDE': 6,
    'MIN_BATTLES': 8,
    'MAX_BATTLES': 12,
    'DISTANCE_RANGE': [0, 3],
    'START_TIME': datetime(2026, 5, 14, 6, 0),
    'TACTICAL_BUTTLE_NUM': 1,
    'TACTICAL_BATTLE_TIME': datetime(2026, 5, 14, 6, 0),
    'TACTICAL_COMMENT': 'штурм высоты',
}

result = tact_battle(files, player_data, enemy_data, other_data, injury_table=injury_table)
```

---

## Google Sheets (SPREADSHEET_ID: 19zobRN2kc4jLC6yPVUGk-JfE2PBQ4PWlS8FQ_sw3qs8)

| Лист | Назначение |
|---|---|
| `injuries` | Вероятности ранений по дистанции и типу оружия (ground-бой) |
| `artillery` | Радиусы поражения и точность артиллерии |
| `contact_chance` | Вероятность контакта с противником |
| `who_is_contact` | Таблица типов встречаемых противников |
| `enemy_action` | Действия противника (засада / обстрел / подкрепления / контратака) |

---

## Следующий этап: Оперативный уровень

**Цель**: симуляция группировок 20–50 тыс. человек на картах 40–100 км².
**Единица управления**: бригада (а не отдельный солдат).
**Планируемые механики**:
- Карта с гексами или квадратами (зоны 5–10 км)
- Бригады как объекты с численностью, типом, состоянием (боеспособна / истощена / уничтожена)
- Движение бригад по карте
- Боестолкновения бригад → вызов `tact_battle()` для детализации
- Снабжение и восстановление
- Артиллерийская поддержка на оперативном уровне

**Предполагаемая архитектура**:
- Новый файл `operational_engine.py`
- Карта как DataFrame или dict гексов/квадратов
- Объект `Brigade` — обёртка над `ForceManager` с позицией на карте
- Новый ноутбук `operational_module.ipynb`
