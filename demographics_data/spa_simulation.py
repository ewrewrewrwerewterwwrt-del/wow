import pandas as pd
import numpy as np

# --- Configuration: Seats per Constituency (2016 Distribution) ---
SEAT_DISTRIBUTION = {
    'catalunya': 47,
    'euskadi': 18,
    'galicia': 23,
    'valencia': 33, 
    'navarra': 5,
    'balears': 8,
    'rest': 216 
}

VIRTUAL_REST_STRUCTURE = {
    36: 1,  # Madrid (Urban, Proportional)
    12: 1,  # Seville
    11: 1,  # Malaga
    10: 1,  # Murcia
    9: 1,   # Cadiz
    8: 2,   # Las Palmas, Asturias
    7: 3,   # Granada, Zaragoza, Tenerife
    6: 4,   # Cordoba, Almeria, Toledo, Badajoz
    5: 5,   # Jaen, Huelva, Valladolid, Ciudad Real, Cantabria
    4: 6,   # Leon, Burgos, Salamanca, Albacete, Caceres, La Rioja
    3: 8,   # Avila, Palencia, Segovia, Zamora, Guadalajara, Cuenca, Huesca, Teruel
    2: 1,   # Soria
    1: 2    # Ceuta, Melilla
}

PROTECTED_MINORS = {
    'cc': 0.30,   # Coalicion Canaria
    'prc': 0.25,  # Partido Regionalista de Cantabria
    'te': 0.22,
}

RURAL_BIAS = {
    # Applied to districts with <= 4 seats (approx. 20 provinces)
    'pp': 1.15,      # PP is dominant in rural Castilla
    'psoe': 1.05,    # PSOE holds up well in rural South
    'podemos': 0.75, # Podemos struggles significantly in rural areas
    'cs': 0.85,      # Cs also struggles in rural areas
}

URBAN_BIAS = {
    # Applied to districts with >= 8 seats (Madrid, Malaga, Zaragoza, etc.)
    'pp': 0.95,      # PP is slightly weaker in fierce urban competition
    'psoe': 0.95,
    'podemos': 1.15, # Podemos overperforms in cities
    'cs': 1.05       # Cs overperforms in cities
}

def dhondt_method(votes_dict, num_seats):
    """
    Standard D'Hondt method implementation.
    """
    seats = {party: 0 for party in votes_dict}
    quotients = []
    
    for party, vote_count in votes_dict.items():
        if vote_count > 0:
            quotients.append({
                'party': party, 
                'val': float(vote_count), 
                'original': float(vote_count), 
                'seats': 0
            })
    
    for _ in range(num_seats):
        if not quotients:
            break
        quotients.sort(key=lambda x: x['val'], reverse=True)
        winner = quotients[0]
        winner['seats'] += 1
        winner['val'] = winner['original'] / (winner['seats'] + 1)
        
    for q in quotients:
        seats[q['party']] = q['seats']
        
    return seats

def simulate_rest_constituency(votes_map):
    """
    1. Checks for protected minors, assigns seats, and REMOVES their votes.
    2. Runs Virtual Province simulation for the remaining seats using remaining votes.
    """
    final_seats = {party: 0 for party in votes_map}
    
    working_votes = votes_map.copy()
    total_rest_votes = sum(votes_map.values())
    
   
    
    # 1. Check and assign protected minor seats
    seats_preassigned = 0
    for party, threshold in PROTECTED_MINORS.items():
        if party in working_votes:
            # Check percentage against the GLOBAL Rest total
            party_share = (votes_map[party] / total_rest_votes) * 100
            
            while party_share >= threshold:                
                # Award the protected seat
                final_seats[party] = 1
                seats_preassigned += 1
                party_share -= threshold
                # Remove their votes from the working set
                working_votes[party] = 0

    # 2.  Target districts around size 5-8 (typical sizes where protected parties usually run)
    virtual_districts = []
    for size, count in VIRTUAL_REST_STRUCTURE.items():
        virtual_districts.extend([size] * count)
    
    virtual_districts.sort()
    
    for _ in range(seats_preassigned):
        for i, size in enumerate(virtual_districts):
            if size >= 5:
                virtual_districts[i] -= 1
                break
    
    # 3. Run D'Hondt on the modified districts using the CLEANED votes (no minors)
    for district_size in virtual_districts:
        if district_size > 0:
            district_votes = {}
            
            if district_size <= 4:
                bias_set = RURAL_BIAS
            elif district_size >= 8:
                bias_set = URBAN_BIAS
            else:
                bias_set = {} 
            
            for party, votes in working_votes.items():
                multiplier = bias_set.get(party, 1.0) # Default to 1.0
                district_votes[party] = votes * multiplier
            
            district_result = dhondt_method(district_votes, district_size)
            
            for p, s in district_result.items():
                final_seats[p] += s
            
            

    return final_seats

