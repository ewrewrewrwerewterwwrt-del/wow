import pandas as pd
from decimal import Decimal, ROUND_HALF_UP

# Multipliers for provinces based on population proportions
province_multipliers = {
    'catalunya': Decimal('55'),
    'barcelona': Decimal('40.5'),
    'girona': Decimal('5.5'),
    'lleida': Decimal('3.2'),
    'tarragona': Decimal('5.5'),
}

def adjust_population(pd):
    def adjust_weights(row):
        province = row['province'].lower()
        multiplier = province_multipliers.get(province, Decimal('1'))
        # Convert values to Decimal, multiply, round, and convert back to float
        for idx in row.index[1:]:
            value = Decimal(str(row[idx]))
            result = (value * multiplier).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            row[idx] = float(result)
        return row

    pd = pd.apply(adjust_weights, axis=1)
    return pd

if __name__ == "__main__":
    input_path = "demographics_data/clean/population_weights_2012.csv"
    output_path = "demographics_data/clean/population_weights_2012.csv"

    df = pd.read_csv(input_path)
    adjusted_df = adjust_population(df)
    adjusted_df.to_csv(output_path, index=False)
    print(f"Adjusted population weights saved to {output_path}")