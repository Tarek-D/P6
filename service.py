import bentoml
import json
import os
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime

# Champs requis selon le notebook de modélisation :

# Ne necissitent pas de transformation :
# NumberofBuildings
# NumberofFloors
# PropertyGFATotal = Surface totale du bâtiment avec parking
# PropertyGFABuilding(s) = Surface totale du bâtiment sans parking
# UsesSteam
# UsesNaturalGas
# HasParking
# NumPropertyUseTypes

# Champs nécessitant une transformation :
# BuildingType / encodé en numérique mapping pré-défini / BuildingType_label_encoding_mapping.json
# LargestPropertyUseType / LargestPropertyUseType_label_encoding_mapping.json
# PrimaryPropertyType / PrimaryPropertyType_label_encoding_mapping.json
# BuildingAge / YearBuilt transformé en âge du bâtiment


import bentoml
import json
import os
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime

# ==========================================
# 1. CONFIGURATION & UTILITAIRES
# ==========================================

# ATTENTION : 2025 pour que le calcul de l'âge (BuildingAge) soit cohérent avec l'entraînement.
REFERENCE_YEAR = 2025 

def create_dynamic_enum(filename: str, enum_name: str):
    """
    Charge un JSON et retourne un tuple (EnumClass, MappingDict).
    Nettoie les clés pour qu'elles soient valides en Python.
    """
    # Chemin absolu vers le fichier JSON (situé dans le même dossier que service.py)
    path = os.path.join(os.path.dirname(__file__), filename)
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            mapping_dict = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"ERREUR CRITIQUE : Le fichier de mapping '{filename}' est introuvable dans le dossier du service.")

    # Transformation des clés JSON en noms de variables Python valides
    # Ex: "Non-Refrigerated Warehouse" -> "NON_REFRIGERATED_WAREHOUSE"
    enum_members = {
        k.upper()
         .replace(" ", "_")
         .replace("-", "_")
         .replace("(", "")
         .replace(")", "")
         .replace("/", "_")
         .replace("'", "") : k 
        for k in mapping_dict.keys()
    }
    
    # Création dynamique de l'Enum typé 'str' pour la validation Pydantic
    enum_class = Enum(enum_name, enum_members, type=str)
    
    return enum_class, mapping_dict

# ==========================================
# 2. CHARGEMENT DES MAPPINGS (Initialisation)
# ==========================================

# On charge les 3 dictionnaires au démarrage du service
BuildingTypeEnum, BUILD_TYPE_MAP = create_dynamic_enum(
    "BuildingType_label_encoding_mapping.json", "BuildingType"
)

LargestUseEnum, LARGEST_USE_MAP = create_dynamic_enum(
    "LargestPropertyUseType_label_encoding_mapping.json", "LargestUse"
)

PrimaryTypeEnum, PRIMARY_TYPE_MAP = create_dynamic_enum(
    "PrimaryPropertyType_label_encoding_mapping.json", "PrimaryType"
)

# ==========================================
# 3. SCHEMA DE DONNÉES (Contrat d'interface)
# ==========================================

class BuildingInput(BaseModel):
    # Champs Catégoriels (User envoie un String, ex: "Hotel")
    BuildingType: BuildingTypeEnum
    PrimaryPropertyType: PrimaryTypeEnum
    LargestPropertyUseType: LargestUseEnum
    
    # Champs Numériques
    NumberofBuildings: float
    NumberofFloors: float
    PropertyGFATotal: float
    
    # Alias obligatoire car les parenthèses sont interdites dans les noms de variables Python
    # Dans le JSON envoyé par l'utilisateur, la clé sera "PropertyGFABuilding(s)"
    PropertyGFABuildings: float = Field(alias="PropertyGFABuilding(s)")
    
    NumPropertyUseTypes: int
    
    # Transformation requise : On demande l'année de construction pour calculer l'âge
    YearBuilt: int
    
    # Champs Booléens
    UsesSteam: bool
    UsesNaturalGas: bool
    HasParking: bool


# ==========================================
# 4. SERVICE BENTOML (Logique Métier)
# ==========================================

@bentoml.service(name="energy_prediction_service")
class EnergyPredictor:
    # Récupération du modèle depuis le store local
    bento_model = bentoml.models.get("energy_rf_model:latest")

    def __init__(self):
        self.model = self.bento_model.load_model()

    @bentoml.api
    def predict(self, input_: BuildingInput) -> float:
        print(f"DEBUG RECU -> Type: {input_.BuildingType.value}")
        print(f"DEBUG MAP DISPO: {list(BUILD_TYPE_MAP.keys())[:5]}...")
        # --- A. Transformations Préliminaires ---
        
        # 1. Calcul de l'âge du bâtiment
        building_age = REFERENCE_YEAR - input_.YearBuilt
        
        # 2. Encodage des variables catégorielles (String -> Int)
        # On utilise .value pour récupérer la chaîne originale (ex: "Hotel") 
        # puis on cherche l'index correspondant dans le dictionnaire chargé.
        building_type_enc = BUILD_TYPE_MAP[input_.BuildingType.value]
        primary_type_enc = PRIMARY_TYPE_MAP[input_.PrimaryPropertyType.value]
        largest_use_enc = LARGEST_USE_MAP[input_.LargestPropertyUseType.value]

        # --- B. Construction du Vecteur (Ordre Strict) ---
        # L'ordre ici doit correspondre exactement à X_train.columns lors du fit()
        features = [[
            building_type_enc,               # 1. BuildingType
            primary_type_enc,                # 2. PrimaryPropertyType
            input_.NumberofBuildings,    # 3. NumberofBuildings
            input_.NumberofFloors,       # 4. NumberofFloors
            input_.PropertyGFATotal,     # 5. PropertyGFATotal
            input_.PropertyGFABuildings, # 6. PropertyGFABuilding(s)
            largest_use_enc,                 # 7. LargestPropertyUseType
            building_age,                    # 8. BuildingAge
            int(input_.UsesSteam),       # 9. UsesSteam
            int(input_.UsesNaturalGas),  # 10. UsesNaturalGas
            int(input_.HasParking),      # 11. HasParking
            input_.NumPropertyUseTypes   # 12. NumPropertyUseTypes
        ]]
        
        # --- C. Prédiction ---
        return self.model.predict(features)[0]
# Pour lancer le service en local :
# bentoml serve service.py:EnergyPredictor