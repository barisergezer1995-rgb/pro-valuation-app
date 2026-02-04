import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
import requests

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Terapi", page_icon="🧘", layout="wide")

# --- BAŞLIK ---
st.title("🧘 Amınoğlu Terapi Modu (v19.0)")
st.markdown("""
**Logaritmik Sönümleme:** * Çok uçuk kârları tıraşlar (Absürtlüğü önler).
* Derin zararları yumuşatır (Moral bozmaz).
* **Amaç:** Gerçekçi ve sindirilebilir rakamlar.
""")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("🔍 Analiz")
    ticker = st.text_input("Hisse Sembolü", value="THYAO.IS").upper()
    
    st.markdown("---")
    st.subheader("🔑 API Ayarları")
    default_key = "XcQER6LvWluszHZVly18nqMMxz8Xj1GO"
    api_key = st.text_input("FMP API Key", value=default_key, type="password")
    
    st.success("Mod: **TERAPİ** (Kalp Dostu Matematik)")

# --- YARDIMCI ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- PSİKOLOJİK FREN FONKSİYONU ---
def apply_therapy(raw_upside):
    """
    Hem kârı hem zararı logaritmik olarak sıkıştırır.
    Örnek: %300 -> %138 | -%90 -> -%65
    """
    if raw_upside >= 0:
        # Kârda Logaritmik Fren (ln(1 + x))
        # Örn: %100 (1.0) -> ln(2) = 0.69 (%69)
        # Örn: %500 (5.0) -> ln(6) = 1.79 (%179) -> Uçuk rakamı indirir.
        # Ama küçük rakamları (örn %10) çok öldürmesin diye 1.2 ile çarpalım.
        damped = np.log1p(raw_upside) * 1.2
        return damped
    else:
        # Zararda Logaritmik Yastık
        # Örn: -%90 (0.9) -> ln(1.9) = 0.64 -> -%64
        abs_loss = abs(raw_upside)
        damped = np.log1p(abs_loss)
        return -damped

# --- VERİ ÇEKME (HİBRİT) ---
def get_data_hybrid(symbol, key):
    if ".IS" in symbol: return get_data_yahoo(symbol)
    data, err = get_data_fmp(symbol, key)
    if data: return data, None
    return get_data_yahoo(symbol)

def get_data_fmp(symbol, key):
    BASE_URL = "https://financialmodelingprep.com/stable"
    try:
        res = requests.get(f"{BASE_URL}/quote?symbol={symbol}&apikey={key}", timeout=2).json()
        if not res: return None, "Bulunamadı"
        quote = res[0]
        
        prof = requests.get(f"{BASE_URL}/profile?symbol={symbol}&apikey={key}").json()[0]
        inc = requests.get(f"{BASE_URL}/income-statement?symbol={symbol}&limit=1&apikey={key}").json()[0]
        bal = requests.get(f"{BASE_URL}/balance-sheet-statement?symbol={symbol}&limit=1&apikey={key}").json()[0]

        data = {
            'source': 'FMP (Resmi)',
            'ticker': symbol,
            'currency': prof.get('currency', 'USD'),
            'current_price': safe_float(quote.get('price')),
            'shares': safe_float(quote.get('marketCap')) / safe_float(quote.get('price')) / 1e6,
            'total_debt': safe_float(bal.get('totalDebt')) / 1e6,
            'cash': safe_float(bal.get('cashAndCashEquivalents')) / 1e6,
            'revenue': safe_float(inc.get('revenue')) / 1e6,
            'ebit': safe_float(inc.get('operatingIncome')) / 1e6,
        }
        data['ebit_margin'] = data['ebit'] / data['revenue'] if data['revenue'] else 0.15
        return data, None
    except:
        return None, "FMP Hatası"

def get_data_yahoo(symbol):
    try:
        s = yf.Ticker(symbol)
        p = s.fast_info.get('last_price', None)
        if not p:
            h = s.history(period="1d")
            p = h['Close'].iloc[-1] if not h.empty else None
        
        if not p: return None, "Fiyat Yok"
            
        try:
            bs = s.balance_sheet
            ist = s.financials
            debt = safe_float(bs.iloc[:,0].get('Total Debt'))/1e6 if not bs.empty else 0
            cash = safe_float(bs.iloc[:,0].get('Cash And Cash Equivalents'))/1e6 if not bs.empty else 0
            rev = safe_float(ist.iloc[:,0].get('Total Revenue'))/1e6 if not ist.empty else 0
            ebit = safe_float(ist.iloc[:,0].get('EBIT'))/1e6 if not ist.empty else 0
            if ebit==0: ebit = safe_float(ist.iloc[:,0].get('Operating Income'))/1e6
        except:
            debt, cash, rev, ebit = 0, 0, 0, 0
            
        data = {
            'source': 'Yahoo (Yedek)',
            'ticker': symbol,
            'currency': s.fast_info.get('currency', 'TRY' if ".IS" in symbol else 'USD'),
            'current_price': safe_float(p),
            'shares': safe_float(s.fast_info.get('shares', 1e6))/1e6,
            'total_debt': debt, 'cash': cash, 'revenue': rev, 'ebit': ebit,
            'ebit_margin': ebit/rev if rev else 0.15
        }
        return data, None
    except:
        return None, "Yahoo Hatası"

