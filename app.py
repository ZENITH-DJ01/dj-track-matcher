import io
import re
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st

st.set_page_config(page_title="DJ Track Matcher", page_icon="🎛️", layout="wide")

# ---------- Roue de Camelot ----------
CLASSIQUE_VERS_CAMELOT = {
    "Abm": "1A", "B": "1B", "Ebm": "2A", "F#": "2B", "Bbm": "3A", "Db": "3B",
    "Fm": "4A", "Ab": "4B", "Cm": "5A", "Eb": "5B", "Gm": "6A", "Bb": "6B",
    "Dm": "7A", "F": "7B", "Am": "8A", "C": "8B", "Em": "9A", "G": "9B",
    "Bm": "10A", "D": "10B", "F#m": "11A", "A": "11B", "Dbm": "12A", "E": "12B",
}
ENHARMONIQUES = {"G#m": "Abm", "D#m": "Ebm", "A#m": "Bbm", "C#m": "Dbm", "Gbm": "F#m",
                 "Gb": "F#", "C#": "Db", "G#": "Ab", "D#": "Eb", "A#": "Bb"}


def vers_camelot(k):
    k = str(k).strip()
    m = re.fullmatch(r"(\d{1,2})([ABab])", k)
    if m:
        return int(m.group(1)), m.group(2).upper()
    code = CLASSIQUE_VERS_CAMELOT.get(ENHARMONIQUES.get(k, k))
    return (int(code[:-1]), code[-1]) if code else None


# ---------- Scores (None = donnée absente : le critère est ignoré) ----------
def score_tonalite(k1, k2):
    a, b = vers_camelot(k1), vers_camelot(k2)
    if not a or not b:
        return None
    diff = min(abs(a[0] - b[0]), 12 - abs(a[0] - b[0]))
    if diff == 0:
        return 1.0 if a[1] == b[1] else 0.9
    if diff == 1 and a[1] == b[1]:
        return 0.85
    if diff == 2 and a[1] == b[1]:
        return 0.6
    return 0.1


def score_bpm(b1, b2):
    if pd.isna(b1) or pd.isna(b2) or not b1 or not b2:
        return None
    pct = min(abs(b1 - b2), abs(b1 - b2 * 2), abs(b1 - b2 / 2)) / b1 * 100
    return 1.0 if pct <= 2 else 0.8 if pct <= 5 else 0.5 if pct <= 8 else 0.0


def mots(txt):
    return set(re.findall(r"[a-zà-ÿ0-9]{3,}", str(txt).lower()))


def score_texte(t1, t2):
    s1, s2 = mots(t1), mots(t2)
    if not s1 or not s2:
        return None
    return len(s1 & s2) / len(s1 | s2)


def score_annee(y1, y2):
    if pd.isna(y1) or pd.isna(y2):
        return None
    return max(0.0, 1 - abs(y1 - y2) / 15)


# ---------- Chargement ----------
COLONNES = ["Titre", "Artiste", "BPM", "Tonalite", "Genre", "Style", "Ambiance", "Annee"]
ALIAS = {
    "Titre": ["titre", "track title", "title", "name", "nom", "nom du morceau"],
    "Artiste": ["artiste", "artist"],
    "BPM": ["bpm"],
    "Tonalite": ["tonalite", "tonalité", "key", "tonality"],
    "Genre": ["genre"],
    "Style": ["style", "grouping", "label"],
    "Ambiance": ["ambiance", "comments", "commentaires", "commentaire", "mood"],
    "Annee": ["annee", "année", "year"],
}


def charger_xml(f):
    racine = ET.parse(f).getroot()
    lignes = []
    for t in racine.iterfind(".//COLLECTION/TRACK"):
        lignes.append({
            "Titre": t.get("Name", ""), "Artiste": t.get("Artist", ""),
            "BPM": t.get("AverageBpm", ""), "Tonalite": t.get("Tonality", ""),
            "Genre": t.get("Genre", ""),
            "Style": " ".join(x for x in (t.get("Grouping"), t.get("Label")) if x),
            "Ambiance": t.get("Comments", ""), "Annee": t.get("Year", ""),
        })
    return pd.DataFrame(lignes)


def charger_csv(f):
    brut = f.getvalue()
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(brut), sep=None, engine="python", encoding=enc)
            break
        except Exception:
            continue
    else:
        raise ValueError("CSV illisible")
    bas = {str(c).strip().lower(): c for c in df.columns}
    renom = {}
    for cible, alias in ALIAS.items():
        for a in alias:
            if a in bas:
                renom[bas[a]] = cible
                break
    return df.rename(columns=renom)


def preparer(df):
    for c in COLONNES:
        if c not in df.columns:
            df[c] = ""
    df = df[COLONNES].copy()
    df["BPM"] = pd.to_numeric(df["BPM"], errors="coerce")
    df["Annee"] = pd.to_numeric(df["Annee"], errors="coerce")
    for c in ("Titre", "Artiste", "Tonalite", "Genre", "Style", "Ambiance"):
        df[c] = df[c].fillna("").astype(str)
    df = df[df["Titre"] != ""].reset_index(drop=True)
    bpm_txt = df["BPM"].round().astype("Int64").astype(str).replace("<NA>", "?")
    df["Display"] = df["Artiste"] + " - " + df["Titre"] + " (" + bpm_txt + " BPM | " + df["Tonalite"] + ")"
    return df


# ---------- Interface ----------
st.title("🎛️ DJ Smart Track Matcher")
st.markdown("Trouve la transition idéale selon le **BPM**, la **tonalité**, l'**ambiance**, le **genre** et l'**époque**.")

