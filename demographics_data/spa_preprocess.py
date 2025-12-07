import os
import xml.etree.ElementTree as ET
import pandas as pd
import sys

# Define valid parties per region to filter out noise/small parties immediately
VALID_PARTIES_BY_REGION = {
    "catalunya": ["ciu", "psoe", "erc", "pp", "cs", "podemos", "iu", "cup", "fr", "dl", "pdcat", "jxsi", "cdc", "unio", "junts", "upyd", "vox", "mpais", "up", "sumar", "jxcat"],
    "valencia": ["pp", "psoe", "podemos", "cs", "iu", "compromis", "vox", "up", "sumar", "upyd", "mpais"],
    "balears": ["pp", "psoe", "podemos", "cs", "iu", "vox", "up", "sumar", "upyd", "mpais", "mes"],
    "navarra": ["pp", "psoe", "podemos", "cs", "iu", "vox", "up", "sumar", "upyd", "mpais", "amaiur", "nsuma", "ehbildu", "upn", "gbai"],
    "euskadi": ["pp", "psoe", "podemos", "cs", "iu", "vox", "up", "sumar", "upyd", "mpais", "ehbildu", "pnv", "amaiur"],
    "galicia": ["pp", "psoe", "podemos", "cs", "iu", "vox", "up", "sumar", "upyd", "mpais", "bng", "nos"],
    "rest": ["pp", "psoe", "podemos", "cs", "iu", "vox", "up", "sumar", "upyd", "mpais", "cc", "fac", "prc", "te" ]
}

def normalize_party_name(raw_name, year):
    """
    Cleans and maps raw XML party names to the target standard list.
    Returns 'other' if the party isn't in our explicit mapping.
    """

    party_mapping = {
        # PP and allies
        "pp": "pp",
        "partido popular": "pp",
        "pp-par": "pp",
        "upn-pp": "pp",
        
        # PSOE and allies
        "psoe": "psoe",
        "partido socialista obrero español": "psoe",
        "psc": "psoe",
        "psc-psoe": "psoe",
        "psoe-nc": "psoe",
        "pse-ee": "psoe",
        "psdeg-psoe": "psoe",
        
        # Podemos / Sumar / IU / Left Coalitions - These get updated by the year since stuff changes
        "podemos": "up",
        "unidos podemos": "up",
        "unidospodemos": "up",
        "en comú podem": "up", 
        "en comú": "up",
        "en marea": "up", 
        "iu": "iu",
        "izquierda unida": "up",
        "eupv": "up",
        "euiai": "up",
        "ecp": "up",
        "unidad popular": "up",
        "ahora madrid": "up",
        "mas pais": "mpais",
        "más país": "mpais",
        "sumar": "sumar",
        
        # Ciudadanos
        "c's": "cs",
        "cs": "cs",
        "ciudadanos": "cs",
        
        # Catalan
        "erc": "erc",
        "esquerra republicana": "erc",
        "cdc": "cdc",
        "dl": "dl",
        "di l": "dl", # Democracia i Llibertat
        "democracia i llibertat": "dl",
        "jxcat-junts": "jxcat",
        "junts": "junts",
        "jxcat": "jxcat",
        "junts per catalunya": "jxcat",
        "cup": "cup",
        "unio": "unio",
        "front": "fr",
        "front republica": "fr",
        "front republicà": "fr",
        "unio.cat": "unio",
        "pdcat": "pdcat",
        "pdecat": "pdcat",
        
        # Basque
        "pnv": "pnv",
        "eaj-pnv": "pnv",
        "eh bildu": "ehbildu",
        "ehbildu": "ehbildu",
        "bildu": "ehbildu",
        "amaiur": "amaiur",
        
        # Valencian and Balearic
        "a la valenciana": "up",
        "compromís-podemos-eupv": "up",
        "compromís": "up",
        "MÉS COMPROM": "compromis",
        "mes": "mes",
        "més": "mes",

        # Navarrese
        "upn": "upn",
        "gbai": "gbai",
        "nsuma": "nsuma",
        "na+": "nsuma",

        # Galician
        "bng": "bng",
        "nos": "nos",
        "nós": "nos",
        
        # Others
        "vox": "vox",
        "upyd": "upyd",
        "cc": "cc", 
        "cc-pnc": "cc",
        "te": "te",
        "¡te!": "te",
        "teruel existe": "te",
        "¡teruel existe!": "te",
        "fac": "fac",
        "prc": "prc"
    }

    if year == "2015":
        party_mapping.update({
            "unidad popular en común": "iu",
            "podemos": "podemos",
            "en comú podem": "podemos", 
            "en comú": "podemos",
            "en marea": "podemos", 
            "iu": "iu",
            "iu-upec": "iu",
            "izquierda unida": "iu",
            "eupv": "iu",
            "euiai": "iu",
            "unidad popular": "iu",
        })
    
    if year == "2019-a":
        party_mapping.update({
            "compromis": "compromis",
            "compromís": "compromis",
            "bloc": "compromis",
            "idpv": "compromis",
            "verdsequo": "compromis",
            "ara-mes-esquerra": "mes",
        })

    if year == "2019-n":
        party_mapping.update({
            "compromis": "compromis",
            "compromís": "compromis",
            "bloc": "compromis",
            "idpv": "compromis",
            "verdsequo": "compromis",
            "ara-mes-esquerra": "mes",
            "mas pais": "mpais",
            "más país": "mpais",
        })

    if not raw_name:
        return "other"
        
    # Basic cleaning
    clean_name = raw_name.lower().strip()
    
    # 1. Direct Mapping
    if clean_name in party_mapping:
        return party_mapping[clean_name]
    
    # 2. Substring matching (risky but useful for "Party X - Coalition Y")
    # Check known keys inside the string
    for key, value in party_mapping.items():
        if key in clean_name:
             # Prioritize exact matches or start/end matches if needed
             return value

    return "other" # Discard or label as 'other'

