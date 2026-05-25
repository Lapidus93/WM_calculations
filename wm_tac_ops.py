import random
import wm_unit as wmu
import pandas as pd
from datetime import timedelta




def calculate_force(force):
    available_force = 0
    casualties = 0
    for i in force:
        available_force += len(i.alive_df)
        casualties += len(i.cas_df)
    return available_force,casualties

def next_turn(current_time):
    current_time += timedelta(minutes=15)
    print(current_time)
    return current_time


def evacuation_and_regroup(unit,cas_avacuated,current_time):
    cas_to_add = unit.cas_df
    cas_to_add['side'] = unit.side
    cas_to_add['unit'] = unit.unit_id
    cas_to_add['evac_time'] = current_time
    cas_avacuated = cas_avacuated.append(cas_to_add)
    if 0 < len(unit.alive_df) <= 12:
        unit.size = 'SQ'
    elif 13 < len(unit.alive_df) <= 40:
        unit.size = 'PT'
    elif len(unit.alive_df) > 40:
        unit.size = 'CM'
    if 'type' in unit.alive_df.columns:
        unit.size = 'ARMOR'
    unit.cas_df = pd.DataFrame()
    
    return unit, cas_avacuated


def abandon_cas(unit,cas_abandoned,current_time):
    cas_to_add = unit.cas_df
    cas_to_add['side'] = unit.side
    cas_to_add['unit'] = unit.unit_id
    cas_to_add['evac_time'] = current_time
    cas_abandoned = cas_abandoned.append(cas_to_add)
    unit.cas_df = pd.DataFrame()    

    return unit, cas_abandoned

def save_units(list_of_sides):
    for side in list_of_sides:
        for podr in side:
            podr.alive_df.to_csv(podr.unit_id+'.csv',index=False)

            
def load_units(list_of_sides):
    for side in list_of_sides:
        for podr in side:
            podr.alive_df = pd.read_csv(podr.unit_id+'.csv')


def create_inf(name,ls,side):
    alive_df = []
    for i in range(ls):
        alive_df.append([name+'_'+str(i),1,0,0])
    alive_df = pd.DataFrame(alive_df,columns=['sol_id','power','inf_kills','apc_kills'])

    unit = wmu.Unit(unit_id=name, overall_type="inf",personal_type="inf", alive_df=alive_df,  cas_df=pd.DataFrame(),side=side)
    return unit

def create_arm(name,ls,side):
    alive_df = []
    for i in range(ls):
        alive_df.append([name+'_'+str(i),'apc',9,8,0,0])
    alive_df = pd.DataFrame(alive_df,columns=['armor_id','type','transport','power','inf_kills','apc_kills'])

    unit = wmu.Unit(unit_id=name, overall_type="arm",personal_type="arm", alive_df=alive_df,  cas_df=pd.DataFrame(),side=side)
    return unit

def create_mech(inf_name,ls,arm_name,armor_cnt,side):
    inf = create_inf(inf_name,ls,side)
    arm = create_arm(arm_name,armor_cnt,side)
    inf.armor_part = arm
    inf.update_current_type()
    return inf, arm


# ---------------------------------------------------------------------------
# AI Artillery Decision Engine
# ---------------------------------------------------------------------------

def ai_arty_decide(
    assets: list,
    deep_level: int,
    active_contacts: int,
    current_turn: int,
    ai_arty_table: pd.DataFrame,
    total_turns: int = 8,
) -> list:
    """Decide which enemy artillery assets fire this turn.

    Each asset that fires expends exactly ONE salvo this turn.
    Multiple different assets can fire simultaneously.

    Args:
        assets:          List of dicts, e.g.:
                           [{'weapon': 'rocket', 'salvos_left': 1, 'shells_per_salvo': 1},
                            {'weapon': 'mlrs',   'salvos_left': 3, 'shells_per_salvo': 40}]
                         The function does NOT mutate this list — caller decrements salvos_left.
        deep_level:      Player penetration depth: 1 (shallow), 2 (medium), 3 (deep).
        active_contacts: Number of ongoing engagements between player and enemy units.
        current_turn:    Current game turn within the phase (1-based).
        ai_arty_table:   DataFrame with columns: deep_level, has_contact, fire_d20, max_assets.
                         Loaded from Google Sheets tab 'ai_arty_decision'.
        total_turns:     Number of turns in the phase (default 8).

    Returns:
        List of asset dicts selected to fire this turn (subset of input assets).
        Each selected asset fires one salvo (shells_per_salvo shells).

    Balance table reference (ai_arty_decision sheet):
        deep_level | has_contact | fire_d20 | max_assets
             1     |      0      |    0     |     0      # never without contact
             1     |      1      |    5     |     1      # 25%, 1 asset, conservative
             2     |      0      |    3     |     1      # 15%, rare, 1 asset
             2     |      1      |    9     |     2      # 45%, up to 2 assets
             3     |      0      |    13    |     2      # 65%, aggressive
             3     |      1      |    19    |    99      # 95%, all assets
    """
    # 1. Determine has_contact flag
    has_contact = 1 if active_contacts > 0 else 0

    # 2. Look up balance row
    row = ai_arty_table[
        (ai_arty_table["deep_level"] == deep_level) &
        (ai_arty_table["has_contact"] == has_contact)
    ]
    if row.empty:
        print(f"[ai_arty_decide] No table row for deep_level={deep_level}, has_contact={has_contact}")
        return []

    fire_d20   = int(row.iloc[0]["fire_d20"])
    max_assets = int(row.iloc[0]["max_assets"])

    # 3. Pacing correction — deep_level 2 only: spread salvos across the phase
    #    If fewer total salvos remain than turns left → slow down (reduce threshold)
    if deep_level == 2:
        turns_left   = max(1, total_turns - current_turn + 1)
        total_salvos = sum(a["salvos_left"] for a in assets)
        if total_salvos > 0 and total_salvos < turns_left:
            # more turns than salvos → scale down threshold to conserve
            fire_d20 = int(fire_d20 * total_salvos / turns_left)

    # 4. Filter to assets that still have ammo
    available = [a for a in assets if a.get("salvos_left", 0) > 0]
    if not available or fire_d20 == 0:
        return []

    # 5. Roll d20 per asset; collect candidates
    random.shuffle(available)   # randomise order so no asset gets priority by position
    candidates = []
    for asset in available:
        if random.randint(1, 20) <= fire_d20:
            candidates.append(asset)

    # 6. Cap by max_assets
    selected = candidates[:max_assets]

    # 7. Print summary
    if selected:
        names = ", ".join(a["weapon"] for a in selected)
        print(
            f"  [ИИ арта] ход {current_turn} | deep={deep_level} contact={has_contact} "
            f"| fire_d20={fire_d20} | стреляют: {names}"
        )
    else:
        print(
            f"  [ИИ арта] ход {current_turn} | deep={deep_level} contact={has_contact} "
            f"| fire_d20={fire_d20} | тишина"
        )

    return selected