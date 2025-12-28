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
    def __init__(self, unit_id: str, size: str, size_decrease: float = 1.0,
                 alive_df=None, cas_df=None, last_parameters: Optional[dict] = None):

        self.unit_id = unit_id
        self.size = size
        self.size_decrease = size_decrease

        # alive и cas — DataFrame
        self.alive_df = alive_df
        self.cas_df = cas_df

        self.last_parameters = last_parameters or {
            'elev_pos': 0,
            'cover_level': 0,
            'target_distance': 0,
            'enemy_unit_id': 'id1',
        }


    def target_vals_to_koefs(self):
        elev_pos = 1
        cover_level = 1
        target_distance = 1
        
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
                self.last_parameters[key] = int(x)

        if self.last_parameters['target_distance'] > 0:
            target_distance =  pow(0.7,self.last_parameters['target_distance']-1)
        return target_distance  

    
    def calculate_unit_power(self):
 

        
        """
        Power = (alive - cas * 3) * size_decrease
        округлить и вернуть как int
        """
        power = (self.alive_df['power'].sum() - len(self.cas_df))/5 * self.size_decrease
        print(self.unit_id,power)
        
        target_distance = self.target_vals_to_koefs()
        
        power = power* target_distance
               
        return int(round(power))

    


    def attack_unit(self, other_unit: "Unit"):
        """
        unit1.attack_unit(unit2)

        При вызове:
        - У unit2 увеличивается cas на количество alive у unit1
        """

        def calculate_attack(t1, t2):

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


            def calculate_casualties(power, koef):
                r = int(round(power*koef,0))
                if r < 3:
                    r = 3
                casualties = 0
                for i in range(3):
                    casualties += random.randint(1,r)
                casualties -= 3
                
                return casualties
            
            
            result1,result2 = calculate_result(t1,t2)
            koef1 = calculate_koef(result1)
            koef2 = calculate_koef(result2)
            cas1 =  calculate_casualties(t1, koef1)
            cas2 =  calculate_casualties(t2, koef2)
            print(result1)
            
            return cas1, cas2

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
            print(cas)
            selected = alive_df.sample(n=cas, replace=False)
        
            # 2. добавляем их в cas_df
            cas_df = pd.concat([cas_df, selected], ignore_index=True)
        
            # 3. удаляем выбранные строки из alive_df
            alive_df = alive_df.drop(selected.index).reset_index(drop=True)
            
            return alive_df, cas_df

        
        team1_power = self.calculate_unit_power()
        team2_power = other_unit.calculate_unit_power()
               
        cas1, cas2 = calculate_attack(team1_power,team2_power)
        
        manage_kills(self.alive_df, cas1)
        manage_kills(other_unit.alive_df, cas2)

        alive_df, cas_df = manage_casualties(self.alive_df, self.cas_df, cas2)
        self.alive_df = alive_df
        self.cas_df = cas_df
        
        alive_df, cas_df = manage_casualties(other_unit.alive_df, other_unit.cas_df, cas1)
        other_unit.alive_df = alive_df
        other_unit.cas_df = cas_df

    
    
    def __repr__(self):
        return (f"Unit(unit_id={self.unit_id}, size={self.size}, alive_df={len(self.alive_df)}, "
                        f"cas_df={len(self.cas_df)}, "
                        f"size_decrease={self.size_decrease}, "
                        f"last_parameters={self.last_parameters})")
