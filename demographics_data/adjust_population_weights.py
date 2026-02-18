import pandas as pd

# Multipliers for provinces based on population proportions (in thousands)
province_multipliers = {
    'catalunya': 7500000,
    'barcelona': 4850000,
    'girona': 600000,
    'lleida': 380000,
    'tarragona': 670000,
}

def adjust_population(df):
    def adjust_weights(row):
        province = row['province'].lower()
        multiplier = province_multipliers.get(province, 1)
        # Normalize the values (excluding 'province')
        values = [row[idx] for idx in row.index[1:]]
        total = sum(values)
        if total == 0:
            normalized = [0 for _ in values]
        else:
            normalized = [v / total for v in values]
        # Multiply by multiplier, round, and convert back to float
        for i, idx in enumerate(row.index[1:]):
            result = round(normalized[i] * multiplier, 3)
            row[idx] = result
        return row

    df = df.apply(adjust_weights, axis=1)
    return df

if __name__ == "__main__":
    input_path = "demographics_data/clean/population_weights_2012.csv"
    output_path = "demographics_data/clean/ok_population_weights_2012.csv"

    df = pd.read_csv(input_path)
    adjusted_df = adjust_population(df)
    adjusted_df.to_csv(output_path, index=False)
    print(f"Adjusted population weights saved to {output_path}")