def simulate_election(input_csv, output_seats_csv):
    try:
        df = pd.read_csv(input_csv)
    except FileNotFoundError:
        print(f"Error: Could not find file {input_csv}")
        return

    # 1. Separate Abstention Data
    abstention_mask = df['party'].str.lower() == 'abstention'
    df_abstention = df[abstention_mask].copy()
    df_parties = df[~abstention_mask].copy()

    # 2. Run Seat Simulation (D'Hondt)
    results_list = []
    
    # Get list of constituencies from the party data
    constituencies = df_parties['constituency'].unique()

    for constituency in constituencies:
        const_key = constituency.lower()
        
        # Get votes for this region
        region_data = df_parties[df_parties['constituency'] == constituency]
        votes_map = pd.Series(region_data.votes.values, index=region_data.party).to_dict()
        
        seat_results = {}
        
        # ROUTING LOGIC
        if const_key == 'rest':
            print(f"Processing 'Rest' using Virtual Province Model (216 seats)...")
            seat_results = simulate_rest_constituency(votes_map)
        else:
            # Standard regions (Catalunya, etc.)
            seats_available = SEAT_DISTRIBUTION.get(const_key, 0)
            if seats_available > 0:
                seat_results = dhondt_method(votes_map, seats_available)
            else:
                print(f"Warning: No configuration for '{constituency}'. Skipping.")
                continue

        # Store Results
        for party, s_count in seat_results.items():
            if s_count > 0: # Only saving winners keeps file cleaner, remove if you want all zeros
                results_list.append({
                    "party": party,
                    "constituency": constituency,
                    "votes": votes_map.get(party, 0),
                    "seats": s_count
                })

    # Save Seat Results
    results_df = pd.DataFrame(results_list)
    results_df = results_df.sort_values(by=['constituency', 'seats'], ascending=[True, False])
    results_df.to_csv(output_seats_csv, index=False)
    print(f"Simulation complete. Seat allocation saved to '{output_seats_csv}'.")

    # 3. Calculate and Print Turnout Stats
    print("\n" + "="*40)
    print("       TURNOUT & ABSTENTION REPORT")
    print("="*40)
    
    # Group valid votes by constituency
    valid_votes = df_parties.groupby('constituency')['votes'].sum()
    
    # Group abstention votes by constituency
    # Use set_index to align with the valid_votes series easily
    abst_votes = df_abstention.set_index('constituency')['votes']
    
    # Combine into a single DataFrame for calculation
    stats = pd.concat([valid_votes, abst_votes], axis=1, keys=['valid', 'abstention']).fillna(0)
    
    stats['census'] = stats['valid'] + stats['abstention']
    stats['turnout_pct'] = (stats['valid'] / stats['census']) * 100
    stats['abst_pct'] = (stats['abstention'] / stats['census']) * 100
    
    # Print Per-Constituency Data
    print(f"{'CONSTITUENCY':<15} | {'TURNOUT':<10} | {'ABSTENTION':<10}")
    print("-" * 40)
    for const, row in stats.iterrows():
        print(f"{const:<15} | {row['turnout_pct']:6.2f}%    | {row['abst_pct']:6.2f}%")

    # 4. Calculate Global Abstention
    total_census = stats['census'].sum()
    total_abstention = stats['abstention'].sum()
    
    if total_census > 0:
        global_abstention_rate = (total_abstention / total_census) * 100
    else:
        global_abstention_rate = 0.0

    print("-" * 40)
    print(f"GLOBAL ABSTENTION TOTAL: {int(total_abstention):,}")
    print(f"GLOBAL ABSTENTION RATE:  {global_abstention_rate:.2f}%")
    print("="*40)

    # 5. Print parties with at least one seat
    print("\n" + "="*40)
    print("       ELECTION RESULTS (Seats Won)")
    print("="*40)
    # Aggregate total seats by party and order the results
    total_seats_by_party = results_df.groupby('party')['seats'].sum().reset_index()
    total_seats_by_party = total_seats_by_party[total_seats_by_party['seats'] > 0]
    total_seats_by_party = total_seats_by_party.sort_values(by='seats', ascending=False)

    print(f"{'PARTY':<20} | {'TOTAL SEATS':<10}")
    print("-" * 32)
    for _, row in total_seats_by_party.iterrows():
        print(f"{row['party']:<20} | {row['seats']:<10}")

if __name__ == "__main__":
    import sys

    sys_args_len = 3  # script name + 3 arguments

    if len(sys.argv) != sys_args_len and len(sys.argv) != 1:
        raise ValueError(f"Expected {sys_args_len - 1} arguments (input_csv, output_seats_csv), got {len(sys.argv) - 1}")
    
    if len(sys.argv) == sys_args_len:
        in_filepath = sys.argv[1]
        out_filepath = sys.argv[2]
    else:
        in_filepath = "demographics_data/clean/spa_2019-a.csv"
        out_filepath = "demographics_data/simulation_results/spa_2019-a_results.csv"


    simulate_election(
        input_csv=in_filepath,
        output_seats_csv=out_filepath,
    )
    
