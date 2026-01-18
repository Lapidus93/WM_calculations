import itertools
from collections import Counter
import matplotlib.pyplot as plt
import random 
from typing import Optional
##### import random
from collections import Counter
import wm_unit as wmu
import pandas as pd

class Unit:
    def __init__(self, unit_id: str, size = str,
                 alive_df=None, cas_df=None, last_parameters: Optional[dict] = None,side=str):

        self.unit_id = unit_id
        self.size = size
        self.side = side

        # alive и cas — DataFrame
        self.alive_df = alive_df

        if 0 < len(self.alive_df) <= 12:
            self.size = 'SQ'
        elif 13 < len(self.alive_df) <= 40:
            self.size = 'PT'
        elif len(self.alive_df) > 40:
            self.size = 'CM'
        
        if 'type' in self.alive_df.columns:
            self.size = 'ARMOR'





        self.cas_df = cas_df

        self.last_parameters = last_parameters or {
            'elev_pos': 0,
            'cover_level': 0,
            'target_distance': 0,
            'enemy_unit_id': 'id1',
            'berserk_mode': 0,
        }


    def check_unit_parameters(self):
        elev_pos = 0
        cover_level = 0
        target_distance = 0
        
        print("""
        ######
        {}
        ######
        """.format(self.unit_id))
        for key in self.last_parameters:
       
            print(key,self.last_parameters[key],'?')
            x = input()
            if x == '':
                pass
            else:
                try:
                    self.last_parameters[key] = int(x)
                except:
                    self.last_parameters[key] = str(x)

    def get_size_decrease(self):
            size = str(self.size)
            size_decrease = 1
            if size == 'CM':
                size_decrease = 0.6
            elif size == 'PT':
                size_decrease = 0.8
            elif size == 'SQ':
                size_decrease = 0.9
            return size_decrease    
    
    def calculate_attack_power(self):
  

        size_decrease = self.get_size_decrease()
        
        berserk_mode = self.last_parameters['berserk_mode']
        if berserk_mode == '1':
            berserk_mode = 1.5
        else:
            berserk_mode = 1

        cover_attack_bonus = self.last_parameters['cover_level']
        cover_attack_bonus = pow(1.1,cover_attack_bonus+1)

        elevation_bonus = self.last_parameters['elev_pos']
        elevation_bonus = pow(1.4,cover_attack_bonus+1)

        attack_power = (self.alive_df['power'].sum() - len(self.cas_df)/5) * size_decrease * cover_attack_bonus * berserk_mode  * elevation_bonus
                
               
        return int(round(attack_power,0))
    
    def calculate_cas_amount(self,attack_power,koef,other_unit,result):

        target_distance = self.last_parameters['target_distance']
        target_distance = pow(0.75,target_distance+1)

        defender_cover = other_unit.last_parameters['cover_level']

        elevation_bonus = self.last_parameters['elev_pos'] - other_unit.last_parameters['elev_pos']
        elevation_bonus = pow(1.4,elevation_bonus)

        enemy_cas = attack_power * koef * target_distance * elevation_bonus

        if result in ['засада','поражение'] and str(other_unit.last_parameters['berserk_mode']) == '1':
            chence = random.randint(1,3)
            if chence == 1:
                berserk_koef = 1
            elif chence == 2:
                berserk_koef = 1.5
            elif chence == 3:
                berserk_koef = 2
            enemy_cas = enemy_cas * berserk_koef


        if enemy_cas < 3:
            enemy_cas = 3
        casualties = 0

        enemy_cas = int(round(enemy_cas,0))

        for i in range(3):
            casualties += random.randint(1,enemy_cas)
        casualties = casualties - 3 - defender_cover*2

        if casualties <0:
            casualties = 0


        if defender_cover == 0:
            cover_safer =1 
        elif defender_cover == 1:
            cover_safer =0.5 
        elif defender_cover == 2:
            cover_safer =0.3
        elif defender_cover == 3:
            cover_safer =0.3
        elif defender_cover == 4:
            cover_safer =0.3

        max_casualties = int(round(cover_safer * len(other_unit.alive_df),0))

        if casualties > max_casualties:
            print(other_unit.unit_id, ' вжат землю')
            casualties = max_casualties+0
            
        return casualties

    def calculate_side_attack_cas_amount(self,other_unit):

        distance_decrease = 1 
        if self.last_parameters['target_distance'] == 0:
            distance_decrease = 0.7
        elif self.last_parameters['target_distance'] == 1:
            distance_decrease = 0.5
        elif self.last_parameters['target_distance'] == 2:
            distance_decrease = 0.3
        elif self.last_parameters['target_distance'] == 3:
            distance_decrease = 0.2
        elif self.last_parameters['target_distance'] == 4:
            distance_decrease = 0.1

        size_decrease = self.get_size_decrease()

        attack_power = int(round(len(self.alive_df) * size_decrease * distance_decrease, 0))

        size_bonus = 4
        if 0 < len(other_unit.alive_df) <= 12:
            size_bonus = 8
        elif 13 < len(other_unit.alive_df) <= 60:
            size_bonus = 6
            
        cover_bonus = 4
        if other_unit.last_parameters['cover_level'] == 1:
            cover_bonus = 6
        elif other_unit.last_parameters['cover_level'] == 2:
            cover_bonus = 8
        elif other_unit.last_parameters['cover_level'] == 3:
            cover_bonus = 10
        elif other_unit.last_parameters['cover_level'] == 4:
            cover_bonus = 12
                        
            
        defence_power = cover_bonus*size_bonus

        print(attack_power,defence_power)

        attack = 0
        defence = 0

        for i in range(3):
            attack += random.randint(1, attack_power)
        attack = attack - 3 

        for i in range(3):
            defence += random.randint(1, defence_power)
        defence = defence - 3 

        casualties = attack - defence

        print(attack,defence)
        print(casualties)

        if casualties <0:
            casualties = 0


        defender_cover = other_unit.last_parameters['cover_level']

        if defender_cover == 0:
            cover_safer =1 
        elif defender_cover == 1:
            cover_safer =0.5 
        elif defender_cover == 2:
            cover_safer =0.3
        elif defender_cover == 3:
            cover_safer =0.3
        elif defender_cover == 4:
            cover_safer =0.3

        max_casualties = int(round(cover_safer * len(other_unit.alive_df),0))

        if casualties > max_casualties:
            print(other_unit.unit_id, ' вжат землю')
            casualties = max_casualties+0
            
        return casualties

    





    def attack_unit(self, other_unit: "Unit",logs,current_time):
        def calculate_result(team1,team2):
                # --- t1: сумма 2 кубиков d24 ---
            if team1 <2:
                t1 = 1
            else:
                t1 = random.randint(1, team1)
            # --- t2: сумма 2 кубиков d60 ---
                
            if team2 <2:
                t2 = 1
            else:
                t2 = random.randint(1, team2)
            # --- t2: сумма 2 кубиков d60 ---
                
            r = round(t1 / t2, 1)
            if r <= 0.3:
                return "засада","разгром"
            elif r < 0.8:
                return "поражение","победа"
            elif r <= 1.25:
                return "ничья","ничья"
            elif r < 3.33:
                return "победа","поражение"
            else:
                return "разгром","засада"

        def calculate_koef(result):
            koef = 1
            if result == "засада":
                koef = 0.03
            elif result == "поражение":
                koef = 0.03
            elif result == "ничья":
                koef = 0.06
            elif result == "победа":
                koef = 0.18
            elif result == "разгром":
                koef = 0.65
            return koef
        

        def manage_kills(unit_df, kills):
            for k in range(kills):
                # выбрать случайную строку
                rnd_index = unit_df.sample(n=1).index[0]
                # увеличить счётчик убийств на 1
                unit_df.loc[rnd_index, "kill_count"] += 1
            
        def manage_casualties(alive_df, cas_df, cas):
            if cas > len(alive_df):
                cas = len(alive_df)
                    

            # 1. случайный выбор cas строк
            selected = alive_df.sample(n=cas, replace=False)
            
            # 2. добавляем их в cas_df
            cas_df = pd.concat([cas_df, selected], ignore_index=True)
            
            # 3. удаляем выбранные строки из alive_df
            alive_df = alive_df.drop(selected.index).reset_index(drop=True)
                
            return alive_df, cas_df
        
        log_our_force = len(self.alive_df)
        log_enemy_force = len(other_unit.alive_df)


        for i in [self,other_unit]:
            i.check_unit_parameters()    
        
        team1_power = self.calculate_attack_power()
        team2_power = other_unit.calculate_attack_power()

        result1,result2 = calculate_result(team1_power,team2_power)

        cas_koef1 = calculate_koef(result1)
        cas_koef2 = calculate_koef(result2)

        cas1 = self.calculate_cas_amount(team1_power,cas_koef1,other_unit,result2)


        if str(other_unit.last_parameters['enemy_unit_id']) != str(self.unit_id):
            print('атака без ответа')

            cas1 = self.calculate_side_attack_cas_amount(other_unit)

            manage_kills(self.alive_df, cas1)
            alive_df, cas_df = manage_casualties(other_unit.alive_df, other_unit.cas_df, cas1)
            other_unit.alive_df = alive_df
            other_unit.cas_df = cas_df
            print(cas1)

            cas2 = 0
        
        else:
            cas2 = other_unit.calculate_cas_amount(team2_power,cas_koef2,self,result1)    
        
            manage_kills(self.alive_df, cas1)
            manage_kills(other_unit.alive_df, cas2)

            alive_df, cas_df = manage_casualties(self.alive_df, self.cas_df, cas2)
            self.alive_df = alive_df
            self.cas_df = cas_df

            alive_df, cas_df = manage_casualties(other_unit.alive_df, other_unit.cas_df, cas1)
            other_unit.alive_df = alive_df
            other_unit.cas_df = cas_df
            

            print(result1)
            print(cas_koef1,cas_koef2)
            print(cas1,cas2)


        new_log = [current_time,
                   self.side,
                   self.unit_id,
                   self.size,
                   log_our_force,
                   cas2,
                   other_unit.unit_id,
                   other_unit.size,
                   log_enemy_force,
                   cas1,result1]
        new_log = pd.DataFrame([new_log],columns=['time','attack_unit_side','attack_unit','attack_unit_size','attack_unit_alive_force','attack_cas',
                                                  'defend_unit','defend_unit_size','defend_unit_alive_force','defend_cas','result'])
        
        logs = pd.concat([logs,new_log])

        return logs
        
    
    def __repr__(self):
        return (f"Unit(unit_id={self.unit_id}, size={self.size}, alive_df={len(self.alive_df)}, "
                        f"cas_df={len(self.cas_df)}, "
                        f"last_parameters={self.last_parameters})")