def parse_xml_file(filepath, year, constituency_override=None):
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        
        if constituency_override:
            constituency = constituency_override
        else:
            constituency = root.find('nombre_sitio').text
            
        vote_data = {}
        
        # 1. Extract Party Votes with Normalization
        for party in root.findall('.//resultados/partido'):
            raw_name = party.find('nombre').text
            votes = int(party.find('votos_numero').text)
            
            clean_name = normalize_party_name(raw_name, year)
            # Don't throw away votes, aggregate them into the clean name
            if clean_name != "other":
                vote_data[clean_name] = vote_data.get(clean_name, 0) + votes
            
        # 2. Extract Abstention
        abstention_node = root.find('.//votos/abstenciones/cantidad')
        if abstention_node is not None:
            vote_data['abstention'] = int(abstention_node.text)
            
        return constituency, vote_data
        
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return None, None

def process_election_year(year_folder, analysis_year, output_filepath):
    # Mapping filenames to your strict lowercase constituency names
    # Note: filenames might be slightly different in your system, adjust keys if needed.
    specific_regions_map = {
        'catalunya.xml': 'catalunya',
        'balears.xml': 'balears',
        'euskadi.xml': 'euskadi', 
        'galicia.xml': 'galicia',
        'navarra.xml': 'navarra',
        'valencia.xml': 'valencia'
    }
    
    if not os.path.exists(year_folder):
        print(f"Folder not found: {year_folder}")
        return None
    
    all_data = []
    specific_region_totals = {} 
    
    # 1. Process Specific Regions
    for xml_file, const_name in specific_regions_map.items():
        full_path = os.path.join(year_folder, xml_file)
        if os.path.exists(full_path):
            _, votes_dict = parse_xml_file(full_path, year=analysis_year, constituency_override=const_name)
            
            if votes_dict:
                # Get valid whitelist for this region
                valid_list = VALID_PARTIES_BY_REGION.get(const_name, [])
                
                for party, votes in votes_dict.items():
                    # Only add if it's in the whitelist or it's abstention
                    if party in valid_list or party == 'abstention':
                        all_data.append({
                            "party": party,
                            "constituency": const_name,
                            "votes": votes
                        })
                        
                        # Add to totals for subtraction (regardless of whitelist?)
                        # usually better to subtract EVERYTHING found to get accurate Rest)
                        specific_region_totals[party] = specific_region_totals.get(party, 0) + votes
                    else:
                        # If mapped but not in whitelist (e.g. PNV in Andalucia context), ignore?
                        # For subtraction logic, we MUST track it.
                        specific_region_totals[party] = specific_region_totals.get(party, 0) + votes
        else:
            print(f"Warning: {xml_file} not found")

    # 2. Process 'Rest'
    all_xml_path = os.path.join(year_folder, 'all.xml')
    if os.path.exists(all_xml_path):
        _, total_votes_dict = parse_xml_file(all_xml_path, year=analysis_year, constituency_override="rest")
        
        if total_votes_dict:
            valid_list_rest = VALID_PARTIES_BY_REGION.get("rest", [])
            
            for party, national_votes in total_votes_dict.items():
                already_counted = specific_region_totals.get(party, 0)
                rest_votes = national_votes - already_counted
                
                if rest_votes > 0:
                    # Filter for Rest whitelist
                    if party in valid_list_rest or party == 'abstention':
                        all_data.append({
                            "party": party,
                            "constituency": "rest",
                            "votes": rest_votes
                        })

    # 3. Export
    df = pd.DataFrame(all_data)    
    df.to_csv(output_filepath, index=False)
    print(f"Saved to {output_filepath}")

        
    return df


if __name__ == "__main__":
    import sys
    import os

    sys_args_len = 4  # script name + 3 arguments

    if len(sys.argv) != sys_args_len and len(sys.argv) != 1:
        raise ValueError("Please provide input folder path, output CSV file path, and analysis year as arguments.")

    if len(sys.argv) == sys_args_len:
        in_folder = sys.argv[1]
        out_filepath = sys.argv[2]
        analysis_year = sys.argv[3]
    else:
        in_folder = "demographics_data/spa_votes_raw/"
        out_filepath = "demographics_data/clean/spa_2019-a.csv"
        analysis_year = "2019-a"
    
    year_folder = os.path.join(in_folder, analysis_year)
    process_election_year(year_folder, analysis_year, out_filepath)
    
    