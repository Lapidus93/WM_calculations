import itertools
import random
from collections import Counter
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd

class Unit:
    def __init__(
        self,
        unit_id: str,
        overall_type: str,
        personal_type: str,
        size: str = "",
        alive_df=None,
        cas_df=None,
        armor_part=None,
        last_parameters: Optional[dict] = None,
        side: str = "",
    ):
        self.overall_type = overall_type
        self.personal_type = personal_type
        self.unit_id = unit_id
        self.size = size
        self.side = side
        self.armor_part = armor_part if armor_part is not None else []


        # alive и cas — DataFrame
        self.alive_df = alive_df


        if 0 < len(self.alive_df) <= 12:
            self.size = 'SQ'
        elif 13 < len(self.alive_df) <= 40:
            self.size = 'PT'
        elif len(self.alive_df) > 40:
            self.size = 'CM'
        



        self.cas_df = cas_df

        self.last_parameters = last_parameters or {
            'elev_pos': 0,
            'cover_level': 0,
            'target_distance': 0,
            'enemy_unit_id': 'id1',
            'berserk_mode': 0,
        }

    @staticmethod
    def manage_casualties(alive_df: pd.DataFrame, cas_df: pd.DataFrame, cas: int):
        """Move random casualties from alive_df to cas_df.

        Notes:
            - If cas is greater than the number of alive rows, it is clamped.
            - Returns (new_alive_df, new_cas_df).
        """
        if cas <= 0 or len(alive_df) == 0:
            return alive_df, cas_df

        if cas > len(alive_df):
            cas = len(alive_df)

        selected = alive_df.sample(n=cas, replace=False)
        cas_df = pd.concat([cas_df, selected], ignore_index=True)
        alive_df = alive_df.drop(selected.index).reset_index(drop=True)
        return alive_df, cas_df

    @staticmethod
    def manage_kills(unit_df: pd.DataFrame, kills: int, cas_type:str):
        """Randomly increment 'kill_count' on unit_df for a given number of kills."""
        if kills <= 0 or len(unit_df) == 0:
            return
        for _ in range(kills):
            rnd_index = unit_df.sample(n=1).index[0]
            unit_df.loc[rnd_index, cas_type] += 1



    def update_current_type(self):
        if self.personal_type == 'inf' and (self.armor_part == [] or len(self.armor_part.alive_df)==0):
            self.overall_type = 'inf'
        if self.personal_type == 'arm':
            self.overall_type = 'arm'
        if self.personal_type == 'inf' and self.armor_part != [] and len(self.armor_part.alive_df)>0:
            self.overall_type = 'mech'
        
      
      


    def check_unit_parameters(self):

        
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
        
        if self.armor_part != [] and len(self.armor_part.alive_df) >0:
            attack_power += self.armor_part.alive_df['power'].sum()
               
        return int(round(attack_power,0))
    
    def calculate_cas_amount(self,koef,other_unit,result):
        
        attack_power = self.alive_df['power'].sum()

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
        def calculate_side_attack_power(attack_power, distance, cover):
            import math
            result = (
                5
                * math.sqrt(attack_power)
                * (0.72 ** distance)
                * (0.75 ** cover)
            )
            return int(round(result))


        distance = self.last_parameters['target_distance']
        attack_power = sum(self.alive_df['power']) 
        cover =  other_unit.last_parameters['cover_level']
                        
        final_power = calculate_side_attack_power(attack_power, distance, cover)

        attack = 0
        defence = 0

        for i in range(3):
            attack += random.randint(1, final_power)
        attack = attack - 3 

        for i in range(3):
            defence += random.randint(1, 10)

        casualties = attack - defence


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

    


    def inf_armor_attack(self,armor_unit):

        def rpg_shot(move,distance):
            cas = 0
            chance = 70
    
            if distance == '1':
                chance = chance*0.5
            if move == '1':
                chance = chance*0.25
            chance = int(round(chance,0))

            shot_result = random.randint(1,100)
            if shot_result <=chance:
                cas+=1
    
            return cas


        shots = 1
        if self.size =='CM':
            shots = 3
    
        move = input('Броня двигается?')
        distance = input('Броня далеко?')

        cas = 0
    
        for i in range(shots):
            cas+= rpg_shot(move,distance)

        if cas > len(armor_unit.alive_df):
            cas = len(armor_unit.alive_df)


        alive_df, cas_df = self.manage_casualties(armor_unit.alive_df, armor_unit.cas_df, cas)
        armor_unit.alive_df = alive_df
        armor_unit.cas_df = cas_df

        Unit.manage_kills(self.alive_df, cas,'apc_kills')

        return armor_unit, cas


    def armor_to_armor_attack(self,armor_unit):

        distance = self.last_parameters['target_distance']
        cas = 0
        for i in range(len(self.alive_df)):
            chance = 5+ distance
            shoot = random.randint(1,10)
            if shoot > chance:
                cas+=1


        if cas > len(armor_unit.alive_df):
            cas = len(armor_unit.alive_df)


        alive_df, cas_df = self.manage_casualties(armor_unit.alive_df, armor_unit.cas_df, cas)
        armor_unit.alive_df = alive_df
        armor_unit.cas_df = cas_df

        Unit.manage_kills(self.alive_df, cas,'apc_kills')

        return armor_unit, cas



    def direct_attack_unit(self, other_unit: "Unit", attack_scale):
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
        

        enem_cas = 0
        fr_cas = 0




        team1_power = self.calculate_attack_power()
        team2_power = other_unit.calculate_attack_power()

        if self.size =='ARMOR' and attack_scale =='short':
            team1_power = int(round(team1_power/2,0))


        result1,result2 = calculate_result(team1_power,team2_power)

        enem_cas = calculate_koef(result1)
        fr_cas_koef = calculate_koef(result2)
        

        if str(other_unit.last_parameters['enemy_unit_id']) != str(self.unit_id):
            print('атака без ответа')

        
            enem_cas = self.calculate_side_attack_cas_amount(other_unit)
            Unit.manage_kills(self.alive_df, enem_cas, 'inf_kills')

            alive_df, cas_df = Unit.manage_casualties(other_unit.alive_df, other_unit.cas_df, enem_cas)
            other_unit.alive_df = alive_df
            other_unit.cas_df = cas_df

            result1 = 'side_attack'



    
        else:
            

            enem_cas = self.calculate_cas_amount(enem_cas,other_unit,result2)
            fr_cas = other_unit.calculate_cas_amount(fr_cas_koef,self,result1)    
    
            Unit.manage_kills(self.alive_df, enem_cas,'inf_kills')
            Unit.manage_kills(other_unit.alive_df, fr_cas,'inf_kills')

            alive_df, cas_df = Unit.manage_casualties(self.alive_df, self.cas_df, fr_cas)
            self.alive_df = alive_df
            self.cas_df = cas_df

            alive_df, cas_df = Unit.manage_casualties(other_unit.alive_df, other_unit.cas_df, enem_cas)
            other_unit.alive_df = alive_df
            other_unit.cas_df = cas_df
        



        return result1 , fr_cas , enem_cas
    

    def base_attack(self, other_unit: "Unit",logs,current_time):
        
        initiator = self.side

        log_attackers_id = self.unit_id   
        log_attackers_type = self.overall_type
        log_attackers_inf_force = 0
        if  self.overall_type in ['inf','mech']:
            log_attackers_inf_force = len(self.alive_df)

        log_attackers_arm_force = 0
        if  self.overall_type =='mech':
            log_attackers_arm_force = len(self.armor_part.alive_df)
        elif  self.overall_type =='arm':
            log_attackers_arm_force = len(self.alive_df)

        log_attackers_cas_inf = 0
        log_attackers_cas_armor = 0
    
        log_defenders_id = other_unit.unit_id   
        log_defenders_type = other_unit.overall_type
        log_defenders_inf_force = 0
        if  other_unit.overall_type in ['inf','mech']:
            log_defenders_inf_force = len(other_unit.alive_df)

        log_defenders_arm_force = 0
        if  other_unit.overall_type =='mech':
            log_defenders_arm_force = len(other_unit.armor_part.alive_df)
        elif  other_unit.overall_type =='arm':
            log_defenders_arm_force = len(other_unit.alive_df)

        log_defenders_cas_inf = 0
        log_defenders_cas_armor = 0


        log_attack_type = ''
        log_result = ''


        # ПЕХОТА атакует БРОНЮ
        if self.overall_type == 'inf' and other_unit.overall_type == 'arm':
            log_attack_type = 'inf_attacks_armor'

            other_unit, cas1 = self.inf_armor_attack(other_unit)
            Unit.manage_kills(self.alive_df, cas1,'apc_kills')
            print(self.unit_id,'атаковал броню',other_unit.unit_id,'и подбил',cas1,'единиц брони')
            log_defenders_cas_armor += cas1


        else:
            for i in [self,other_unit]:
                i.check_unit_parameters()

            # БРОНЯ атакует БРОНЮ
            if self.overall_type == 'arm' and other_unit.overall_type == 'arm':
                log_attack_type = 'armor_attacks_armor' 
            
                other_unit, cas1 = self.armor_to_armor_attack(other_unit)
                Unit.manage_kills(self.alive_df, cas1,'apc_kills')
                print(self.unit_id,'атаковал броню',other_unit.unit_id,'и подбил',cas1,'единиц брони')
                log_defenders_cas_armor += cas1



            # БРОНЯ атакует МОТОПЕХОТУ 
            # (не указываются айдишники подразделений при проверке параметров)
            elif self.overall_type == 'arm' and other_unit.overall_type == 'mech':
                log_attack_type = 'armor_attacks_mech'

                other_unit, cas1 = self.armor_to_armor_attack(other_unit.armor_part)
           
                Unit.manage_kills(self.alive_df, cas1,'apc_kills')
                print(self.unit_id,'атаковал броню',other_unit.unit_id,'и подбил',cas1,'единиц брони')
                log_defenders_cas_armor +=cas1
             

                log_result,  fr_cas , enem_cas  = self.direct_attack_unit(other_unit,'short')
                print('Бронированный',self.unit_id,'обстрелял пехотный отряд',other_unit.unit_id)
                print('Потери',other_unit.unit_id,enem_cas)
                log_defenders_cas_inf += enem_cas
                log_attackers_cas_armor += fr_cas



            # МОТОПЕХОТА атакует ПЕХОТУ
            elif self.overall_type == 'mech' and other_unit.overall_type == 'inf':
                log_attack_type = 'mech_attacks_inf'

                print('Механизированный',self.unit_id,'атакует пехотный отряд',other_unit.unit_id)
                log_result, fr_cas , enem_cas  = self.armor_part.direct_attack_unit(other_unit,'full')
                print('Бронированный',self.armor_part.unit_id,'наносит потери',enem_cas)    
                log_defenders_cas_inf += enem_cas
                log_attackers_cas_inf += fr_cas


                log_result, fr_cas , enem_cas = self.direct_attack_unit(other_unit,'full')
                print('В стрелковом бою',self.unit_id,'атакует с результатом',log_result)
                print('Потери',self.unit_id,fr_cas,' Потери',other_unit.unit_id,enem_cas)
                log_defenders_cas_inf += enem_cas
                log_attackers_cas_inf += fr_cas


            # МОТОПЕХОТА атакует МОТОПЕХОТУ
            elif self.overall_type == 'mech' and other_unit.overall_type == 'mech':
                log_attack_type = 'mech_attacks_mech'
                
                other_unit.armor_part, cas1 = self.armor_part.armor_to_armor_attack(other_unit.armor_part)
                Unit.manage_kills(self.armor_part.alive_df, cas1,'apc_kills')
                print(self.unit_id,'атаковал броню',other_unit.unit_id,'и подбил',cas1,'единиц брони')
                log_defenders_cas_armor += cas1

                if len(other_unit.armor_part.alive_df) >0:
                    self.armor_part, cas1 = other_unit.armor_part.armor_to_armor_attack(self.armor_part)
                    Unit.manage_kills(other_unit.armor_part.alive_df, cas1,'apc_kills')
                    print(other_unit.unit_id,'атаковал броню',self.unit_id,'и подбил',cas1,'единиц брони')
                    log_attackers_cas_armor += cas1

                log_result, fr_cas , enem_cas = self.direct_attack_unit(other_unit,'short')
                print(self.unit_id,'атаковал отряд',other_unit.unit_id,'c результатом',log_result)
                print('Потери',self.unit_id,fr_cas,' Потери',other_unit.unit_id,enem_cas)
                log_defenders_cas_inf += enem_cas
                log_attackers_cas_inf += fr_cas

                if log_result in ['победа','разгром'] and len(other_unit.armor_part.alive_df) >0 :
                    other_unit, cas1 = self.inf_armor_attack(other_unit.armor_part)
                    Unit.manage_kills(self.alive_df, cas1,'apc_kills')
                    print(self.unit_id,'атаковал броню из отряда',other_unit.unit_id,'и подбил',cas1,'единиц брони')
                    log_defenders_cas_armor += cas1

                elif log_result in ['засада','поражение'] and len(self.armor_part.alive_df) >0 :
                    self, cas1 = other_unit.inf_armor_attack(self.armor_part)
                    Unit.manage_kills(other_unit.alive_df, cas1,'apc_kills')
                    print(other_unit.unit_id,'атаковал броню из отряда',self.unit_id,'и подбил',cas1,'единиц брони')
                    log_attackers_cas_armor += cas1


            # МОТОПЕХОТА атакует БРОНЮ
            elif self.overall_type == 'mech'  and  other_unit.overall_type == 'arm':
                log_attack_type = 'mech_attacks_arm'
                
                other_unit, cas1 = self.armor_part.armor_to_armor_attack(other_unit)
                Unit.manage_kills(self.armor_part.alive_df, cas1,'apc_kills')
                print(self.unit_id,'атаковал броню',other_unit.unit_id,'и подбил',cas1,'единиц брони')
                log_defenders_cas_armor += cas1
            
                if self.last_parameters['target_distance'] <= 1:
                    other_unit, cas1 = self.inf_armor_attack(other_unit)
                    Unit.manage_kills(self.alive_df, cas1,'apc_kills')
                    print(self.unit_id,'атаковал броню',other_unit.unit_id,'и подбил',cas1,'единиц брони')
                    log_defenders_cas_armor += cas1

            # БРОНЯ атакует ПЕХОТУ (не вносим айдишники подразделений)
            elif self.overall_type == 'arm' and other_unit.overall_type == 'inf':
                log_attack_type = 'arm_attacks_inf'

                result1, fr_cas , enem_cas  = self.direct_attack_unit(other_unit,'full')
                print('Бронированный',self.unit_id,'обстрелял пехотный отряд',other_unit.unit_id)
                print('Потери',other_unit.unit_id,enem_cas)
                log_defenders_cas_inf += enem_cas

                
            # ПЕХОТА атакует ПЕХОТУ или МОТОПЕХОТУ
            else:
                log_attack_type = 'inf_attacks_inf'
                if other_unit.overall_type == 'mech':
                    log_attack_type = 'inf_attacks_mech'
                log_result, fr_cas , enem_cas = self.direct_attack_unit(other_unit,'full')
                print(self.unit_id,'атаковал отряд',other_unit.unit_id,'c результатом',log_result)
                print('Потери',self.unit_id,fr_cas,' Потери',other_unit.unit_id,enem_cas)
                log_defenders_cas_inf += enem_cas
                log_attackers_cas_inf += fr_cas

                if log_result in ['победа','разгром'] and (other_unit.armor_part != [] or len(other_unit.armor_part.alive_df) >0 ):

                    other_unit, cas1 = self.inf_armor_attack(other_unit.armor_part)
                    Unit.manage_kills(self.alive_df, cas1,'apc_kills')
                    print(self.unit_id,'атаковал броню из отряда',other_unit.unit_id,'и подбил',cas1,'единиц брони')
                    log_defenders_cas_armor += cas1
               
        if initiator == 'blue':
            new_log = [str(current_time),
            initiator,
            log_attackers_id,
            log_attackers_type,
            log_attackers_inf_force,
            log_attackers_arm_force,
            log_attackers_cas_inf,
            log_attackers_cas_armor,
            log_defenders_id,
            log_defenders_type,
            log_defenders_inf_force,
            log_defenders_arm_force,
            log_defenders_cas_inf,
            log_defenders_cas_armor,
            log_attack_type,
            log_result]
        else:
            new_log = [str(current_time),
            initiator,
            log_defenders_id,
            log_defenders_type,
            log_defenders_inf_force,
            log_defenders_arm_force,
            log_defenders_cas_inf,
            log_defenders_cas_armor,
            log_attackers_id,
            log_attackers_type,
            log_attackers_inf_force,
            log_attackers_arm_force,
            log_attackers_cas_inf,
            log_attackers_cas_armor,
            log_attack_type,
            log_result]

        new_log = pd.DataFrame([new_log],columns=['current_time',
        'initiator',
        'log_blue_id',
        'log_blue_type',
        'log_blue_inf_force',
        'log_blue_arm_force',
        'log_blue_cas_inf',
        'log_blue_cas_armor',
        'log_red_id',
        'log_red_type',
        'log_red_inf_force',
        'log_red_arm_force',
        'log_red_cas_inf',
        'log_red_cas_armor',
        'log_attack_type',
        'log_result'])
    
        logs = pd.concat([logs,new_log])

        return logs
        
    
    def __repr__(self):
        armor_component = 0
        if self.armor_part == []:
            pass
        else:
            armor_component = len(self.armor_part.alive_df)
        return (f"Unit(unit_id={self.unit_id}, overall_type={self.overall_type},personal_type={self.personal_type},size={self.size}, alive_df={len(self.alive_df)}, "
                        f"cas_df={len(self.cas_df)}, " f"armor_part={armor_component}, "
                        f"last_parameters={self.last_parameters})")