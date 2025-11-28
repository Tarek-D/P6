import streamlit as st
import requests
import json
import os

# ==========================================
# 1. CONFIGURATION
# ==========================================
API_URL = "http://localhost:3000/predict"
st.set_page_config(page_title="Prédiction Énergie", page_icon="⚡")

st.title("⚡ Prédiction de Consommation Énergétique")
st.markdown("Remplissez les caractéristiques du bâtiment pour estimer sa consommation.")

# ==========================================
# 2. CHARGEMENT DES LISTES DÉROULANTES
# ==========================================
def load_options(filename):
    """Charge les clés d'un fichier JSON pour les menus déroulants"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            return list(data.keys()) # On retourne juste les noms (ex: "Bureau", "Hotel")
    except FileNotFoundError:
        st.error(f"Fichier {filename} introuvable !")
        return []

# Chargement des options depuis vos fichiers JSON existants
building_types = load_options("BuildingType_label_encoding_mapping.json")
primary_types = load_options("PrimaryPropertyType_label_encoding_mapping.json")
largest_uses = load_options("LargestPropertyUseType_label_encoding_mapping.json")

# ==========================================
# 3. FORMULAIRE
# ==========================================
with st.form("prediction_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🏗️ Structure")
        building_type = st.selectbox("Type de Bâtiment", building_types)
        primary_type = st.selectbox("Usage Principal", primary_types)
        n_buildings = st.number_input("Nombre de Bâtiments", min_value=1, value=1)
        n_floors = st.number_input("Nombre d'Étages", min_value=1, value=2)
        year_built = st.number_input("Année de Construction", min_value=1800, max_value=2025, value=2000)

    with col2:
        st.subheader("📏 Surfaces & Usages")
        # Attention à l'alias ici : on affiche un nom propre, mais on enverra l'alias
        gfa_total = st.number_input("Surface Totale (m²)", min_value=10.0, value=1000.0)
        gfa_building = st.number_input("Surface Bâtie (m²)", min_value=10.0, value=900.0)
        largest_use = st.selectbox("Plus Grand Usage", largest_uses)
        n_uses = st.number_input("Nombre d'Usages Différents", min_value=1, value=1)

    st.subheader("⚡ Équipements")
    c1, c2, c3 = st.columns(3)
    with c1:
        uses_steam = st.checkbox("Utilise la Vapeur ?")
    with c2:
        uses_gas = st.checkbox("Utilise le Gaz Naturel ?", value=True)
    with c3:
        has_parking = st.checkbox("Possède un Parking ?")

    # Bouton de soumission
    submit_btn = st.form_submit_button("Lancer la Prédiction")

# ==========================================
# 4. APPEL API BENTOML
# ==========================================
if submit_btn:
    # 1. Construction du payload JSON exact attendu par Pydantic
    # Notez la clé "input_" qui enveloppe tout (si BentoML l'exige)
    # OU directement l'objet selon votre configuration.
    # On essaie d'abord le format enveloppé "input_" qui semblait fonctionner
    
    payload = {
        "input_": {  
            "BuildingType": building_type,
            "PrimaryPropertyType": primary_type,
            "LargestPropertyUseType": largest_use,
            "NumberofBuildings": n_buildings,
            "NumberofFloors": n_floors,
            "PropertyGFATotal": gfa_total,
            "PropertyGFABuilding(s)": gfa_building, # L'alias critique !
            "YearBuilt": year_built,
            "NumPropertyUseTypes": n_uses,
            "UsesSteam": uses_steam,
            "UsesNaturalGas": uses_gas,
            "HasParking": has_parking
        }
    }

    with st.spinner("Calcul en cours..."):
        try:
            response = requests.post(API_URL, json=payload)
            
            if response.status_code == 200:
                prediction = response.json()
                st.success(f"✅ Consommation Estimée : **{prediction:,.2f}** kWh (ou unité locale)")
                
                # Petit bonus visuel
                st.metric(label="Site Energy Use", value=f"{prediction:,.0f}")
            else:
                st.error(f"Erreur API ({response.status_code}) :")
                st.json(response.json()) # Affiche le détail de l'erreur pour déboguer
                
        except requests.exceptions.ConnectionError:
            st.error("❌ Impossible de contacter l'API. Vérifiez que 'bentoml serve' tourne bien sur le port 3000.")
# streamlit run app.py 