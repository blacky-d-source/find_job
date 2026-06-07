import streamlit as st
from supabase import create_client, Client
import os
from dotenv import load_dotenv
import copy
from datetime import datetime, timezone
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

# Load environment variables
load_dotenv()
load_dotenv("../.env")

st.set_page_config(page_title="Gestion des Appels et Leads", layout="wide")

def fetch_schema_tables(url, key):
    try:
        import requests
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}"
        }
        response = requests.get(f"{url}/rest/v1/", headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            definitions = data.get("definitions", {})
            return sorted(list(definitions.keys()))
    except Exception as e:
        print(f"Failed to fetch schema tables: {e}")
    return []

def get_query_param(name, default=""):
    try:
        if name in st.query_params:
            return st.query_params[name]
    except AttributeError:
        try:
            params = st.experimental_get_query_params()
            if name in params:
                return params[name][0]
        except Exception:
            pass
    return default

def set_query_param(name, value):
    try:
        st.query_params[name] = str(value)
    except AttributeError:
        try:
            st.experimental_set_query_params(**{name: [str(value)]})
        except Exception:
            pass

# Initialize session state variables from URL parameters to persist mobile sessions
init_db_choice = get_query_param("db_choice", "autom_scrap_mess")
init_page_choice = get_query_param("page_choice", "")
init_quick_call_index = int(get_query_param("quick_call_index", "0"))
init_view_mode = get_query_param("view_mode", "Liste complete")

if "db_choice" not in st.session_state:
    st.session_state.db_choice = init_db_choice
if "quick_call_index" not in st.session_state:
    st.session_state.quick_call_index = init_quick_call_index
if "view_mode" not in st.session_state:
    st.session_state.view_mode = init_view_mode

# Database Selection at the top of sidebar
st.sidebar.subheader("Configuration Base de donnees")

db_options = ["autom_scrap_mess", "findjob", "Personnalise"]
db_default_idx = db_options.index(st.session_state.db_choice) if st.session_state.db_choice in db_options else 0

db_choice = st.sidebar.selectbox(
    "Selectionner le projet",
    options=db_options,
    index=db_default_idx,
    key="db_choice_select"
)

# Detect project switch to clear cache and data
if "last_db_choice" not in st.session_state:
    st.session_state.last_db_choice = db_choice
elif st.session_state.last_db_choice != db_choice:
    st.session_state.last_db_choice = db_choice
    st.cache_data.clear()
    if "leads" in st.session_state:
        del st.session_state.leads
    if "emails" in st.session_state:
        del st.session_state.emails
    if "jobs" in st.session_state:
        del st.session_state.jobs
    if "templates" in st.session_state:
        del st.session_state.templates
    if "leads_error" in st.session_state:
        del st.session_state.leads_error
    if "table_input_key" in st.session_state:
        del st.session_state.table_input_key
    
    # Clear cached tables list for databases
    for k in list(st.session_state.keys()):
        if k.startswith("db_tables_") or k.startswith("detected_table_"):
            del st.session_state[k]
            
    st.session_state.quick_call_index = 0
    # Will be re-evaluated below with the new client
    if "whatsapp_template" in st.session_state:
        del st.session_state.whatsapp_template

st.session_state.db_choice = db_choice

# Dynamically set Supabase URL and KEY
SUPABASE_URL = None
SUPABASE_KEY = None

if db_choice == "autom_scrap_mess":
    SUPABASE_URL = os.getenv("SUPABASE_URL_AUTOM_SCRAP_MESS") or os.getenv("SUPABASE_URL") or os.getenv("SUPABASE_URL_FINDJOB")
    SUPABASE_KEY = (os.getenv("SUPABASE_KEY_AUTOM_SCRAP_MESS") or 
                    os.getenv("SERVICE_ROLE_AUTOM_SCRAP_MESS") or 
                    os.getenv("SUPABASE_SERVICE_ROLE_KEY") or 
                    os.getenv("SERVICE_ROLE") or 
                    os.getenv("SUPABASE_KEY") or
                    os.getenv("SUPABASE_KEY_FINDJOB") or
                    os.getenv("SERVICE_ROLE_FINDJOB"))
elif db_choice == "findjob":
    SUPABASE_URL = os.getenv("SUPABASE_URL_FINDJOB") or os.getenv("SUPABASE_URL")
    SUPABASE_KEY = (os.getenv("SUPABASE_KEY_FINDJOB") or 
                    os.getenv("SERVICE_ROLE_FINDJOB") or
                    os.getenv("SUPABASE_SERVICE_ROLE_KEY") or 
                    os.getenv("SERVICE_ROLE") or 
                    os.getenv("SUPABASE_KEY"))
else: # Personnalise
    if "custom_url" not in st.session_state:
        st.session_state.custom_url = ""
    if "custom_key" not in st.session_state:
        st.session_state.custom_key = ""
        
    custom_url = st.sidebar.text_input("Supabase URL", value=st.session_state.custom_url, key="input_custom_url")
    custom_key = st.sidebar.text_input("Supabase Key (Service Role)", value=st.session_state.custom_key, key="input_custom_key", type="password")
    
    st.session_state.custom_url = custom_url
    st.session_state.custom_key = custom_key
    
    SUPABASE_URL = custom_url
    SUPABASE_KEY = custom_key

# Prompt manually if missing for predefined profiles
if db_choice in ["autom_scrap_mess", "findjob"] and (not SUPABASE_URL or not SUPABASE_KEY):
    st.sidebar.warning(f"Credentials absents pour {db_choice} dans le .env.")
    
    env_url_key = f"input_url_{db_choice}"
    env_token_key = f"input_key_{db_choice}"
    
    if env_url_key not in st.session_state:
        st.session_state[env_url_key] = ""
    if env_token_key not in st.session_state:
        st.session_state[env_token_key] = ""
        
    input_url = st.sidebar.text_input("Saisir Supabase URL", value=st.session_state[env_url_key], key=f"widget_url_{db_choice}")
    input_key = st.sidebar.text_input("Saisir Supabase Key", value=st.session_state[env_token_key], key=f"widget_key_{db_choice}", type="password")
    
    st.session_state[env_url_key] = input_url
    st.session_state[env_token_key] = input_key
    
    SUPABASE_URL = input_url
    SUPABASE_KEY = input_key

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Configuration Supabase manquante.")
    st.info("Veuillez renseigner les credentials Supabase dans le .env ou dans les champs ci-dessus.")
    st.stop()

# Instantiate Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Navigation Options based on project database
if db_choice == "findjob":
    nav_options = [
        "Appels (Entreprises et Telephones)",
        "Emails Professionnels",
        "Opportunites d'Emplois",
        "Modeles de Messages"
    ]
elif db_choice == "autom_scrap_mess":
    state_key = f"db_tables_{db_choice}"
    if state_key not in st.session_state:
        all_tables = fetch_schema_tables(SUPABASE_URL, SUPABASE_KEY)
        filtered = [t for t in all_tables if t.lower().startswith(("dataset", "leads"))]
        if not filtered:
            filtered = ["dataset_5000"]
        st.session_state[state_key] = filtered
    nav_options = st.session_state[state_key] + ["Modeles de Messages"]
else:
    nav_options = [
        "Appels (Entreprises et Telephones)",
        "Modeles de Messages"
    ]

# If the previously selected page choice is not in the allowed options, reset it
if "navigation_page_choice" in st.session_state and st.session_state.navigation_page_choice not in nav_options:
    st.session_state.navigation_page_choice = nav_options[0]
elif "navigation_page_choice" not in st.session_state and init_page_choice in nav_options:
    st.session_state.navigation_page_choice = init_page_choice

page_default_idx = nav_options.index(st.session_state.navigation_page_choice) if "navigation_page_choice" in st.session_state and st.session_state.navigation_page_choice in nav_options else 0

# Navigation Page Selection in sidebar
st.sidebar.subheader("Navigation")
page_choice = st.sidebar.selectbox(
    "Selectionner la table/vue",
    options=nav_options,
    index=page_default_idx,
    key="navigation_page_choice"
)

# Detect page selection switch to clear manual override
if "last_page_choice" not in st.session_state:
    st.session_state.last_page_choice = page_choice
elif st.session_state.last_page_choice != page_choice:
    st.session_state.last_page_choice = page_choice
    if "table_input_key" in st.session_state:
        del st.session_state.table_input_key

# Table mapping
if page_choice == "Appels (Entreprises et Telephones)":
    if db_choice == "findjob":
        active_table = "companies"
    elif db_choice == "autom_scrap_mess":
        state_key = f"detected_table_{db_choice}"
        if state_key not in st.session_state:
            detected = None
            candidates = ["dataset_5000", "leads_ca_french", "leads"]
            for cand in candidates:
                try:
                    res = supabase.table(cand).select("id").limit(1).execute()
                    detected = cand
                    break
                except Exception:
                    continue
            if not detected:
                detected = os.getenv("SUPABASE_TABLE") or "dataset_5000"
            st.session_state[state_key] = detected
        active_table = st.session_state[state_key]
    else: # Personnalise
        active_table = os.getenv("SUPABASE_TABLE") or "leads"
elif page_choice.lower().startswith(("dataset", "leads")):
    active_table = page_choice
elif page_choice == "Emails Professionnels":
    active_table = "company_emails"
elif page_choice == "Opportunites d'Emplois":
    active_table = "job_opportunities"
else:
    active_table = "messages_templates"

# Respect manual override if the widget key exists and page/project hasn't just changed
if "table_input_key" in st.session_state and st.session_state.table_input_key:
    if "last_db_choice" in st.session_state and st.session_state.last_db_choice == db_choice:
        active_table = st.session_state.table_input_key

# Detect table name switch to clear cached data
if "last_table_name" not in st.session_state:
    st.session_state.last_table_name = active_table
elif st.session_state.last_table_name != active_table:
    st.session_state.last_table_name = active_table
    if "leads" in st.session_state:
        del st.session_state.leads
    if "emails" in st.session_state:
        del st.session_state.emails
    if "jobs" in st.session_state:
        del st.session_state.jobs
    if "templates" in st.session_state:
        del st.session_state.templates
    st.session_state.quick_call_index = 0

st.session_state.table_name = active_table

# Initialisation du pool d'executeurs
if "db_executor" not in st.session_state:
    st.session_state.db_executor = ThreadPoolExecutor(max_workers=1)

def db_update(client, lead_id, phone_list, table_name):
    try:
        client.table(table_name).update({"phone_whatsapp_valides": phone_list}).eq("id", lead_id).execute()
    except Exception as e:
        print(f"Background DB Update Failed: {e}")

def db_update_phone(client, phone_id, update_fields):
    try:
        client.table("company_phones").update(update_fields).eq("id", phone_id).execute()
    except Exception as e:
        print(f"Background Phone DB Update Failed: {e}")

def db_update_template(client, content_val):
    try:
        res = client.table("messages_templates").select("id").limit(1).execute()
        if res.data:
            row_id = res.data[0]["id"]
            client.table("messages_templates").update({"content": content_val}).eq("id", row_id).execute()
        else:
            client.table("messages_templates").insert({"content": content_val}).execute()
    except Exception as e:
        print(f"Background Template Update Failed: {e}")

def get_whatsapp_template(client):
    try:
        res = client.table("messages_templates").select("content").limit(1).execute()
        if res.data and res.data[0].get("content"):
            return res.data[0]["content"]
    except Exception as e:
        print(f"Failed to fetch template from DB: {e}")
    return "Bonjour, je vous contacte au nom de [Nom_Entreprise] suite a votre interet pour nos services."

def on_template_change():
    new_template = st.session_state.whatsapp_template_input
    st.session_state.whatsapp_template = new_template
    st.session_state.db_executor.submit(db_update_template, supabase, new_template)

# Callbacks pour mise a jour en temps reel (executes en arriere-plan)
def on_wa_change(lead, phone, key):
    new_val = st.session_state[key]
    phone["has_whatsapp"] = new_val
    if st.session_state.table_name == "companies" and "id" in phone:
        st.session_state.db_executor.submit(db_update_phone, supabase, phone["id"], {"has_whatsapp": new_val})
    else:
        phone_list_copy = copy.deepcopy(lead["phone_whatsapp_valides"])
        st.session_state.db_executor.submit(db_update, supabase, lead["id"], phone_list_copy, st.session_state.table_name)

def on_cont_change(lead, phone, key):
    new_val = st.session_state[key]
    phone["contacted"] = new_val
    if new_val:
        phone["last_contacted"] = datetime.now(timezone.utc).isoformat()
    else:
        phone["last_contacted"] = None
    if st.session_state.table_name == "companies" and "id" in phone:
        st.session_state.db_executor.submit(db_update_phone, supabase, phone["id"], {"contacted": new_val, "last_contacted": phone["last_contacted"]})
    else:
        phone_list_copy = copy.deepcopy(lead["phone_whatsapp_valides"])
        st.session_state.db_executor.submit(db_update, supabase, lead["id"], phone_list_copy, st.session_state.table_name)

def on_status_click(lead, phone):
    current_status = phone.get("call_status", "to call")
    if current_status == "to call":
        new_status = "called"
    elif current_status == "called":
        new_status = "unavailable"
    else:
        new_status = "to call"
        
    phone["call_status"] = new_status
    if new_status == "called":
        phone["contacted"] = True
        phone["last_contacted"] = datetime.now(timezone.utc).isoformat()
    elif new_status == "to call":
        phone["contacted"] = False
        phone["last_contacted"] = None
        
    if st.session_state.table_name == "companies" and "id" in phone:
        update_fields = {"call_status": new_status}
        if new_status == "called":
            update_fields["contacted"] = True
            update_fields["last_contacted"] = phone["last_contacted"]
        elif new_status == "to call":
            update_fields["contacted"] = False
            update_fields["last_contacted"] = None
        st.session_state.db_executor.submit(db_update_phone, supabase, phone["id"], update_fields)
    else:
        phone_list_copy = copy.deepcopy(lead["phone_whatsapp_valides"])
        st.session_state.db_executor.submit(db_update, supabase, lead["id"], phone_list_copy, st.session_state.table_name)

def on_job_click(lead, phone):
    current_val = phone.get("job_obtained", "en attente")
    if current_val == "en attente":
        new_val = "oui"
    elif current_val == "oui":
        new_val = "non"
    else:
        new_val = "en attente"
        
    phone["job_obtained"] = new_val
    if st.session_state.table_name == "companies" and "id" in phone:
        st.session_state.db_executor.submit(db_update_phone, supabase, phone["id"], {"job_obtained": new_val})
    else:
        phone_list_copy = copy.deepcopy(lead["phone_whatsapp_valides"])
        st.session_state.db_executor.submit(db_update, supabase, lead["id"], phone_list_copy, st.session_state.table_name)

@st.dialog("Offres d'emploi de l'entreprise")
def show_company_jobs_dialog(company_name, company_id):
    st.write(f"### {company_name}")
    st.write(f"ID : `{company_id}`")
    st.markdown("---")
    
    try:
        res = supabase.table("job_opportunities").select("*").eq("company_id", company_id).order("id").execute()
        jobs = res.data or []
        
        if not jobs:
            st.info("Aucune offre d'emploi trouvee pour cette entreprise dans la base de donnees.")
        else:
            st.write(f"**{len(jobs)} offre(s) d'emploi trouvee(s) :**")
            for idx, j in enumerate(jobs):
                with st.container(border=True):
                    st.write(f"**{j.get('title') or 'Poste Inconnu'}**")
                    st.write(f"Contrat : {j.get('contract_type') or 'Non precise'} | Salaire : {j.get('salary') or 'Non precise'}")
                    pub_date = parse_date(j.get("pub_date"))
                    if pub_date:
                        st.write(f"Publie le : {pub_date.strftime('%Y-%m-%d')}")
                    
                    apply_url = j.get("apply_url")
                    if apply_url:
                        clean_url = apply_url if apply_url.startswith(("http://", "https://")) else f"https://{apply_url}"
                        st.markdown(f'<a href="{clean_url}" target="_blank" class="custom-btn" style="width: auto; display: inline-block;">Voir l\'offre</a>', unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Erreur lors de la recuperation des opportunites : {e}")

if "whatsapp_template" not in st.session_state:
    st.session_state.whatsapp_template = get_whatsapp_template(supabase)
if "quick_call_index" not in st.session_state:
    st.session_state.quick_call_index = 0



# Inject custom CSS for modern monochrome theme
st.markdown("""
<style>
    /* Global styles */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #F9F9F9 !important;
        border-right: 1px solid #E5E5E5 !important;
    }
    
    /* Force all text inside the app container and sidebar to be black */
    [data-testid="stAppViewContainer"] *, [data-testid="stSidebar"] * {
        color: #000000 !important;
    }
    
    /* Override button text to be white */
    div[data-testid="stButton"] button, div[data-testid="stButton"] button *, .custom-btn, .custom-btn * {
        color: #FFFFFF !important;
    }
    
    /* Custom buttons styled as links */
    .custom-btn {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        border: 1px solid #000000 !important;
        border-radius: 2px !important;
        font-weight: 500 !important;
        padding: 6px 16px !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
        font-size: 14px !important;
        text-decoration: none !important;
        text-align: center !important;
        display: inline-block !important;
        cursor: pointer !important;
        width: 100% !important;
    }
    
    .custom-btn:hover {
        background-color: #222222 !important;
        border-color: #222222 !important;
        color: #FFFFFF !important;
    }
    
    .custom-btn:active {
        background-color: #111111 !important;
        color: #FFFFFF !important;
    }
    
    /* Headings */
    h1, h2, h3, h4, h5, h6 {
        color: #000000 !important;
        font-family: 'Geist', -apple-system, sans-serif !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em !important;
    }
    
    /* Expander styling */
    div[data-testid="stExpander"] {
        background-color: #F9F9F9 !important;
        border: 1px solid #E5E5E5 !important;
        border-radius: 4px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
        margin-bottom: 12px !important;
    }
    
    div[data-testid="stExpander"] summary {
        background-color: #F9F9F9 !important;
        color: #000000 !important;
    }
    
    /* Inputs, selectboxes and their dropdown items */
    input, select, textarea, div[data-baseweb="select"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        border: 1px solid #E5E5E5 !important;
        border-radius: 4px !important;
    }
    
    /* Dropdown options rendering */
    ul[role="listbox"] li, div[role="option"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
    }
    
    /* Buttons */
    div[data-testid="stButton"] button {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        border: 1px solid #000000 !important;
        border-radius: 2px !important;
        font-weight: 500 !important;
        padding: 6px 16px !important;
        transition: background-color 0.2s ease !important;
    }
    
    div[data-testid="stButton"] button:hover {
        background-color: #222222 !important;
        color: #FFFFFF !important;
        border-color: #222222 !important;
    }
    
    div[data-testid="stButton"] button:active {
        background-color: #111111 !important;
        color: #FFFFFF !important;
    }
    
    /* Alerts and Toasts */
    div[data-testid="stAlert"] {
        background-color: #F9F9F9 !important;
        color: #000000 !important;
        border: 1px solid #E5E5E5 !important;
        border-radius: 4px !important;
    }
    
    div[data-testid="stAlert"] * {
        color: #000000 !important;
    }
    
    /* Metric styling */
    div[data-testid="stMetricValue"] {
        color: #000000 !important;
        font-weight: 700 !important;
    }
    
    div[data-testid="stMetricLabel"] {
        color: #444444 !important;
    }

    /* Tabs selector monochrome */
    button[data-baseweb="tab"] {
        color: #888888 !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
    }
    button[data-baseweb="tab"] p {
        color: #888888 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #000000 !important;
        border-bottom-color: #000000 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] p {
        color: #000000 !important;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)

# Page header
st.title("Dashboard de Gestion - SwipeJob")

# Recharger les donnees Button in Sidebar
st.sidebar.markdown("---")
if st.sidebar.button("Recharger les donnees"):
    st.cache_data.clear()
    # Force data reload depending on page
    if page_choice == "Appels (Entreprises et Telephones)" or page_choice.lower().startswith(("dataset", "leads")):
        if "leads" in st.session_state:
            del st.session_state.leads
    elif page_choice == "Emails Professionnels":
        if "emails" in st.session_state:
            del st.session_state.emails
    elif page_choice == "Opportunites d'Emplois":
        if "jobs" in st.session_state:
            del st.session_state.jobs
    elif page_choice == "Modeles de Messages":
        if "templates" in st.session_state:
            del st.session_state.templates
    st.session_state.quick_call_index = 0
    st.rerun()

# Configuration de la Table (Manual Override)
st.sidebar.markdown("---")
with st.sidebar.expander("Parametres avances"):
    def on_table_change():
        st.cache_data.clear()
        if "leads" in st.session_state:
            del st.session_state["leads"]
        if "leads_error" in st.session_state:
            del st.session_state["leads_error"]
        st.session_state.quick_call_index = 0

    table_input = st.text_input(
        "Table Supabase",
        value=st.session_state.table_name,
        key="table_input_key",
        on_change=on_table_change
    )
    st.session_state.table_name = table_input

# Filters initialization
search_company = ""
search_phone = ""
whatsapp_filter = "Tous"
contacted_filter = "Tous"
call_status_filter = "Tous"
date_filter_type = "Tous"
filter_date = None
job_obtained_filter = "Tous"

search_email = ""
email_stage_filter = "Tous"
email_contacted_filter = "Tous"
email_replied_filter = "Tous"

search_job = ""
job_contract_filter = "Tous"
job_active_filter = "Tous"

# Dynamic sidebar filters based on the selected view page
if page_choice == "Appels (Entreprises et Telephones)" or page_choice.lower().startswith(("dataset", "leads")):
    st.sidebar.subheader("Filtres Appels")
    search_company = st.sidebar.text_input("Rechercher une entreprise", value="")
    search_phone = st.sidebar.text_input("Rechercher un numero", value="")
    whatsapp_filter = st.sidebar.selectbox("WhatsApp", options=["Tous", "Avec WhatsApp", "Sans WhatsApp"])
    contacted_filter = st.sidebar.selectbox("Statut de contact", options=["Tous", "Contacte", "Non contacte"])
    call_status_filter = st.sidebar.selectbox("Statut de l'appel", options=["Tous", "to call", "called", "unavailable"])
    date_filter_type = st.sidebar.selectbox("Date de dernier contact", options=["Tous", "Depuis une date", "Avant une date", "Pas de date"])
    if date_filter_type in ["Depuis une date", "Avant une date"]:
        filter_date = st.sidebar.date_input("Date cible", value=datetime.today().date())
    job_obtained_filter = st.sidebar.selectbox("Job obtenu", options=["Tous", "en attente", "oui", "non"])

elif page_choice == "Emails Professionnels":
    st.sidebar.subheader("Filtres Emails")
    search_email = st.sidebar.text_input("Rechercher un email", value="")
    email_stage_filter = st.sidebar.selectbox("Etape de campagne", options=["Tous", "start", "follow-up", "completed"])
    email_contacted_filter = st.sidebar.selectbox("Contacte", options=["Tous", "Oui", "Non"])
    email_replied_filter = st.sidebar.selectbox("Repondu", options=["Tous", "Oui", "Non"])

elif page_choice == "Opportunites d'Emplois":
    st.sidebar.subheader("Filtres Offres d'Emploi")
    search_job = st.sidebar.text_input("Rechercher un emploi", value="")
    job_contract_filter = st.sidebar.selectbox("Type de contrat", options=["Tous", "CDI", "CDD", "Freelance", "Stage", "Remote"])
    job_active_filter = st.sidebar.selectbox("Statut de l'offre", options=["Tous", "Active", "Inactive"])

# Configuration du modèle de message WhatsApp
if page_choice == "Appels (Entreprises et Telephones)" or page_choice.lower().startswith(("dataset", "leads")) or page_choice == "Modeles de Messages":
    st.sidebar.markdown("---")
    st.sidebar.subheader("Configuration WhatsApp")
    whatsapp_template = st.sidebar.text_area(
        "Modele de message",
        value=st.session_state.whatsapp_template,
        key="whatsapp_template_input",
        on_change=on_template_change
    )

# Retrieve data with cache
@st.cache_data(ttl=3600)
def get_data(table_name, supabase_url, supabase_key):
    temp_client = create_client(supabase_url, supabase_key)
    all_data = []
    limit = 1000
    offset = 0
    if table_name == "companies":
        while True:
            res = temp_client.table("companies")\
                .select("id, name, website, address, industry, risk_score, has_careers_page, is_hiring_yc, company_phones(*)")\
                .order("id")\
                .range(offset, offset + limit - 1)\
                .execute()
            if not res.data:
                break
            all_data.extend(res.data)
            if len(res.data) < limit:
                break
            offset += limit
        
        mapped_data = []
        for item in all_data:
            mapped_item = {
                "id": item["id"],
                "company": item["name"],  # Map 'name' to 'company'
                "website": item["website"],
                "address": item.get("address"),
                "industry": item.get("industry"),
                "risk_score": item.get("risk_score", 0.0),
                "has_careers_page": item.get("has_careers_page", False),
                "is_hiring_yc": item.get("is_hiring_yc", False),
                "phone_whatsapp_valides": item.get("company_phones", []) or []
            }
            mapped_data.append(mapped_item)
        return mapped_data
    else:
        while True:
            res = temp_client.table(table_name).select("*").order("id").range(offset, offset + limit - 1).execute()
            if not res.data:
                break
            all_data.extend(res.data)
            if len(res.data) < limit:
                break
            offset += limit
        return all_data

# Initialisation du session state pour les leads
if "leads_error" not in st.session_state:
    st.session_state.leads_error = None

def load_page_data(force=False):
    try:
        if page_choice == "Appels (Entreprises et Telephones)" or page_choice.lower().startswith(("dataset", "leads")):
            if "leads" not in st.session_state or force:
                st.session_state.leads = copy.deepcopy(get_data(st.session_state.table_name, SUPABASE_URL, SUPABASE_KEY))
        elif page_choice == "Emails Professionnels":
            if "emails" not in st.session_state or force:
                st.session_state.emails = copy.deepcopy(get_data("company_emails", SUPABASE_URL, SUPABASE_KEY))
        elif page_choice == "Opportunites d'Emplois":
            if "jobs" not in st.session_state or force:
                st.session_state.jobs = copy.deepcopy(get_data("job_opportunities", SUPABASE_URL, SUPABASE_KEY))
        elif page_choice == "Modeles de Messages":
            if "templates" not in st.session_state or force:
                st.session_state.templates = copy.deepcopy(get_data("messages_templates", SUPABASE_URL, SUPABASE_KEY))
        
        # Override table loading
        if page_choice not in ["Appels (Entreprises et Telephones)", "Emails Professionnels", "Opportunites d'Emplois", "Modeles de Messages"] and not page_choice.lower().startswith(("dataset", "leads")):
            if "custom_table_data" not in st.session_state or force:
                st.session_state.custom_table_data = copy.deepcopy(get_data(st.session_state.table_name, SUPABASE_URL, SUPABASE_KEY))
        st.session_state.leads_error = None
    except Exception as e:
        st.session_state.leads_error = str(e)

load_page_data()

if st.session_state.get("leads_error"):
    st.error(f"### Erreur de connexion a la table : {st.session_state.table_name}")
    st.info(
        "Veuillez verifier le nom de la table ou que les credentials configurés sont corrects.\n\n"
        f"Detail technique : `{st.session_state.leads_error}`"
    )
    st.stop()

# Parseur de date robuste
def parse_date(date_str):
    if not date_str:
        return None
    try:
        clean_str = date_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str)
    except Exception:
        return None

# Reload dynamic page views
if page_choice == "Appels (Entreprises et Telephones)" or page_choice.lower().startswith(("dataset", "leads")):
    # Selector for View Mode
    view_options = ["Liste complete", "Appel rapide (Un par un)"]
    view_default_idx = view_options.index(st.session_state.view_mode) if "view_mode" in st.session_state and st.session_state.view_mode in view_options else 0
    view_mode = st.radio(
        "Mode d'affichage",
        options=view_options,
        index=view_default_idx,
        horizontal=True,
        key="view_mode"
    )

    # Reset page number / quick call index if filters change
    filter_state = (search_company, search_phone, contacted_filter, whatsapp_filter, call_status_filter, date_filter_type, str(filter_date), job_obtained_filter)
    if "prev_filter_state" not in st.session_state:
        st.session_state.prev_filter_state = filter_state
    elif st.session_state.prev_filter_state != filter_state:
        st.session_state.prev_filter_state = filter_state
        st.session_state.quick_call_index = 0

    # Filtrage en memoire
    filtered_leads = []
    for lead in st.session_state.leads:
        phone_list = lead.get("phone_whatsapp_valides")
        if not phone_list or not isinstance(phone_list, list):
            continue
            
        # Recherche entreprise
        if search_company:
            company_name = lead.get("company") or ""
            if search_company.lower() not in company_name.lower():
                continue
                
        matching_phones = []
        for phone in phone_list:
            # Recherche numero
            if search_phone:
                number = phone.get("number") or ""
                if search_phone not in number:
                    continue
                    
            # WhatsApp filter
            has_wa = phone.get("has_whatsapp", False)
            if whatsapp_filter == "Avec WhatsApp" and not has_wa:
                continue
            elif whatsapp_filter == "Sans WhatsApp" and has_wa:
                continue
                
            # Contacted filter
            is_contacted = phone.get("contacted", False)
            if contacted_filter == "Contacte" and not is_contacted:
                continue
            elif contacted_filter == "Non contacte" and is_contacted:
                continue
                
            # Call status filter
            status = phone.get("call_status", "to call")
            if call_status_filter != "Tous" and status != call_status_filter:
                continue
                
            # Date filter
            last_contact = parse_date(phone.get("last_contacted"))
            if date_filter_type == "Depuis une date" and filter_date:
                if not last_contact or last_contact.date() < filter_date:
                    continue
            elif date_filter_type == "Avant une date" and filter_date:
                if not last_contact or last_contact.date() > filter_date:
                    continue
            elif date_filter_type == "Pas de date":
                if last_contact is not None:
                    continue
            
            # Job Obtained filter
            job_obtained = phone.get("job_obtained", "en attente")
            if job_obtained_filter != "Tous" and job_obtained != job_obtained_filter:
                continue
                    
            matching_phones.append(phone)
            
        if matching_phones:
            lead_copy = dict(lead)
            lead_copy["_matching_phones"] = matching_phones
            filtered_leads.append(lead_copy)

    # Section Statistiques
    st.markdown("### Statistiques")
    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric(label="Entreprises filtrees", value=len(filtered_leads))
    total_matching_phones = sum(len(lead["_matching_phones"]) for lead in filtered_leads)
    m_col2.metric(label="Numeros filtres", value=total_matching_phones)
    total_contacted = sum(1 for lead in filtered_leads for phone in lead["_matching_phones"] if phone.get("contacted"))
    m_col3.metric(label="Numeros contactes", value=total_contacted)

    # Rendu en fonction du mode choisi
    if view_mode == "Liste complete":
        st.markdown("---")
        st.markdown("### Statistiques et Graphiques avances")
        
        total_called = 0
        total_unavailable = 0
        calls_today = 0
        today_utc = datetime.now(timezone.utc).date()
        
        status_counts = {"to call": 0, "called": 0, "unavailable": 0}
        job_counts = {"en attente": 0, "oui": 0, "non": 0}
        
        for lead in filtered_leads:
            for phone in lead["_matching_phones"]:
                status = phone.get("call_status", "to call")
                status_counts[status] = status_counts.get(status, 0) + 1
                
                job_status = phone.get("job_obtained", "en attente")
                job_counts[job_status] = job_counts.get(job_status, 0) + 1
                
                if status == "called":
                    total_called += 1
                elif status == "unavailable":
                    total_unavailable += 1
                    
                last_contact_str = phone.get("last_contacted")
                if last_contact_str:
                    parsed_dt = parse_date(last_contact_str)
                    if parsed_dt and parsed_dt.date() == today_utc:
                        if status in ["called", "unavailable"]:
                            calls_today += 1
                        
        total_attempted = total_called + total_unavailable
        contactability_rate = (total_called / total_attempted * 100) if total_attempted > 0 else 0.0
        
        kpi_col1, kpi_col2 = st.columns(2)
        kpi_col1.metric(
            label="Taux de contactibilite", 
            value=f"{contactability_rate:.1f}%",
            help="Pourcentage d'appels aboutis par rapport au total tente"
        )
        kpi_col2.metric(
            label="Volume quotidien", 
            value=f"{calls_today} appel(s) aujourd'hui",
            help="Nombre d'appels passes dans la journee en cours (UTC)"
        )
            
        import pandas as pd
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            st.markdown("#### Distribution des statuts d'appel")
            df_status = pd.DataFrame(
                list(status_counts.items()),
                columns=["Statut", "Nombre"]
            ).set_index("Statut")
            try:
                st.bar_chart(df_status, color="#000000")
            except Exception:
                st.bar_chart(df_status)
                
        with chart_col2:
            st.markdown("#### Progression des recrutements")
            df_job = pd.DataFrame(
                list(job_counts.items()),
                columns=["Job obtenu", "Nombre"]
            ).set_index("Job obtenu")
            try:
                st.bar_chart(df_job, color="#000000")
            except Exception:
                st.bar_chart(df_job)

        # Pagination
        items_per_page = 10
        total_items = len(filtered_leads)
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        
        st.sidebar.markdown("---")
        page_number = st.sidebar.number_input(
            "Page Appels",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1
        )
        
        current_page = min(page_number, total_pages)
        start_idx = (current_page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, total_items)
        leads_page = filtered_leads[start_idx:end_idx]
        
        st.markdown(f"Affichage des resultats {start_idx + 1} a {end_idx} sur {total_items}")
        
        for lead in leads_page:
            matching_phones = lead["_matching_phones"]
            
            with st.expander(f"{lead['company'] or 'Entreprise Inconnue'} (ID: {lead['id']})"):
                website_url = lead.get("website")
                if db_choice == "findjob":
                    col_web, col_job = st.columns([1, 1])
                    with col_web:
                        if website_url:
                            clean_url = website_url if website_url.startswith(("http://", "https://")) else f"https://{website_url}"
                            st.markdown(f'<a href="{clean_url}" target="_blank" class="custom-btn" style="width: auto; display: inline-block; margin-bottom: 16px;">Site Web</a>', unsafe_allow_html=True)
                    with col_job:
                        if st.button("Offres d'emploi (Jobs)", key=f"list_job_dialog_btn_{lead['id']}", use_container_width=True):
                            show_company_jobs_dialog(lead.get('company') or 'Entreprise Inconnue', lead['id'])
                else:
                    if website_url:
                        clean_url = website_url if website_url.startswith(("http://", "https://")) else f"https://{website_url}"
                        st.markdown(f'<a href="{clean_url}" target="_blank" class="custom-btn" style="width: auto; display: inline-block; margin-bottom: 16px;">Site Web</a>', unsafe_allow_html=True)
                    
                for phone in matching_phones:
                    orig_index = lead["phone_whatsapp_valides"].index(phone)
                    
                    col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([1.5, 0.8, 0.8, 1.5, 1.2, 1.2, 1.8, 2.2])
                    
                    raw_num = phone.get("number", "")
                    clean_num = "".join(c for c in raw_num if c.isdigit() or c == '+')
                    tel_url = f"tel:{clean_num}"
                    
                    company_placeholder = lead.get("company") or ""
                    formatted_msg = whatsapp_template.replace("[Entreprise]", company_placeholder)
                    formatted_msg = formatted_msg.replace("[Nom_Entreprise]", company_placeholder)
                    encoded_msg = urllib.parse.quote(formatted_msg)
                    wa_url = f"https://wa.me/{clean_num}?text={encoded_msg}"
                    
                    with col1:
                        st.write(f"Numero : **{phone.get('number', 'N/A')}**")
                        
                    with col2:
                        cb_key = f"list_wa_{lead['id']}_{orig_index}"
                        st.checkbox(
                            "WhatsApp",
                            value=bool(phone.get("has_whatsapp", False)),
                            key=cb_key,
                            on_change=on_wa_change,
                            args=(lead, phone, cb_key)
                        )
                            
                    with col3:
                        cb_cont_key = f"list_cont_{lead['id']}_{orig_index}"
                        st.checkbox(
                            "Contacte",
                            value=bool(phone.get("contacted", False)),
                            key=cb_cont_key,
                            on_change=on_cont_change,
                            args=(lead, phone, cb_cont_key)
                        )
                            
                    with col4:
                        last_contact_str = phone.get("last_contacted", "")
                        parsed_dt = parse_date(last_contact_str)
                        if phone.get("contacted", False):
                            if parsed_dt:
                                display_date = parsed_dt.strftime("%Y-%m-%d %H:%M")
                                st.text(f"Dernier contact :\n{display_date}")
                            else:
                                st.text("Date non definie")
                        else:
                            st.text("Non contacte")
                    
                    with col5:
                        st.markdown(f'<a href="{tel_url}" target="_self" class="custom-btn">Appeler</a>', unsafe_allow_html=True)
                        
                    with col6:
                        st.markdown(f'<a href="{wa_url}" target="_blank" class="custom-btn">Message</a>', unsafe_allow_html=True)
                        
                    with col7:
                        current_status = phone.get("call_status", "to call")
                        btn_label = f"Statut : {current_status}"
                        st.button(
                            btn_label,
                            key=f"list_status_btn_{lead['id']}_{orig_index}",
                            on_click=on_status_click,
                            args=(lead, phone)
                        )
                        
                    with col8:
                        current_job = phone.get("job_obtained", "en attente")
                        job_btn_label = f"Job obtenu : {current_job}"
                        st.button(
                            job_btn_label,
                            key=f"list_job_btn_{lead['id']}_{orig_index}",
                            on_click=on_job_click,
                            args=(lead, phone)
                        )

    else:
        # Mode Appel Rapide (Un par un)
        if not filtered_leads:
            st.info("Aucun lead ne correspond aux filtres actuels.")
        else:
            idx = st.session_state.quick_call_index
            if idx >= len(filtered_leads):
                idx = len(filtered_leads) - 1
            if idx < 0:
                idx = 0
            st.session_state.quick_call_index = idx
            
            lead = filtered_leads[idx]
            matching_phones = lead["_matching_phones"]
            
            st.markdown("---")
            st.markdown(f"**Lead {idx + 1} sur {len(filtered_leads)}**")
            
            website_url = lead.get("website")
            
            st.markdown(f"""
            <div style="padding: 24px; border: 1px solid #E5E5E5; border-radius: 4px; background-color: #F9F9F9; margin-bottom: 12px;">
                <h4 style="margin: 0 0 8px 0; font-family: 'Geist', sans-serif; font-weight: 600; color: #000000;">{lead.get('company') or 'Entreprise Inconnue'}</h4>
                <p style="margin: 0; color: #444444; font-size: 14px; margin-bottom: 0;">ID: {lead['id']}</p>
            </div>
            """, unsafe_allow_html=True)
            
            if db_choice == "findjob":
                col_web, col_job = st.columns([1, 1])
                with col_web:
                    if website_url:
                        clean_url = website_url if website_url.startswith(("http://", "https://")) else f"https://{website_url}"
                        st.markdown(f'<a href="{clean_url}" target="_blank" class="custom-btn" style="text-decoration: none; margin-bottom: 24px;">Site Web</a>', unsafe_allow_html=True)
                with col_job:
                    if st.button("Offres d'emploi (Jobs)", key=f"quick_job_dialog_btn_{lead['id']}", use_container_width=True):
                        show_company_jobs_dialog(lead.get('company') or 'Entreprise Inconnue', lead['id'])
            else:
                if website_url:
                    clean_url = website_url if website_url.startswith(("http://", "https://")) else f"https://{website_url}"
                    st.markdown(f'<a href="{clean_url}" target="_blank" class="custom-btn" style="text-decoration: none; margin-bottom: 24px;">Site Web</a>', unsafe_allow_html=True)
            
            for phone in matching_phones:
                orig_index = lead["phone_whatsapp_valides"].index(phone)
                
                col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([1.5, 0.8, 0.8, 1.5, 1.2, 1.2, 1.8, 2.2])
                
                raw_num = phone.get("number", "")
                clean_num = "".join(c for c in raw_num if c.isdigit() or c == '+')
                tel_url = f"tel:{clean_num}"
                
                company_placeholder = lead.get("company") or ""
                formatted_msg = whatsapp_template.replace("[Entreprise]", company_placeholder)
                formatted_msg = formatted_msg.replace("[Nom_Entreprise]", company_placeholder)
                encoded_msg = urllib.parse.quote(formatted_msg)
                wa_url = f"https://wa.me/{clean_num}?text={encoded_msg}"
                
                with col1:
                    st.write(f"Numero : **{phone.get('number', 'N/A')}**")
                    
                with col2:
                    cb_key = f"quick_wa_{lead['id']}_{orig_index}"
                    st.checkbox(
                        "WhatsApp",
                        value=bool(phone.get("has_whatsapp", False)),
                        key=cb_key,
                        on_change=on_wa_change,
                        args=(lead, phone, cb_key)
                    )
                        
                with col3:
                    cb_cont_key = f"quick_cont_{lead['id']}_{orig_index}"
                    st.checkbox(
                        "Contacte",
                        value=bool(phone.get("contacted", False)),
                        key=cb_cont_key,
                        on_change=on_cont_change,
                        args=(lead, phone, cb_cont_key)
                    )
                        
                with col4:
                    last_contact_str = phone.get("last_contacted", "")
                    parsed_dt = parse_date(last_contact_str)
                    if phone.get("contacted", False):
                        if parsed_dt:
                            display_date = parsed_dt.strftime("%Y-%m-%d %H:%M")
                            st.text(f"Dernier contact :\n{display_date}")
                        else:
                            st.text("Date non definie")
                    else:
                        st.text("Non contacte")
                        
                with col5:
                    st.markdown(f'<a href="{tel_url}" target="_self" class="custom-btn">Appeler</a>', unsafe_allow_html=True)
                    
                with col6:
                    st.markdown(f'<a href="{wa_url}" target="_blank" class="custom-btn">Message</a>', unsafe_allow_html=True)
                    
                with col7:
                    current_status = phone.get("call_status", "to call")
                    btn_label = f"Statut : {current_status}"
                    st.button(
                        btn_label,
                        key=f"quick_status_btn_{lead['id']}_{orig_index}",
                        on_click=on_status_click,
                        args=(lead, phone)
                    )
                    
                with col8:
                    current_job = phone.get("job_obtained", "en attente")
                    job_btn_label = f"Job obtenu : {current_job}"
                    st.button(
                        job_btn_label,
                        key=f"quick_job_btn_{lead['id']}_{orig_index}",
                        on_click=on_job_click,
                        args=(lead, phone)
                    )
                        
            st.markdown("---")
            nav_col1, nav_col2, nav_col3 = st.columns([2, 4, 2])
            
            with nav_col1:
                if st.button("Precedent", disabled=(idx == 0), key="prev_lead_btn"):
                    st.session_state.quick_call_index -= 1
                    st.rerun()
                    
            with nav_col2:
                st.write("")
                
            with nav_col3:
                is_last = (idx == len(filtered_leads) - 1)
                next_label = "Terminer" if is_last else "Terminer et Suivant"
                if st.button(next_label, key="next_lead_btn"):
                    if not is_last:
                        st.session_state.quick_call_index += 1
                        st.rerun()
                    else:
                        st.success("Tous les leads filtres ont ete traites !")

elif page_choice == "Emails Professionnels":
    st.markdown("### Liste des Emails Professionnels")
    
    # Reload email helper
    def db_update_email(client, email_val, update_fields):
        try:
            client.table("company_emails").update(update_fields).eq("email", email_val).execute()
        except Exception as e:
            print(f"Background Email DB Update Failed: {e}")

    emails_list = st.session_state.emails
    total_emails = len(emails_list)
    contacted_count = sum(1 for e in emails_list if e.get("contacted"))
    replied_count = sum(1 for e in emails_list if e.get("replied"))
    
    st.markdown("#### Statistiques")
    e_col1, e_col2, e_col3 = st.columns(3)
    e_col1.metric(label="Total Emails", value=total_emails)
    e_col2.metric(label="Emails Contactes", value=contacted_count)
    e_col3.metric(label="Emails Repondus", value=replied_count)
    
    filtered_emails = []
    for e in emails_list:
        if search_email and search_email.lower() not in e.get("email", "").lower():
            continue
        stage = e.get("stage", "start") or "start"
        if email_stage_filter != "Tous" and stage != email_stage_filter:
            continue
        is_cont = e.get("contacted", False)
        if email_contacted_filter == "Oui" and not is_cont:
            continue
        elif email_contacted_filter == "Non" and is_cont:
            continue
        is_rep = e.get("replied", False)
        if email_replied_filter == "Oui" and not is_rep:
            continue
        elif email_replied_filter == "Non" and is_rep:
            continue
        filtered_emails.append(e)
        
    st.write(f"Affichage de {len(filtered_emails)} email(s) filtre(s)")
    
    items_per_page = 20
    total_items = len(filtered_emails)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    
    st.sidebar.markdown("---")
    page_number = st.sidebar.number_input(
        "Page Emails",
        min_value=1,
        max_value=total_pages,
        value=1,
        step=1
    )
    
    current_page = min(page_number, total_pages)
    start_idx = (current_page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    emails_page = filtered_emails[start_idx:end_idx]
    
    if not emails_page:
        st.info("Aucun email ne correspond aux filtres actuels.")
    else:
        # Table Header
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2.5, 1.5, 1.2, 0.8, 0.8, 1.5, 1.5])
        col1.write("**Email**")
        col2.write("**Entreprise (ID)**")
        col3.write("**Etape**")
        col4.write("**Contacte**")
        col5.write("**Repondu**")
        col6.write("**Dernier contact**")
        col7.write("**Action**")
        st.markdown("---")
        
        for idx, e in enumerate(emails_page):
            cb_cont_key = f"email_cont_{e.get('email')}_{idx}"
            cb_rep_key = f"email_rep_{e.get('email')}_{idx}"
            sb_stage_key = f"email_stage_{e.get('email')}_{idx}"
            
            row_col1, row_col2, row_col3, row_col4, row_col5, row_col6, row_col7 = st.columns([2.5, 1.5, 1.2, 0.8, 0.8, 1.5, 1.5])
            
            with row_col1:
                st.write(f"{e.get('email')}")
            with row_col2:
                st.text(e.get("company_id") or "N/A")
            with row_col3:
                stages = ["start", "follow-up", "completed"]
                current_stage = e.get("stage", "start")
                if current_stage not in stages:
                    stages.append(current_stage)
                
                selected_stage = st.selectbox(
                    "Etape",
                    options=stages,
                    index=stages.index(current_stage),
                    key=sb_stage_key,
                    label_visibility="collapsed"
                )
                if selected_stage != current_stage:
                    st.session_state.db_executor.submit(db_update_email, supabase, e.get("email"), {"stage": selected_stage})
                    e["stage"] = selected_stage
            with row_col4:
                contacted_val = st.checkbox(
                    "Cont.",
                    value=bool(e.get("contacted", False)),
                    key=cb_cont_key,
                    label_visibility="collapsed"
                )
                if contacted_val != e.get("contacted", False):
                    last_cont = datetime.now(timezone.utc).isoformat() if contacted_val else None
                    st.session_state.db_executor.submit(db_update_email, supabase, e.get("email"), {"contacted": contacted_val, "last_contacted": last_cont})
                    e["contacted"] = contacted_val
                    e["last_contacted"] = last_cont
            with row_col5:
                replied_val = st.checkbox(
                    "Rep.",
                    value=bool(e.get("replied", False)),
                    key=cb_rep_key,
                    label_visibility="collapsed"
                )
                if replied_val != e.get("replied", False):
                    st.session_state.db_executor.submit(db_update_email, supabase, e.get("email"), {"replied": replied_val})
                    e["replied"] = replied_val
            with row_col6:
                last_contact = parse_date(e.get("last_contacted"))
                if e.get("contacted", False):
                    if last_contact:
                        st.text(last_contact.strftime("%Y-%m-%d %H:%M"))
                    else:
                        st.text("Date inconnue")
                else:
                    st.text("Non contacte")
            with row_col7:
                mailto_url = f"mailto:{e.get('email')}?subject=Opportunite%20de%20recrutement"
                st.markdown(f'<a href="{mailto_url}" target="_blank" class="custom-btn" style="padding: 2px 8px; font-size: 12px;">Email</a>', unsafe_allow_html=True)

elif page_choice == "Opportunites d'Emplois":
    st.markdown("### Opportunites d'Emplois")
    
    def db_update_job(client, job_id, update_fields):
        try:
            client.table("job_opportunities").update(update_fields).eq("id", job_id).execute()
        except Exception as e:
            print(f"Background Job DB Update Failed: {e}")

    jobs_list = st.session_state.jobs
    total_jobs = len(jobs_list)
    active_jobs = sum(1 for j in jobs_list if j.get("active", True))
    
    st.markdown("#### Statistiques")
    j_col1, j_col2 = st.columns(2)
    j_col1.metric(label="Total Opportunites", value=total_jobs)
    j_col2.metric(label="Offres Actives", value=active_jobs)
    
    filtered_jobs = []
    for j in jobs_list:
        if search_job:
            title_lower = (j.get("title") or "").lower()
            desc_lower = (j.get("description") or "").lower()
            loc_lower = (j.get("location") or "").lower()
            query_lower = search_job.lower()
            if query_lower not in title_lower and query_lower not in desc_lower and query_lower not in loc_lower:
                continue
        contract_type = (j.get("contract_type") or "").lower()
        if job_contract_filter != "Tous":
            if job_contract_filter.lower() not in contract_type:
                if job_contract_filter == "Remote" and "remote" not in (j.get("location") or "").lower():
                    continue
                elif job_contract_filter != "Remote":
                    continue
        is_act = j.get("active", True)
        if job_active_filter == "Active" and not is_act:
            continue
        elif job_active_filter == "Inactive" and is_act:
            continue
        filtered_jobs.append(j)
        
    st.write(f"Affichage de {len(filtered_jobs)} offre(s) filtre(s)")
    
    items_per_page = 15
    total_items = len(filtered_jobs)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    
    st.sidebar.markdown("---")
    page_number = st.sidebar.number_input(
        "Page Jobs",
        min_value=1,
        max_value=total_pages,
        value=1,
        step=1
    )
    
    current_page = min(page_number, total_pages)
    start_idx = (current_page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    jobs_page = filtered_jobs[start_idx:end_idx]
    
    if not jobs_page:
        st.info("Aucune offre ne correspond aux filtres actuels.")
    else:
        for idx, j in enumerate(jobs_page):
            cb_act_key = f"job_active_{j.get('id')}_{idx}"
            
            with st.expander(f"{j.get('title') or 'Poste Inconnu'} - {j.get('location') or 'Localisation Inconnue'}"):
                col1, col2, col3 = st.columns([2, 2, 2])
                with col1:
                    st.write(f"Contrat : **{j.get('contract_type') or 'Non precise'}**")
                    st.write(f"Remuneration : **{j.get('salary') or 'Non precise'}**")
                with col2:
                    st.write(f"Source : **{j.get('source_provider') or 'Inconnue'}**")
                    pub_date = parse_date(j.get("pub_date"))
                    if pub_date:
                        st.write(f"Publie le : **{pub_date.strftime('%Y-%m-%d')}**")
                    else:
                        st.write("Publie le : **Date inconnue**")
                with col3:
                    active_val = st.checkbox(
                        "Offre Active",
                        value=bool(j.get("active", True)),
                        key=cb_act_key
                    )
                    if active_val != j.get("active", True):
                        st.session_state.db_executor.submit(db_update_job, supabase, j.get("id"), {"active": active_val})
                        j["active"] = active_val
                
                desc = j.get("description")
                if desc:
                    st.markdown("**Description du poste :**")
                    st.text_area(label="Description complete", value=desc, height=150, disabled=True, key=f"job_desc_{j.get('id')}_{idx}", label_visibility="collapsed")
                
                apply_url = j.get("apply_url")
                if apply_url:
                    clean_url = apply_url if apply_url.startswith(("http://", "https://")) else f"https://{apply_url}"
                    st.markdown(f'<a href="{clean_url}" target="_blank" class="custom-btn" style="width: auto; display: inline-block; margin-top: 10px;">Voir l\'offre / Postuler</a>', unsafe_allow_html=True)

elif page_choice == "Modeles de Messages":
    st.markdown("### Gestion des Modeles de Messages")
    
    templates_list = st.session_state.templates
    st.write(f"Il y a actuellement {len(templates_list)} modele(s) de message enregistre(s).")
    
    st.markdown("#### Ajouter un nouveau modele")
    new_template_text = st.text_area("Contenu du message (utilisez [Nom_Entreprise] ou [Entreprise] comme espace reserve)", key="new_template_input_area")
    
    if st.button("Ajouter le modele", key="btn_add_template"):
        if new_template_text.strip():
            try:
                supabase.table("messages_templates").insert({"content": new_template_text.strip()}).execute()
                st.success("Modele ajoute avec succes !")
                load_page_data(force=True)
                st.rerun()
            except Exception as e:
                st.error(f"Erreur lors de l'ajout : {e}")
        else:
            st.warning("Le modele ne peut pas etre vide.")
            
    st.markdown("#### Modeles existants")
    if not templates_list:
        st.info("Aucun modele n'est enregistre dans la base de donnees.")
    else:
        for idx, t in enumerate(templates_list):
            with st.expander(f"Modele ID: {t.get('id')} - Apercu: {t.get('content')[:50]}..."):
                st.text_area("Contenu du modele", value=t.get("content"), key=f"temp_content_{t.get('id')}_{idx}", disabled=True, label_visibility="collapsed")
                
                col1, col2 = st.columns([2, 10])
                with col1:
                    if st.button("Utiliser", key=f"use_temp_{t.get('id')}_{idx}"):
                        st.session_state.whatsapp_template = t.get("content")
                        st.success("Ce modele est maintenant utilise pour le bouton WhatsApp !")
                        st.rerun()
                with col2:
                    if st.button("Supprimer", key=f"del_temp_{t.get('id')}_{idx}"):
                        try:
                            supabase.table("messages_templates").delete().eq("id", t.get("id")).execute()
                            st.success("Modele supprime avec succes !")
                            load_page_data(force=True)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur lors de la suppression : {e}")

# Override table view
else:
    st.markdown(f"### Donnees de la table : {st.session_state.table_name}")
    custom_data = st.session_state.get("custom_table_data", [])
    st.write(f"Affichage de {len(custom_data)} ligne(s)")
    st.dataframe(custom_data)

# Update URL query parameters on every run to persist current page state
set_query_param("db_choice", db_choice)
set_query_param("page_choice", page_choice)
if "quick_call_index" in st.session_state:
    set_query_param("quick_call_index", st.session_state.quick_call_index)
if "view_mode" in st.session_state:
    set_query_param("view_mode", st.session_state.view_mode)