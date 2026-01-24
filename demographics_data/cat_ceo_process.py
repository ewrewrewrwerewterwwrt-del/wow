#!/usr/bin/env python3
"""
Process CEO data to classify respondents by socioeconomic status, province, and vote intention.
Note: The CEO is a bit bad in terms of actually depicting the results of the 2012 election, specially when looking only at untreated data.
but it's still useful + it's the only source that has this level of detail.
Tweaks have been made to ensure the simulation actually produces the correct results.
"""

import pandas as pd
import numpy as np
import math
import matplotlib.pyplot as plt

def load_ceo_data(filepath):
    """Load and preprocess the CEO data"""
    try:
        df = pd.read_csv(filepath)
        return df
    except Exception as e:
        df = pd.read_csv(filepath, delimiter=';')
        return df


def classify_socioeconomic(df, current_year):
    """Classify respondents into socioeconomic categories"""
    
    # Rural/Urban classification (HABITAT)
    def classify_habitat(habitat):
        if pd.isna(habitat):
            return 'middle'  # default
        if '<2.000' in str(habitat) or 'De 2.001 a 10.000' in str(habitat) or '2.001-10.000' in str(habitat) or str(habitat).strip() == '1' or str(habitat).strip() == '2': # 2017 data again being an ass
            return 'rural'
        elif 'De 10.001 a 50.000' in str(habitat):
            return 'middle' 
        else:
            return 'middle'  # urban areas - we'll separate industrial later
    
    habitat_class = df['HABITAT'].apply(classify_habitat)
    
    # Employment-based classification (C400)
    def classify_employment(emp_status, education, age):
        if pd.isna(emp_status):
            return 'middle'
        
        emp_str = str(emp_status).lower()

        # Retired
        if 'jubilat' in emp_str or 'retired' in emp_str or age >= 65:
            return 'retired'

        # Unemployed
        if 'atur' in emp_str or 'no treballa' in emp_str:
            return 'unemployed'      
        
        # Self-employed/Business owners
        if 'compte propi' in emp_str or 'autònom' in emp_str or 'empresari' in emp_str:
            return 'buss'
        
        # Industrial workers (working class w/o university/high bachelor)
        if ('treballa' in emp_str and 
            (pd.isna(education) or 'ESO' in str(education) or 'EGB' in str(education) or 'FP' in str(education)) and not ('Universitari' in str(education) or 'Diplomatura' in str(education) or 'Llicenciat' in str(education) or 'Grau' in str(education))):
            return 'ind'
        
        # Default to middle class
        return 'middle'
    
    edat_column_name = "EDAT" if "EDAT" in df.columns else "edat" # Handle case sensitivity


    # One wishes for consistency...
    if current_year == 2012:    
        socio_class = df.apply(lambda row: classify_employment(
            row.get('C400'), row.get('C500'), row.get(edat_column_name, 0)
        ), axis=1)

    elif current_year == 2015:
        def combine_employment(row):
            c401 = str(row.get('C401', '')).strip()
            c401b = str(row.get('C401B', '')).strip()
            combined = f"{c401} - {c401b}".strip()
            return combined

        df['combined_employment'] = df.apply(combine_employment, axis=1)

        # save to temp for inspection
        temp_path = 'demographics_data/.temp/temp_combined_employment_2015.csv'
        df[['combined_employment']].to_csv(temp_path, index=False)

        socio_class = df.apply(lambda row: classify_employment(
            row.get('combined_employment'), row.get('C500'), row.get(edat_column_name, 0)
        ), axis=1)
    
    elif current_year == 2017:
        # The 2017 is the most cryptic of all, all with fuckass weird codes.
        def employment_2017(row):
            c401 = str(row.get('C401', '0')).strip()
            if c401 == '2':
                return 'atur'
            c401a = str(row.get('C401A', '0')).strip()
            if c401a == '1' or c401a == '3':
                return 'jubilat'
            elif c401a == '2' or c401a == '4':
                return 'atur'
            
            c401b = str(row.get('C401B', '0')).strip()
            if c401b == '1' or c401b == '2':
                return 'compte propi'
            return 'treballa'
        
        def education_2017(row):
            c500 = str(row.get('C500', '')).strip()
            # These distinctions then get further simplified, but at least we have some idea while debugging
            if c500 in ['1', '2', '3', '4', '5']:
                return 'ESO'
            elif c500 in ['6', '7']:
                return 'FP'
            elif c500 in ['8', '9', '10', '11']:
                return 'Universitari'
            return None
        
        socio_class = df.apply(lambda row: classify_employment(
            employment_2017(row), education_2017(row), row.get(edat_column_name, 0)
        ), axis=1)

    else:
        raise ValueError("Unsupported analysis year for socioeconomic classification.")

    
    # Override with habitat for rural
    socio_class = np.where(habitat_class == 'rural', 'rural', socio_class)
    
    # Override with age for clear age groups
    socio_class = np.where((df[edat_column_name] >= 65), 'retired', socio_class)
    socio_class = np.where((df[edat_column_name] <= 30), 'young', socio_class)

    return pd.Series(socio_class, index=df.index)