# --- HESAPLAMA (İyimser Temelli + Terapi Freni) ---
def calculate_therapy_mode(data):
    # Temel olarak "İyimser" motoru kullanalım (Moral düzgün olsun)
    # Ama God Mode kadar da uçuk olmasın.
    
    if data['currency'] == 'TRY':
        wacc = 0.20 # TR için makul iyimser
        perpetual_g = 0.15 # Büyüme
    else:
        wacc = 0.08 # ABD için %8
        perpetual_g = 0.04
        
    # Yatırım Oranı (Dengeli)
    reinvestment_rate = 0.15 
    
    years = 10
    current_margin = data.get('ebit_margin', 0.15)
    target_margin = max(current_margin, 0.18) 
    
    margins = np.linspace(current_margin, target_margin, years)
    growth_rates = np.linspace(0.15 if data['currency']=='TRY' else 0.10, perpetual_g, years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(years):
        rev = last_rev * (1 + growth_rates[i])
        nopat = rev * margins[i] * 0.80 # %20 vergi düş
        fcff = nopat * (1 - reinvestment_rate)
        fcffs.append(fcff)
        last_rev = rev
        
    term_val = fcffs[-1] * (1+perpetual_g) / (wacc - perpetual_g)
    pv = np.sum([f / ((1+wacc)**(i+1)) for i, f in enumerate(fcffs)]) + (term_val / ((1+wacc)**years))
    
    equity = pv - data['total_debt'] + data['cash']
    raw_dcf_price = equity / data['shares']
    if raw_dcf_price < 0: raw_dcf_price = 0.01

    # --- TERAPİ ZAMANI (MATEMATİKSEL DÜZELTME) ---
    raw_upside = (raw_dcf_price / data['current_price']) - 1
    
    # Fren uygula
    damped_upside = apply_therapy(raw_upside)
    
    # Yeni "Hissedilen" Fiyatı Hesapla
    therapy_price = data['current_price'] * (1 + damped_upside)
    
    return therapy_price, raw_dcf_price, damped_upside, fcffs

# --- EKRAN ---
if st.button("ANALİZ ET", type="primary"):
    with st.spinner('Rakamlar yumuşatılıyor...'):
        data, err = get_data_hybrid(ticker, api_key)
        
        if data:
            therapy_price, raw_price, final_upside, flows = calculate_therapy_mode(data)
            
            st.success(f"✅ Kaynak: **{data['source']}**")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} {data['currency']}")
            c2.metric("Terapi Değeri", f"{therapy_price:.2f} {data['currency']}", help="Aşırı uçlar törpülendi.")
            
            # Renklendirme
            color = "normal" if final_upside > 0 else "inverse"
            c3.metric("Potansiyel", f"%{final_upside*100:.1f}", delta_color=color)
            
            st.markdown("---")
            st.caption("Matematiksel Müdahale Raporu:")
            
            k1, k2 = st.columns(2)
            raw_up = (raw_price / data['current_price']) - 1
            k1.metric("Frensiz (Ham) Potansiyel", f"%{raw_up*100:.1f}", help="Matematiksel fren olmasaydı çıkacak sonuç.")
            k2.metric("Uygulanan Fren", f"{'Logaritmik Sönümleme' if abs(raw_up) > 0.5 else 'Standart'}")
            
            st.bar_chart(flows)
            
            if final_upside < -0.50:
                st.warning("⚠️ Şirket finansalları çok zayıf ama matematiksel olarak zararı yumuşattık. Yine de dikkatli ol.")
            elif final_upside > 0.50:
                st.success("🚀 Harika bir potansiyel var, uçuk rakamları törpülesek bile hala çok kârlı görünüyor.")

        else:
            st.error("Veri Yok. Manuel Giriş Yapınız.")
            with st.expander("Manuel Giriş", expanded=True):
                 with st.form("manual"):
                    c1, c2 = st.columns(2)
                    m_price = c1.number_input("Fiyat", value=100.0)
                    m_shares = c2.number_input("Hisse (Milyon)", value=100.0)
                    m_rev = c1.number_input("Ciro (Milyon)", value=10000.0)
                    m_ebit = c2.number_input("EBIT", value=3000.0)
                    m_debt = c1.number_input("Borç", value=1000.0)
                    m_cash = c2.number_input("Nakit", value=500.0)
                    if st.form_submit_button("HESAPLA"):
                         pass
