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