import itertools
from collections import Counter
import matplotlib.pyplot as plt
import random 
from typing import Optional
import random
from collections import Counter
import wm_unit as wmu
import pandas as pd




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
