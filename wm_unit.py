import random
from typing import Optional

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

        self.alive_df = alive_df

        if 0 < len(self.alive_df) <= 14:
            self.size = 'SQ'
        elif 14 < len(self.alive_df) <= 42:
            self.size = 'PT'
        elif len(self.alive_df) > 42:
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
    def manage_casualties_with_injury(
        alive_df: pd.DataFrame,
        cas_df: pd.DataFrame,
        cas: int,
        attacker_type: str,
        distance: int,
        injury_table: pd.DataFrame,
    ):
        """Move random casualties from alive_df to cas_df with injury classification.

        Sets status = 'killed' / 'heavy' / 'light' on each casualty row
        based on attacker_type ('inf' -> smal_arms, 'arm' -> arm 2) and distance.
        Returns (new_alive_df, new_cas_df).
        """
        if cas <= 0 or len(alive_df) == 0:
            return alive_df, cas_df

        if cas > len(alive_df):
            cas = len(alive_df)

        caliber = 'smal_arms' if attacker_type == 'inf' else 'arm 2'
        distance_clamped = min(int(distance), 4)

        table_row = injury_table[
            (injury_table['distance'] == distance_clamped) &
            (injury_table['caliber'] == caliber)
        ]

        selected = alive_df.sample(n=cas, replace=False).copy()

        if table_row.empty:
            selected['status'] = 'killed'
        else:
            p_kill = float(table_row.iloc[0]['instant_death_perc'])
            p_heavy = float(table_row.iloc[0]['bad_injury_perc'])
            statuses = []
            for _ in range(len(selected)):
                roll = random.random()
                if roll < p_kill:
                    statuses.append('killed')
                elif roll < p_kill + p_heavy:
                    statuses.append('heavy')
                else:
                    statuses.append('light')
            selected['status'] = statuses

        cas_df = pd.concat([cas_df, selected], ignore_index=True)
        alive_df = alive_df.drop(selected.index).reset_index(drop=True)
        return alive_df, cas_df

    @staticmethod
    def manage_kills(unit_df: pd.DataFrame, kills: int, cas_type: str):
        """Randomly increment kill counter on unit_df for a given number of kills."""
        if kills <= 0 or len(unit_df) == 0:
            return
        for _ in range(kills):
            rnd_index = unit_df.sample(n=1).index[0]
            unit_df.loc[rnd_index, cas_type] += 1

    def update_current_type(self):
        if self.personal_type == 'arm':
            self.overall_type = 'arm'
        elif self.personal_type == 'inf' and self.armor_part != [] and len(self.armor_part.alive_df) > 0:
            self.overall_type = 'mech'
        else:
            self.overall_type = 'inf'

    def __repr__(self):
        armor_component = 0
        if self.armor_part != []:
            armor_component = len(self.armor_part.alive_df)
        return (
            f"Unit(unit_id={self.unit_id}, overall_type={self.overall_type}, "
            f"personal_type={self.personal_type}, size={self.size}, "
            f"alive_df={len(self.alive_df)}, cas_df={len(self.cas_df)}, "
            f"armor_part={armor_component}, last_parameters={self.last_parameters})"
        )