def classify_provinces(df):
    """Map provinces to standard names"""
    province_map = {
        'Barcelona': 'barcelona',
        'Girona': 'girona', 
        'Lleida': 'lleida',
        'Tarragona': 'tarragona',
        8: 'barcelona',
        17: 'girona',
        25: 'lleida',
        43: 'tarragona',
    }
    return df['PROVI'].map(province_map)

def extract_vote_intention(df, analysis_year):
    # Map party codes to our standardized names (all lowercase, stripped)
    party_map = {
        'abstain': 'abstain',
        'abstenció': 'abstain',
        'na': 'abstain',
        'no sap/no contesta': 'abstain',
        'no sap': 'abstain',
        'no contesta': 'abstain',
        'ciu': 'ciu',
        'convergència i unió': 'ciu',
        'convergencia i unio': 'ciu',
        'erc': 'erc',
        'psc': 'psc',
        'ppc': 'ppc',
        'pp': 'ppc',
        'icv-euia': 'icv',
        'icv': 'icv',
        "c's": 'cs',
        'cs': 'cs',
        'ciutadans': 'cs',
        'cup': 'cup',
        "candidatura d'unitat popular": 'cup',                
        'vox': 'vox',
        'solidaritat catalana': 'si',
        'solidaritat per la independència': 'si',
        'solidaritat': 'si',
        'aliança catalana': 'ac',
        'ac': 'ac',
        'pxc': 'ac', # for simplicity's sake
    }

    if analysis_year == 2015:
        ## add all the chaos
        party_map.update({
            'ciu': 'jxsi',
            'convergència i unió': 'jxsi',
            'convergencia i unio': 'jxsi',
            'junts': 'jxsi',
            'junts pel sí': 'jxsi',
            'junts pel si': 'jxsi',
            'cdc': 'jxsi',
            'convergents': 'jxsi',
            'erc': 'jxsi',
            'icv-euia': 'csqp',
            'icv': 'csqp',
            'csqp': 'csqp',
            'catalunya si que es pot': 'csqp',
            'catalunya sí que es pot': 'csqp',
            'podemos': 'csqp',
            'podem': 'csqp',
            'unió': 'unio',
            'unio': 'unio',
        })

    if analysis_year == 2017:
        party_map.update({
            '1': 'ppc',
            '2': 'jxcat',
            '3': 'erc',
            '4': 'psc',
            '5': 'icv',
            '6': 'cs',
            '8': 'si',
            '9': 'ac',
            '10': 'cup',
            '12': 'cecp',
            '13': 'cecp',
            '14': 'jxcat',
            '15': 'jxcat', # this answer is jxsi but by bundling it with jxcat we actually get closer to the real results
            '16': 'cecp',
            '17': 'jxcat',
            '18': 'cecp',
            '20': 'jxcat',
        })

    def normalize_party(val):
        if pd.isna(val):
            return None
        val = str(val).strip().lower()
        return party_map.get(val)

    if analysis_year == 2015:
        column_1 = 'P38B'
        column_2 = 'P37'
        column_3 = 'P24'
    elif analysis_year == 2017:
        column_1 = 'P37'
        column_2 = 'P37_LITERALS' 
        column_3 = 'P38B'
    else:
        column_1 = 'P21'
        column_2 = 'P32'
        column_3 = None

    vote_intention = df[column_1].apply(normalize_party) # 2015: Who did you vote for in Sept? 2012: Who are you going to vote for in November?

    # Save the relevant columns to a temporary CSV for inspection
    temp_path = 'demographics_data/.temp/temp_vote_intention.csv'
    if column_3 is None:
        temp_cols = df[[column_1, column_2]].copy()
    else:
        temp_cols = df[[column_1, column_2, column_3]].copy()
    temp_cols.to_csv(temp_path, index=False)
    
    # By order, we fill in missing values from the next "most relevant" columns
    if column_2 in df.columns:
        vote_recall = df[column_2].apply(normalize_party) # Direct vote intention
        vote_intention = vote_intention.fillna(vote_recall)
    if column_3 is not None and column_3 in df.columns:
        vote_other = df[column_3].apply(normalize_party) # Most sympathetic party
        vote_intention = vote_intention.fillna(vote_other)
    

    # If not found, assume abstention
    vote_intention = vote_intention.fillna('abstain')

    # Also return the set of standardized party names
    standardized_parties = set(party_map.values())
    return vote_intention, standardized_parties

