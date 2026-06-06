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

# Connexion à Supabase
SUPABASE_URL = None
SUPABASE_KEY = None

# Tentative de chargement via Streamlit Secrets (Community Cloud)
try:
    if "SUPABASE_URL" in st.secrets:
        SUPABASE_URL = st.secrets["SUPABASE_URL"]
    if "SUPABASE_SERVICE_ROLE_KEY" in st.secrets:
        SUPABASE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]
    elif "SERVICE_ROLE" in st.secrets:
        SUPABASE_KEY = st.secrets["SERVICE_ROLE"]
    elif "SUPABASE_KEY" in st.secrets:
        SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    pass

# Repli sur les variables d'environnement locales (.env)
if not SUPABASE_URL:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
if not SUPABASE_KEY:
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SERVICE_ROLE") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Configuration Supabase manquante.")
    st.info("Veuillez configurer SUPABASE_URL et SUPABASE_KEY dans vos secrets Streamlit ou dans votre fichier .env.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Default table name
default_table = os.getenv("SUPABASE_TABLE") or "dataset_5000"
if "table_name" not in st.session_state:
    st.session_state.table_name = default_table

st.set_page_config(page_title="Gestion des Appels Marketing", layout="wide")

# Initialisation du pool d'exécuteurs de base de données asynchrones
if "db_executor" not in st.session_state:
    st.session_state.db_executor = ThreadPoolExecutor(max_workers=1)

def db_update(lead_id, phone_list, table_name):
    try:
        supabase.table(table_name).update({"phone_whatsapp_valides": phone_list}).eq("id", lead_id).execute()
    except Exception as e:
        print(f"Background DB Update Failed: {e}")

def db_update_template(content_val):
    try:
        res = supabase.table("messages_templates").select("id").limit(1).execute()
        if res.data:
            row_id = res.data[0]["id"]
            supabase.table("messages_templates").update({"content": content_val}).eq("id", row_id).execute()
        else:
            supabase.table("messages_templates").insert({"content": content_val}).execute()
    except Exception as e:
        print(f"Background Template Update Failed: {e}")

def get_whatsapp_template():
    try:
        res = supabase.table("messages_templates").select("content").limit(1).execute()
        if res.data and res.data[0].get("content"):
            return res.data[0]["content"]
    except Exception as e:
        print(f"Failed to fetch template from DB: {e}")
    return "Bonjour, je vous contacte au nom de [Nom_Entreprise] suite à votre intérêt pour nos services."

def on_template_change():
    new_template = st.session_state.whatsapp_template_input
    st.session_state.whatsapp_template = new_template
    st.session_state.db_executor.submit(db_update_template, new_template)

# Callbacks pour mise à jour en temps réel (exécutés en arrière-plan sans bloquer l'UI)
def on_wa_change(lead, phone, key):
    new_val = st.session_state[key]
    phone["has_whatsapp"] = new_val
    phone_list_copy = copy.deepcopy(lead["phone_whatsapp_valides"])
    st.session_state.db_executor.submit(db_update, lead["id"], phone_list_copy, st.session_state.table_name)

def on_cont_change(lead, phone, key):
    new_val = st.session_state[key]
    phone["contacted"] = new_val
    if new_val:
        phone["last_contacted"] = datetime.now(timezone.utc).isoformat()
    else:
        phone["last_contacted"] = None
    phone_list_copy = copy.deepcopy(lead["phone_whatsapp_valides"])
    st.session_state.db_executor.submit(db_update, lead["id"], phone_list_copy, st.session_state.table_name)

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
        
    phone_list_copy = copy.deepcopy(lead["phone_whatsapp_valides"])
    st.session_state.db_executor.submit(db_update, lead["id"], phone_list_copy, st.session_state.table_name)

def on_job_click(lead, phone):
    current_val = phone.get("job_obtained", "en attente")
    if current_val == "en attente":
        new_val = "oui"
    elif current_val == "oui":
        new_val = "non"
    else:
        new_val = "en attente"
        
    phone["job_obtained"] = new_val
    phone_list_copy = copy.deepcopy(lead["phone_whatsapp_valides"])
    st.session_state.db_executor.submit(db_update, lead["id"], phone_list_copy, st.session_state.table_name)

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
</style>
""", unsafe_allow_html=True)

st.title("Dashboard d'Appels - Dataset RH")

if st.session_state.get("leads_error"):
    st.error(f"### Erreur de connexion à la table : {st.session_state.table_name}")
    st.info(
        "Veuillez vérifier le nom de la table saisi dans la barre latérale. "
        "Les noms de tables PostgreSQL sont sensibles à la casse (généralement en minuscules).\n\n"
        f"Détail technique : `{st.session_state.leads_error}`"
    )
    st.stop()

# Récupération des données avec cache et pagination pour contourner la limite de 1000 lignes
@st.cache_data(ttl=10)
def get_data(table_name):
    all_data = []
    limit = 1000
    offset = 0
    while True:
        res = supabase.table(table_name).select("id, company, phone_whatsapp_valides").range(offset, offset + limit - 1).execute()
        if not res.data:
            break
        all_data.extend(res.data)
        if len(res.data) < limit:
            break
        offset += limit
    return all_data

# Initialisation du session state
if "leads_error" not in st.session_state:
    st.session_state.leads_error = None

if "leads" not in st.session_state:
    try:
        st.session_state.leads = copy.deepcopy(get_data(st.session_state.table_name))
        st.session_state.leads_error = None
    except Exception as e:
        st.session_state.leads = []
        st.session_state.leads_error = str(e)

if "whatsapp_template" not in st.session_state:
    st.session_state.whatsapp_template = get_whatsapp_template()
if "quick_call_index" not in st.session_state:
    st.session_state.quick_call_index = 0

# Selector for View Mode
view_mode = st.radio(
    "Mode d'affichage",
    options=["Liste complete", "Appel rapide (Un par un)"],
    horizontal=True,
    key="view_mode"
)

# Sidebar pour les filtres et actions de rechargement
st.sidebar.title("Filtres")

if st.sidebar.button("Recharger les donnees"):
    st.cache_data.clear()
    try:
        st.session_state.leads = copy.deepcopy(get_data(st.session_state.table_name))
        st.session_state.leads_error = None
    except Exception as e:
        st.session_state.leads = []
        st.session_state.leads_error = str(e)
    st.session_state.whatsapp_template = get_whatsapp_template()
    st.session_state.quick_call_index = 0
    st.rerun()

# Configuration de la Table
st.sidebar.markdown("---")
st.sidebar.subheader("Configuration Table")

def on_table_change():
    st.cache_data.clear()
    if "leads" in st.session_state:
        del st.session_state["leads"]
    if "leads_error" in st.session_state:
        del st.session_state["leads_error"]
    st.session_state.quick_call_index = 0

table_input = st.sidebar.text_input(
    "Table Supabase",
    value=st.session_state.table_name,
    key="table_input_key",
    on_change=on_table_change
)
st.session_state.table_name = table_input

# Champs de recherche
search_company = st.sidebar.text_input("Rechercher une entreprise", value="")
search_phone = st.sidebar.text_input("Rechercher un numero", value="")

# Filtre Whatsapp
whatsapp_filter = st.sidebar.selectbox(
    "WhatsApp",
    options=["Tous", "Avec WhatsApp", "Sans WhatsApp"]
)

# Filtre Contacte
contacted_filter = st.sidebar.selectbox(
    "Statut de contact",
    options=["Tous", "Contacte", "Non contacte"]
)

# Filtre Call Status
call_status_filter = st.sidebar.selectbox(
    "Statut de l'appel",
    options=["Tous", "to call", "called", "unavailable"]
)

# Filtre Date de dernier contact
date_filter_type = st.sidebar.selectbox(
    "Date de dernier contact",
    options=["Tous", "Depuis une date", "Avant une date", "Pas de date"]
)

filter_date = None
if date_filter_type in ["Depuis une date", "Avant une date"]:
    filter_date = st.sidebar.date_input("Date cible", value=datetime.today().date())

# Filtre Job Obtenu
job_obtained_filter = st.sidebar.selectbox(
    "Job obtenu",
    options=["Tous", "en attente", "oui", "non"]
)

# Bouton de reinitialisation des filtres
if st.sidebar.button("Reinitialiser les filtres"):
    st.rerun()

# Configuration du modèle de message WhatsApp
st.sidebar.markdown("---")
st.sidebar.subheader("Configuration WhatsApp")
whatsapp_template = st.sidebar.text_area(
    "Modèle de message",
    value=st.session_state.whatsapp_template,
    key="whatsapp_template_input",
    on_change=on_template_change
)

# Parseur de date robuste
def parse_date(date_str):
    if not date_str:
        return None
    try:
        clean_str = date_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean_str)
    except Exception:
        return None

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

# Section Statistiques et actions globales
st.markdown("### Statistiques")
m_col1, m_col2, m_col3 = st.columns(3)
with m_col1:
    st.metric(label="Entreprises filtrees", value=len(filtered_leads))
with m_col2:
    total_matching_phones = sum(len(lead["_matching_phones"]) for lead in filtered_leads)
    st.metric(label="Numeros filtres", value=total_matching_phones)
with m_col3:
    total_contacted = sum(1 for lead in filtered_leads for phone in lead["_matching_phones"] if phone.get("contacted"))
    st.metric(label="Numeros contactes", value=total_contacted)

# Rendu en fonction du mode choisi
if view_mode == "Liste complete":
    # Statistiques et Graphiques avancés (Analytics)
    st.markdown("---")
    st.markdown("### Statistiques et Graphiques avancés")
    
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
    with kpi_col1:
        st.metric(
            label="Taux de contactibilité", 
            value=f"{contactability_rate:.1f}%",
            help="Pourcentage d'appels aboutis (called) par rapport au total tenté (called + unavailable)"
        )
    with kpi_col2:
        st.metric(
            label="Volume quotidien", 
            value=f"{calls_today} appel(s) aujourd'hui",
            help="Nombre d'appels passés dans la journée en cours (UTC)"
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
        st.markdown("#### Progression des recrutements (Job obtenu)")
        df_job = pd.DataFrame(
            list(job_counts.items()),
            columns=["Job obtenu", "Nombre"]
        ).set_index("Job obtenu")
        try:
            st.bar_chart(df_job, color="#000000")
        except Exception:
            st.bar_chart(df_job)

    # Pagination
    items_per_page = 20
    total_items = len(filtered_leads)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    
    st.sidebar.markdown("---")
    page_number = st.sidebar.number_input(
        "Page",
        min_value=1,
        max_value=total_pages,
        value=1,
        step=1
    )
    
    current_page = min(page_number, total_pages)
    start_idx = (current_page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    leads_page = filtered_leads[start_idx:end_idx]
    
    st.markdown(f"Affichage des résultats {start_idx + 1} à {end_idx} sur {total_items}")
    
    # Rendu de la liste
    for lead in leads_page:
        matching_phones = lead["_matching_phones"]
        
        with st.expander(f"{lead['company'] or 'Entreprise Inconnue'} (ID: {lead['id']})"):
            for phone in matching_phones:
                orig_index = lead["phone_whatsapp_valides"].index(phone)
                
                col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([1.5, 0.8, 0.8, 1.5, 1.2, 1.2, 1.8, 2.2])
                
                # Format variables for actions
                raw_num = phone.get("number", "")
                clean_num = "".join(c for c in raw_num if c.isdigit() or c == '+')
                tel_url = f"tel:{clean_num}"
                
                # Format WhatsApp message replacing placeholder with company name
                company_placeholder = lead.get("company") or ""
                formatted_msg = whatsapp_template.replace("[Entreprise]", company_placeholder)
                formatted_msg = formatted_msg.replace("[Nom_Entreprise]", company_placeholder)
                encoded_msg = urllib.parse.quote(formatted_msg)
                wa_url = f"https://wa.me/{clean_num}?text={encoded_msg}"
                
                with col1:
                    st.write(f"Numéro : **{phone.get('number', 'N/A')}**")
                    
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
                        "Contacté",
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
                            st.text("Date non définie")
                    else:
                        st.text("Non contacté")
                
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
        # Clamp index
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
        
        # Company Card layout
        st.markdown(f"""
        <div style="padding: 24px; border: 1px solid #E5E5E5; border-radius: 4px; background-color: #F9F9F9; margin-bottom: 24px;">
            <h4 style="margin: 0 0 8px 0; font-family: 'Geist', sans-serif; font-weight: 600; color: #000000;">{lead.get('company') or 'Entreprise Inconnue'}</h4>
            <p style="margin: 0; color: #444444; font-size: 14px;">ID: {lead['id']}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Numbers inside the card
        for phone in matching_phones:
            orig_index = lead["phone_whatsapp_valides"].index(phone)
            
            col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([1.5, 0.8, 0.8, 1.5, 1.2, 1.2, 1.8, 2.2])
            
            # Format variables for actions
            raw_num = phone.get("number", "")
            clean_num = "".join(c for c in raw_num if c.isdigit() or c == '+')
            tel_url = f"tel:{clean_num}"
            
            # Format WhatsApp message replacing placeholder with company name
            company_placeholder = lead.get("company") or ""
            formatted_msg = whatsapp_template.replace("[Entreprise]", company_placeholder)
            formatted_msg = formatted_msg.replace("[Nom_Entreprise]", company_placeholder)
            encoded_msg = urllib.parse.quote(formatted_msg)
            wa_url = f"https://wa.me/{clean_num}?text={encoded_msg}"
            
            with col1:
                st.write(f"Numéro : **{phone.get('number', 'N/A')}**")
                
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
                    "Contacté",
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
                        st.text("Date non définie")
                else:
                    st.text("Non contacté")
                    
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
                    
        # Navigation bottom
        st.markdown("---")
        nav_col1, nav_col2, nav_col3 = st.columns([2, 4, 2])
        
        with nav_col1:
            if st.button("Précédent", disabled=(idx == 0), key="prev_lead_btn"):
                st.session_state.quick_call_index -= 1
                st.rerun()
                
        with nav_col2:
            st.write("")
            
        with nav_col3:
            is_last = (idx == len(filtered_leads) - 1)
            next_label = "Terminer" if is_last else "Terminer & Suivant"
            if st.button(next_label, key="next_lead_btn"):
                if not is_last:
                    st.session_state.quick_call_index += 1
                    st.rerun()
                else:
                    st.success("Tous les leads filtrés ont été traités !")