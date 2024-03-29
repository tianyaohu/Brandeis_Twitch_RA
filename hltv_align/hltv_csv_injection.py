import pandas as pd
from utils import *
from tqdm import tqdm

from collections import defaultdict

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

#Read csv from path
df_hltv = pd.read_csv(path_hltv)
df_all = pd.read_csv(path_all)

#delete SHOWMATCH from datarame
df_all = df_all[df_all['Stage'] != 'Showmatch']

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

nth_round = 0
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
    ls_keys = [x.keys() for x in ls_dict]

    #check for how many keys match
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
    hltv_map_gen = (ls_dict[dict_index][key] for key in ls_keys)

    #consecutive index
    round_group = group.index.groupby((group["Round_ID"].diff() != 0).cumsum())


    print('--------------------------------------------------')
    # print('t0_t1_map', t0_t1_map)
    # # print('ls_keys', ls_keys)
    print('ls_keys', ls_keys)
    # print()
    # print('len(round_group.items())', len(round_group.items()))
    # print('start of group', group.index[0])
    # print('end of group', group.index[-1])
    print("-----------------------------------")

    num_round_skipped = 0
    indices_to_kill = []
    bool_drop_indices = True

    #Map Detection: BO3 focused
    bool_seen_00 = False
    round_count_offset = 0
    prev_round_id = pd.DataFrame()

    for nth_round, round_index in round_group.items():
        #trusting FCFS; after checking stream, there is a replay of particular rounds
        #  - where the stream overlay is exactly the same as the normal match except it is replay
        #  - To avoid this, we will only trust the first num_round_skipped rounds played for all matches
        #  - As for program, we here check if the current round number is greater or equal to the hltv record
        # print('nth_round', nth_round)

        cur_round_id = group.loc[round_index[0], ['Team_0', 'Team_1', 'Map']]

        # bool_none_repeat = not cur_round_id.equals(prev_round_id)
        score_is_00 = all(group.loc[round_index[0], ['Score_0', 'Score_1']] == [0, 0])

        #check if score is 0, 0
        if score_is_00 and bool_seen_00 == False: #and bool_none_repeat:
            prev_round_id = cur_round_id
            print("00000000000000000000000000000000000000")
            print(f'0, 0 detected, starting of map, round index {round_index[0]}')
            print(f'starting index {group.index[0]}; ending index {group.index[-1]}')
            #record the round 
            bool_seen_00 = True
            #set round_offset
            round_count_offset = nth_round -1 #nth_round starts from 1
            #get hltv_align
            try:
                print("HLTV NEXT")
                hltv_align = next(hltv_map_gen) ###########################IMPORTANT##################
            except:
                #get all possible keys
                print('failed to find acceptable hltv match for', map_played)
                #print the start and end of the affected indices
                print(f'skipping start {group.index[0]}; end: {group.index[-1]}')
                break

        #init relative round: offsetting for previous map played (BO3) and replays
        relative_round = nth_round - round_count_offset

        print('===========t0_t1_map', t0_t1_map)
        print('roundID', group.loc[round_index[0], 'Round_ID'])
        print('is score 0-0', score_is_00)
        print('bool_seen_00', bool_seen_00)
        print('round_index start', round_index[0], 'round_index end', round_index[-1])
        print('relative_round >= len(hltv_align)', relative_round >= len(hltv_align), 'score_max', max(group.loc[round_index[0], ['Score_0', 'Score_1']]))
        print(f'R# { relative_round} HLTV# {len(hltv_align)} offset {round_count_offset}')

        #Skipping the replayes here, round exhaustion and score >= 15:
        if relative_round >= len(hltv_align) and max(group.loc[round_index[0], ['Score_0', 'Score_1']]) >= 15:
            #set flag for 0,0 triggering.
            bool_seen_00 = False
            #print the start of the affected indices
            print('==================================')
            print(f'round_exhaustion_triggered start {round_index[0]}; end: {round_index[-1]}')
            print('==================================')

    # """
        if relative_round <= len(hltv_align):
            #mark alignment
            group.loc[round_index,'hltv_aligned?'] = True

            #first get correct round index for hltv_align
            hltv_index = hltv_align.index[relative_round-1] #relative_round starts from 1

            #Align map
            group.loc[round_index,'Map'] = hltv_align.loc[hltv_index, 'Map']

            #Align BO
            group.loc[round_index,'BO'] = hltv_align.loc[hltv_index, 'BO']

            #Fill outcome
            group.loc[round_index,'Outcome'] = hltv_align.loc[hltv_index, 'Outcome']

            #before aligning data, first align team names
            bool_t0_aligned = hltv_align['T0'].unique()[0] == t0_t1_map[0]

            #align everything except Map
            if bool_t0_aligned:
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

            print("hltv_align.loc[hltv_index, ['Score_Stream_T0', 'Score_Stream_T1']]: ", hltv_align.loc[hltv_index, ['Score_Stream_T0', 'Score_Stream_T1']].values)

        else:
            #mark indices to kill
            indices_to_kill += round_index.tolist()

            print('skipping last round: suspecting that the last round is a replay')
            num_round_skipped += 1
            #log starting time of round
            RECORD.append(group.loc[round_index[0], 'Stream_Time_Past'])

    #combine
    final = pd.concat([final, group], axis=0)

path_aligned = 'clean_data/hltv_aligned.csv'
print('finished aligning, storing data to', path_aligned)
print('total num rows', len(final), "final.value_counts()", final["hltv_aligned?"].value_counts())

#Finally, save the aligned data
print(f'output file  to {path_aligned}')
final.to_csv(path_aligned, index=False)
# """