def create_demographic_groups(df, analysis_year):
    """Create the full demographic classification"""
    
    # Get classifications
    socio_econ = classify_socioeconomic(df, analysis_year)
    provinces = classify_provinces(df)
    vote_intention, standardized_parties = extract_vote_intention(df, analysis_year)

    # Create results DataFrame
    results = pd.DataFrame({
        'province': provinces,
        'demographic_group': socio_econ,
        'vote_intention': vote_intention
    })

    return results, standardized_parties

def create_province_class_party_breakdown(results_df, standardized_parties):
    """
    Create a breakdown DataFrame with columns:
    province, demographic_group, sample_size, party, percentage
    Ensures all parties are present for each group, even if zero respondents.
    """

    clean_df = results_df.dropna(subset=['province', 'demographic_group', 'vote_intention'])
    rows = []
    provinces = ['barcelona', 'girona', 'lleida', 'tarragona']

    for province in provinces:
        province_data = clean_df[clean_df['province'] == province]
        if province_data.empty:
            continue

        demo_groups = province_data['demographic_group'].unique()
        for group in sorted(demo_groups):
            group_data = province_data[province_data['demographic_group'] == group]
            if group_data.empty:
                continue

            total_in_group = len(group_data)
            party_counts = group_data['vote_intention'].value_counts()
            party_percentages = (party_counts / total_in_group * 100).round(1)
            for party in standardized_parties:
                pct = party_percentages.get(party, 0.0)
                rows.append({
                    'province': province,
                    'demographic_group': group,
                    'sample_size': total_in_group,
                    'party': party,
                    'percentage': pct
                })

    breakdown_df = pd.DataFrame(rows)
    return breakdown_df

def print_province_class_party_breakdown(breakdown_df):
    """Print the province-class-party breakdown DataFrame in a readable format."""
    print("\n" + "="*60)
    print("PROVINCE-CLASS-PARTY SUPPORT BREAKDOWN")
    print("="*60)

    if breakdown_df.empty:
        print("No data available.")
        return

    for province in breakdown_df['province'].unique():
        print(f"\n{province.upper()}:")
        print("-" * 20)
        province_df = breakdown_df[breakdown_df['province'] == province]
        for demo_class in province_df['demographic_group'].unique():
            group_df = province_df[province_df['demographic_group'] == demo_class]
            sample_size = group_df['sample_size'].iloc[0]
            print(f"  {demo_class} (n={sample_size}):")
            # Sort parties by percentage descending
            sorted_parties = group_df.sort_values('percentage', ascending=False)
            party_strs = [
                f"{row['party']}: {row['percentage']:.1f}%"
                for _, row in sorted_parties.iterrows()
            ]
            print(f"    [{', '.join(party_strs)}]")

    print("\n" + "="*60)

