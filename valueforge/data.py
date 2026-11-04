from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def load_companies():
    path=ROOT/"data"/"companies.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()
def load_sample_data():
    path=ROOT/"data"/"sample_companies.csv"
    if not path.exists(): return pd.DataFrame()
    df=pd.read_csv(path); df["data_status"]="ILLUSTRATIVE_ONLY"; return df