with st.sidebar:
    st.header("1. Ta bibliothèque")
    fichier = st.file_uploader("Export Rekordbox (XML recommandé, ou CSV)", type=["xml", "csv"])
    st.divider()
    st.header("2. Poids des critères")
    w_bpm = st.slider("Importance BPM", 0.0, 5.0, 3.0, 0.5)
    w_key = st.slider("Importance Tonalité (Camelot)", 0.0, 5.0, 3.0, 0.5)
    w_vibe = st.slider("Importance Ambiance / Commentaires", 0.0, 5.0, 2.5, 0.5)
    w_genre = st.slider("Importance Genre & Style", 0.0, 5.0, 2.0, 0.5)
    w_year = st.slider("Importance Période / Année", 0.0, 5.0, 1.0, 0.5)
    w_artist = st.slider("Bonus / Malus même artiste", -2.0, 2.0, -0.5, 0.5)

if fichier is not None:
    try:
        brut = charger_xml(fichier) if fichier.name.lower().endswith(".xml") else charger_csv(fichier)
        df = preparer(brut)
    except Exception as e:
        st.error(f"Impossible de lire ce fichier : {e}")
        st.stop()
    if df.empty:
        st.error("Aucun morceau trouvé dans ce fichier.")
        st.stop()
else:
    st.info("💡 Mode démo. Importe l'export XML de ta collection Rekordbox (Fichier > Exporter la collection au format xml).")
    df = preparer(pd.DataFrame({
        "Titre": ["Losing It", "Pjanoo", "Opus", "Baddadan", "Midnight City", "One More Time", "Talamanca", "Rumble"],
        "Artiste": ["Fisher", "Eric Prydz", "Eric Prydz", "Chase & Status", "M83", "Daft Punk", "Burns", "Skrillex & Fred again.."],
        "BPM": [125, 126, 126, 174, 105, 123, 126, 140],
        "Tonalite": ["8A", "8A", "9A", "5A", "11B", "10B", "8B", "4A"],
        "Genre": ["Tech House", "Progressive House", "Melodic Techno", "Drum & Bass", "Synthpop", "French House", "Piano House", "Dubstep / UKG"],
        "Style": ["Club, Peak Time", "Euphoric, Classic", "Hypnotic, Build-up", "Heavy, Roller", "80s, Nostalgic", "Disco, Filter", "Vocal, Summer", "Bass, Dark"],
        "Ambiance": ["Haute énergie", "Festive", "Progressive", "Intense", "Planante", "Festive", "Chaleureuse", "Sombre"],
        "Annee": [2018, 2008, 2015, 2023, 2011, 2000, 2021, 2023],
    }))

with st.expander("Données lues dans ton fichier"):
    st.write(f"{len(df)} morceaux · BPM : {int(df['BPM'].notna().sum())} · tonalité : "
             f"{sum(vers_camelot(k) is not None for k in df['Tonalite'])} · genre : {int((df['Genre'] != '').sum())} · "
             f"commentaires : {int((df['Ambiance'] != '').sum())} · année : {int(df['Annee'].notna().sum())}")
    st.caption("Un critère à 0 est ignoré dans le calcul au lieu de fausser le score.")

fmt = lambda i: df.at[i, "Display"]
courant_idx = st.selectbox("🎧 Morceau en cours de lecture :", df.index, format_func=fmt)
deja_joues = st.multiselect("Déjà joués dans ce set (exclus des suggestions) :", df.index, format_func=fmt)
cur = df.loc[courant_idx]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("BPM", "?" if pd.isna(cur["BPM"]) else round(cur["BPM"]))
c2.metric("Tonalité", cur["Tonalite"] or "?")
c3.metric("Genre", cur["Genre"] or "?")
c4.metric("Ambiance", cur["Ambiance"][:25] or "?")
c5.metric("Année", "?" if pd.isna(cur["Annee"]) else int(cur["Annee"]))
st.divider()

resultats = []
for i, row in df.iterrows():
    if i == courant_idx or i in deja_joues:
        continue
    criteres = [
        (w_bpm, score_bpm(cur["BPM"], row["BPM"])),
        (w_key, score_tonalite(cur["Tonalite"], row["Tonalite"])),
        (w_vibe, score_texte(cur["Ambiance"], row["Ambiance"])),
        (w_genre, score_texte(cur["Genre"] + " " + cur["Style"], row["Genre"] + " " + row["Style"])),
        (w_year, score_annee(cur["Annee"], row["Annee"])),
    ]
    dispo = [(w, s) for w, s in criteres if s is not None and w > 0]
    total = sum(w for w, _ in dispo)
    base = sum(w * s for w, s in dispo) / total if total else 0.0
    if cur["Artiste"] and cur["Artiste"].lower() == row["Artiste"].lower():
        base += w_artist / 10
    resultats.append({
        "Match %": max(0, min(100, int(base * 100))),
        "Artiste": row["Artiste"], "Titre": row["Titre"],
        "BPM": None if pd.isna(row["BPM"]) else round(row["BPM"]),
        "Tonalité": row["Tonalite"], "Genre": row["Genre"],
        "Style": row["Style"], "Ambiance": row["Ambiance"],
        "Année": None if pd.isna(row["Annee"]) else int(row["Annee"]),
    })

res = pd.DataFrame(resultats).sort_values("Match %", ascending=False).head(30)
st.subheader("🔥 Meilleurs morceaux pour la suite :")
st.dataframe(
    res, use_container_width=True, hide_index=True,
    column_config={"Match %": st.column_config.ProgressColumn(
        "Compatibilité", format="%d%%", min_value=0, max_value=100)},
)