def visualize_results(province_breakdown):
    """Visualize the results using bar charts with party color codes, from a DataFrame."""
    party_colors = {
        'ciu': '#002782',
        'cdc': '#002782',
        'unio': '#0052a3',
        'erc': '#ff8000',
        'cup': '#ffed00',
        'jxsi': '#3ab6a5',
        'jxcat': '#ed5975',
        'pdcat': '#0081c2',
        'junts': '#20c0b2',
        'cs': '#f6c300',
        'ppc': '#007fff',
        'pp': '#007fff',
        'psc': '#e73b39',
        'icv': '#67af2f',
        'si': '#000000',
        'csqp': '#c3113b',
        'cecp': '#be3882',
        'ecp': '#6e236e',
        'vox': '#63be21',
        'ac': '#064a81',
        'abstain': '#a0a0a0',
    }

    provinces = province_breakdown['province'].unique()
    for province in provinces:
        prov_df = province_breakdown[province_breakdown['province'] == province]
        demo_groups = prov_df['demographic_group'].unique()
        num_classes = len(demo_groups)
        ncols = 2
        nrows = math.ceil((num_classes + 1) / ncols)
        fig, axes = plt.subplots(nrows, ncols, figsize=(14, 5 * nrows), squeeze=False)
        fig.suptitle(f'Vote Intention by Demographic Group in {province.capitalize()}', fontsize=16)

        # Plot each demographic group
        for idx, demo_class in enumerate(sorted(demo_groups)):
            row, col = divmod(idx, ncols)
            ax = axes[row][col]
            group_df = prov_df[prov_df['demographic_group'] == demo_class]
            parties = group_df.sort_values('percentage', ascending=False)
            party_names = parties['party']
            percentages = parties['percentage']
            colors = [party_colors.get(p, 'skyblue') for p in party_names]
            ax.bar(party_names, percentages, color=colors)
            sample_size = group_df['sample_size'].iloc[0] if not group_df.empty else 0
            ax.set_title(f'{demo_class} (n={sample_size})')
            ax.set_xlabel('Political Parties')
            ax.set_ylabel('Percentage (%)')
            ax.set_ylim(0, 100)
            ax.set_xticklabels(party_names, rotation=45)
            ax.grid(axis='y')

        # Add totals plot for the province
        idx = num_classes
        row, col = divmod(idx, ncols)
        ax = axes[row][col]
        # Aggregate all party votes across all groups
        total_counts = prov_df.groupby('party').apply(lambda x: np.sum(x['percentage'] * x['sample_size'] / 100)).to_dict()
        total_n = prov_df['sample_size'].sum()
        if total_n > 0 and total_counts:
            total_percentages = {party: (count / total_n * 100) for party, count in total_counts.items()}
            sorted_totals = sorted(total_percentages.items(), key=lambda x: x[1], reverse=True)
            party_names, percentages = zip(*sorted_totals)
            colors = [party_colors.get(p, 'skyblue') for p in party_names]
            ax.bar(party_names, percentages, color=colors)
            ax.set_title(f'Total ({total_n} respondents)')
            ax.set_xlabel('Political Parties')
            ax.set_ylabel('Percentage (%)')
            ax.set_ylim(0, 100)
            ax.set_xticklabels(party_names, rotation=45)
            ax.grid(axis='y')
        else:
            ax.axis('off')

        # Hide any unused subplots
        for idx in range(num_classes + 1, nrows * ncols):
            row, col = divmod(idx, ncols)
            axes[row][col].axis('off')

        plt.tight_layout(rect=(0, 0.03, 1, 0.95))
    plt.show()
    

def main(csv_filepath, out_filepath, analysis_year, visuals=False):
    """Main function to process CEO 2012/2015 data"""
    
    print("Loading CEO data...")
    df = load_ceo_data(csv_filepath)

    print(f"Loaded {len(df)} respondents")
    
    print("\nClassifying demographic groups...")
    results, standardized_parties = create_demographic_groups(df, analysis_year)
    
    print("\nCreating Province-Class-Party breakdown...")
    province_breakdown = create_province_class_party_breakdown(results, standardized_parties)

    # Print the breakdown
    print_province_class_party_breakdown(province_breakdown)
    
    # Also save the data by province-class-party to a CSV for further analysis
    province_breakdown.to_csv(out_filepath, index=False)
    print(f"\nSaved province-class-party breakdown to {out_filepath}")

    # Visualize results (pass DataFrame)
    if visuals:
        visualize_results(province_breakdown)
    
    return results, province_breakdown


if __name__ == "__main__":
    import sys
    import os

    sys_args_len = 4  # script name + 3 arguments

    if len(sys.argv) != sys_args_len and len(sys.argv) != 1:
        raise ValueError("Please provide both input CSV file path and output CSV file path as arguments.")

    if len(sys.argv) == sys_args_len:
        csv_file = sys.argv[1]
        out_filepath = sys.argv[2]
        analysis_year = sys.argv[3]
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        csv_file = os.path.join(script_dir, 'ceo_raw', 'cat_data_2017.csv') # For 2015 use _2 since its post-election!
        out_filepath = os.path.join(script_dir, 'clean', 'vote_intention_2017.csv')
        analysis_year = 2017

    results, breakdown = main(csv_file, out_filepath, analysis_year)