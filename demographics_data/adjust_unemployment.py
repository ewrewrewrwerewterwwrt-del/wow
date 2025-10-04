

import pandas as pd
import argparse

def adjust_unemployment(csv_path, output_path, real_unemployment):
    df = pd.read_csv(csv_path)
    provinces = df['province'].unique()
    # For each province, calculate current unemployment %
    for province in provinces:
        row = df[df['province'] == province].iloc[0]
        unemployed = row['unemployed']
        middle = row['middle']
        ind = row['ind']
        buss = row['buss']
        total = unemployed + middle + ind + buss
        current_pct = unemployed / total * 100 if total > 0 else 0
        real_pct = real_unemployment.get(province, None)
        print(f"{province}: current {current_pct:.2f}%, real {real_pct:.2f}%")
        if real_pct is not None and abs(current_pct - real_pct) > 0.01:
            new_unemployed = total * real_pct / 100
            scale = (total - new_unemployed) / (middle + ind + buss) if (middle + ind + buss) > 0 else 1
            # Update values
            df.loc[df['province'] == province, 'unemployed'] = new_unemployed
            df.loc[df['province'] == province, 'middle'] = middle * scale
            df.loc[df['province'] == province, 'ind'] = ind * scale
            df.loc[df['province'] == province, 'buss'] = buss * scale
            print(f"Adjusted {province}: unemployed={new_unemployed:.2f}, scale others by {scale:.4f}")
    df.to_csv(output_path, index=False)
    print(f"Adjusted data saved to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adjust unemployment percentages in a CSV file.")
    parser.add_argument(
        "input_file",
        nargs="?",
        default="demographics_data/clean/ok_population_weights_2012.csv",
        help="Path to input CSV file"
    )
    parser.add_argument(
        "output_file",
        nargs="?",
        default="demographics_data/clean/ok_population_weights_2018.csv",
        help="Path to output CSV file"
    )
    parser.add_argument(
        "adjustment_year",
        nargs="?",
        default="2018",
        help="Adjustment year"
    )
    args = parser.parse_args()
    
    if args.adjustment_year == "2015":
        real_unemployment = {
            'Catalunya': 18.6,
            'Barcelona': 18.2,
            'Girona': 21.6,
            'Lleida': 15.0,
            'Tarragona': 21.9,
        }
    elif args.adjustment_year == "2018":
        real_unemployment = {
            'Catalunya': 11.5,
            'Barcelona': 11.1,
            'Girona': 11.4,
            'Lleida': 10.6,
            'Tarragona': 15.0,
        }
    else:
        raise NotImplementedError("Adjustment year not supported")

    adjust_unemployment(
        csv_path=args.input_file,
        output_path=args.output_file,
        real_unemployment=real_unemployment
    )

