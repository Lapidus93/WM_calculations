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
    def __init__(self, unit_id: str, size: str,
                 alive_df=None, cas_df=None, last_parameters: Optional[dict] = None):

        self.unit_id = unit_id
        self.size = size

        # alive и cas — DataFrame
        self.alive_df = alive_df
        self.cas_df = cas_df

        self.last_parameters = last_parameters or {
            'elev_pos': 0,
            'cover_level': 0,
            'target_distance': 0,
            'enemy_unit_id': 'id1',
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
                self.last_parameters[key] = int(x)

    
    def calculate_attack_power(self):

        def get_size_decrease(size):
            size_decrease = 1
            if size == 'CM':
                size_decrease = 0.6
            elif size == 'PT':
                size_decrease = 0.8
            elif size == 'SQ':
                size_decrease = 0.9
            return size_decrease      
        size_decrease = get_size_decrease(self.size)
        
        cover_attack_bonus = self.last_parameters['cover_level']
        cover_attack_bonus = pow(1.1,cover_attack_bonus)

        attack_power = (self.alive_df['power'].sum() - len(self.cas_df)/5) * size_decrease * cover_attack_bonus
        print(self.unit_id,attack_power)
                
               
        return int(round(attack_power,0))

    





    def attack_unit(self, other_unit: "Unit"):
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



        for i in [self,other_unit]:
            i.check_unit_parameters()    
        
        team1_power = self.calculate_attack_power()
        team2_power = other_unit.calculate_attack_power()



        result1,result2 = calculate_result(team1_power,team1_power)

        print(result1,result2)
        
    
    
    def __repr__(self):
        return (f"Unit(unit_id={self.unit_id}, size={self.size}, alive_df={len(self.alive_df)}, "
                        f"cas_df={len(self.cas_df)}, "
                        f"last_parameters={self.last_parameters})")
