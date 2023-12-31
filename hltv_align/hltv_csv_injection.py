import pandas as pd
import numpy as np
from utils import *
from tqdm import tqdm

from collections import OrderedDict, defaultdict, Counter
import itertools


def convertSeconds(seconds):
    if isinstance(seconds, float):
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        sec_left = seconds % 60
        return str(int(hours)) + 'h' + str(int(minutes)) + 'm' + str(int(sec_left)) + 's; original seconds: ' + str(seconds)
    else:
        return seconds

path_hltv = "clean_data/formatted_hltv_scrape.csv"
# path_all = "clean_data/all.csv"
path_all = "clean_data/all_data.csv"


df_hltv = pd.read_csv(path_hltv)
df_all = pd.read_csv(path_all)

#To prepare for alignment, insert a column for alignment indication
insertion_index = df_all.columns.get_loc('Player_Name_0')-1
# -insert outcome
df_all.insert(insertion_index, 'Outcome', 'NAN')
# -insert side columns 
df_all.insert(insertion_index, 'Side_Team1', 'unknown')
df_all.insert(insertion_index, 'Side_Team0', 'unknown')

# -insert alignment confirmation
df_all.insert(1, 'hltv_aligned?', False)

all_teams = pd.unique(df_all[['Team_0', 'Team_1']].values.ravel('K'))
hltv_teams = pd.unique(df_hltv[['T0', 'T1']].values.ravel('K'))

dict_all2hltv = createDictGuess(all_teams, hltv_teams, toLower=False)

#convert dict hltiv
hltv_group_key = ['Date', 'Map_ID', 'T0', 'T1', 'Map']
#cast 'date' to datetime
df_hltv['Date'] = pd.to_datetime(df_hltv['Date']).dt.strftime('%Y-%m-%d')
hltv_groupby = df_hltv.groupby(hltv_group_key, sort=False)

#init dict hltv
# dict_hltv = OrderedDict()
dict_hltv = defaultdict(dict)
for n, group in hltv_groupby:
    date = n[0]
    teams = n[1:]
    dict_hltv[date][teams] = group

print('dict_hltv', dict_hltv.keys())

#STAGE2SKIP
STAGE2SKIP = ['Showmatch']

#create groupby for all.csv
all_groupkey = ['Date', 'Team_0', 'Team_1']
all_groupby = df_all.groupby(all_groupkey, sort=False)

#init final: to store aligned data
final = pd.DataFrame(columns=df_all.columns)

k=0
RECORD = []

for map_played, group in all_groupby:
    #get stage
    stage = group['Stage'].unique()[0]
    #get match id
    # game_id = group['GameID'].unique()[0]
    #strange case where team1==team2
    bool_sameteam = map_played[1] == map_played[2]
    if any([stage in STAGE2SKIP, bool_sameteam]):
        print('skipping', map_played,' because of', STAGE2SKIP,'stage or same team')
        final = pd.concat([final, group], axis=0)
        continue

    date = pd.to_datetime(map_played[0])
    plus_one = date + pd.Timedelta(days=1)
    ls_dates = [date, plus_one]
    ls_str_dates = [x.strftime('%Y-%m-%d') for x in ls_dates]
    #get team names
    t0_t1_map = [dict_all2hltv[x] for x in map_played[1:3]]

    #choose dated dict
    ls_dict = [dict_hltv[x] for x in ls_str_dates if x in dict_hltv.keys()]
    #get all possible keys
    ls_keys = [list(x.keys()) for x in ls_dict]
    #choose keys based on team names
    match = lambda key: sum([t in key for t in t0_t1_map])
    THRESHOLD = 2
    
    #create criteria for keys
    matched_keys = [[key for key in keys if match(key)>=THRESHOLD] for keys in ls_keys]

    
    #get keys
    ls_keys = max(matched_keys, key=lambda x:len(x))
    #sort keys from newest game to oldest game
    ls_keys.sort(key=lambda x: x[0], reverse=True)
    #get index of dict
    dict_index = matched_keys.index(ls_keys)

    #list of hltv match recording
    ls_hltv = [ls_dict[dict_index][key] for key in ls_keys]

    # hltv alignment data
    try:
        hltv_align = ls_hltv[0] ###########################IMPORTANT##################
    except:
        print('failed to find acceptable hltv match for', map_played)
        continue
    #chop group into rounds based on HP
    index_fullHP = group["Ingame_Time_Passed"].index
    #consecutive index
    round_group = index_fullHP.groupby((group["Round_ID"].diff() != 0).cumsum())

    #before aligning data, first align team names
    bool_t0_aligned = hltv_align['T0'].unique()[0] == t0_t1_map[0]

    print('--------------------------------------------------')
    print('map_played', map_played)
    print('matched_keys', matched_keys)
    print('len ls_hltv', [len(x) for x in ls_hltv])
    print('len(round_group)', len(round_group.items())) 

    # if map_played == ('2023-05-10', 'GamerLegion', 'OG'):
    #     print('--------------------------------------------------')
    #     print('map_played', map_played)
    #     print('matched_keys', matched_keys)
    #     print('len ls_hltv', [len(x) for x in ls_hltv])
    #     print('len(round_group)', len(round_group.items())) 
    #     for num_round, round_index in round_group.items():
    #         sec = group.loc[round_index[0], 'Stream_Time_Past']
    #         s1 = group.loc[round_index[0], 'Score_0']
    #         s2 = group.loc[round_index[0], 'Score_1']

    #         print('num_round', num_round, 'current score', s1, ':',s2 ,'; start of round', convertSeconds(sec))

    #     raise Exception('stop')
    # #only print if the date is 2023-05-09 or 2023-05-10
    # if '2023-05-09' in ls_str_dates or '2023-05-10' in ls_str_dates:
    #     print('--------------------------------------------------')
    #     print('map_played', map_played)
    #     print('BO', Counter(group['BO']))
    #     print('matched_keys', matched_keys)
    #     print('len ls_hltv', [len(x) for x in ls_hltv])
    #     #print number of rounds
    #     print('len(round_group)', len(round_group.items()))

    n = 0

    for num_round, round_index in round_group.items():
        #trusting FCFS; after checking stream, there is a replay of particular rounds
        #  - where the stream overlay is exactly the same as the normal match except it is replay
        #  - To avoid this, we will only trust the first n rounds played for all matches
        #  - As for program, we here check if the current round number is greater or equal to the hltv record
        print("num_round: ", num_round)
        print("len(hltv_align)", len(hltv_align))

        if num_round <= len(hltv_align):
            #mark alignment
            group.loc[round_index,'hltv_aligned?'] = True

            #first get correct round index for hltv_align
            hltv_index = hltv_align.index[num_round-1] #num_round starts from 1

            #Align map
            group.loc[round_index,'Map'] = hltv_align.loc[hltv_index, 'Map']

            #Align BO
            group.loc[round_index,'BO'] = hltv_align.loc[hltv_index, 'BO']

            #Fill outcome
            group.loc[round_index,'Outcome'] = hltv_align.loc[hltv_index, 'Outcome']

            #align everything except Map
            if bool_t0_aligned:
                #ALIGN NAMES

                #round score
                group.loc[round_index,'Score_0'] = hltv_align.loc[hltv_index, 'Score_Stream_T0']
                group.loc[round_index,'Score_1'] = hltv_align.loc[hltv_index, 'Score_Stream_T1']

                #Map_score
                group.loc[round_index,'Team0_Map_Score'] = hltv_align.loc[hltv_index, 'Map_Score_T0']
                group.loc[round_index,'Team1_Map_Score'] = hltv_align.loc[hltv_index, 'Map_Score_T1']

                #Team0_Side
                group.loc[round_index,'Side_Team0'] = hltv_align.loc[hltv_index, 'Side_T0']
                group.loc[round_index,'Side_Team1'] = hltv_align.loc[hltv_index, 'Side_T1']
            else:
                group.loc[round_index,'Score_0'] = hltv_align.loc[hltv_index, 'Score_Stream_T1']
                group.loc[round_index,'Score_1'] = hltv_align.loc[hltv_index, 'Score_Stream_T0']

                #Map_score
                group.loc[round_index,'Team0_Map_Score'] = hltv_align.loc[hltv_index, 'Map_Score_T1']
                group.loc[round_index,'Team1_Map_Score'] = hltv_align.loc[hltv_index, 'Map_Score_T0']

                #Team0_Side
                group.loc[round_index,'Side_Team0'] = hltv_align.loc[hltv_index, 'Side_T1']
                group.loc[round_index,'Side_Team1'] = hltv_align.loc[hltv_index, 'Side_T0']

        else:
            print('skipping last round: suspecting that the last round is a replay')
            n += 1
            #log starting time of round
            RECORD.append(group.loc[round_index[0], 'Stream_Time_Past'])

    # if n > 1:
    #     k += 1
    #     # print('max_keys', max_keys)
    #     print('--------------------------------------------------')

    #     print('map_played', map_played)
    #     print('BO', Counter(group['BO']))
        
    #     # break
    #     print('matched_keys', matched_keys)

    #     RECORD.append([map_played, max_key, n])
    #     if k == 2:
    #         final = pd.concat([final, group], axis=0)
    #         #extract key from matched_keys
    #         keys_from_single_day = max(matched_keys, key = lambda ls: sum([x[1] for x in ls]))
    #         ls_matches = [[len(ls_dict[i][key_overlap_tuple[0]]) for key_overlap_tuple in matched_keys[i]] for i in range(len(matched_keys))]
    #         print('ls_matches', ls_matches)
            
    #         print('len(round_group)', len(round_group))

    #         ls_start =  [group.loc[round_index[0], 'Stream_Time_Past'] for _, round_index in round_group.items()]
            
    #         print('timestamp for start of every round', '\n'.join([convertSeconds(x) for x in ls_start]))
    #         break


    #combine
    final = pd.concat([final, group], axis=0)


# print('--------------------------------------------------')
# print("RECORD")



#function takes an integer of seconds and outputs a string of hours, minutes, and seconds

# for x in RECORD:

#     print(convertSeconds(x))



path_aligned = 'clean_data/hltv_aligned.csv'
print('finished aligning, storing data to', path_aligned)

print('total num rows', len(final), "final.value_counts()", final["hltv_aligned?"].value_counts())

#Finally, save the aligned data
final.to_csv(path_aligned, index=False)