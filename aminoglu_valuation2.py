import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Pro V12", page_icon="🏛️", layout="wide")

# --- BAŞLIK ---
st.title("🏛️ Amınoğlu Pro Değerleme (v12.0 - Stable)")
st.markdown("FMP **Stable** API entegreli. En güncel dokümantasyona uygun yapı.")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("🔍 Analiz")
    ticker = st.text_input("Hisse Sembolü", value="AAPL").upper()
    
    st.markdown("---")
    st.subheader("🔑 API Ayarları")
    # Senin paylaştığın API Key
    default_key = "XcQER6LvWluszHZVly18nqMMxz8Xj1GO"
    api_key = st.text_input("FMP API Key", value=default_key, type="password")
    st.caption("Not: BIST (.IS) hisselerinde API kullanılmaz, Yahoo devreye girer.")

# --- YARDIMCI ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- 1. KAYNAK: FMP STABLE API (DÜZELTİLMİŞ) ---
def get_data_fmp(symbol, key):
    # DÜZELTME: Kullanıcının verdiği Stable URL yapısı
    BASE_URL = "https://financialmodelingprep.com/stable"
    
    # BIST Kontrolü
    if ".IS" in symbol:
        return None, "BIST hissesi tespit edildi. Yahoo'ya yönlendiriliyor..."

    try:
        # --- ENDPOINT 1: /quote (Fiyat) ---
        # Stable sürümde genelde parametre ?symbol= şeklinde de olabilir, path olarak da.
        # Dokümantasyon örneğin search için ?query= kullanmış.
        # Biz standart yolu deneyelim: /quote?symbol=AAPL
        
        url_quote = f"{BASE_URL}/quote?symbol={symbol}&apikey={key}"
        res_quote = requests.get(url_quote, timeout=3)
        
        # HATA KODU KONTROLÜ
        if res_quote.status_code == 403:
            return None, "HATA 403: API Anahtarı geçersiz veya yetkisiz."
        if res_quote.status_code == 429:
            return None, "HATA 429: Günlük istek limitiniz doldu."
        
        quote_data = res_quote.json()
        if not quote_data: return None, "Sembol FMP'de bulunamadı."
        quote = quote_data[0]

        # --- ENDPOINT 2: /profile (Şirket Bilgisi) ---
        url_profile = f"{BASE_URL}/profile?symbol={symbol}&apikey={key}"
        profile = requests.get(url_profile).json()[0]

        # --- ENDPOINT 3: /income-statement (Gelir Tablosu) ---
        url_inc = f"{BASE_URL}/income-statement?symbol={symbol}&limit=1&apikey={key}"
        inc = requests.get(url_inc).json()[0]

        # --- ENDPOINT 4: /balance-sheet-statement (Bilanço) ---
        url_bal = f"{BASE_URL}/balance-sheet-statement?symbol={symbol}&limit=1&apikey={key}"
        bal = requests.get(url_bal).json()[0]

        # --- VERİ PAKETLEME ---
        data = {
            'source': 'FMP (Stable API)',
            'ticker': symbol,
            'currency': profile.get('currency', 'USD'),
            'current_price': safe_float(quote.get('price')),
            'shares': safe_float(quote.get('marketCap')) / safe_float(quote.get('price')) / 1e6,
            
            # Profil Verileri
            'beta': safe_float(profile.get('beta', 1.0)),
            'age': datetime.datetime.now().year - int(profile.get('ipoDate', '2000-01-01').split('-')[0]),
            'revenue_growth': 0.08, 

            # Finansallar (Milyon $)
            'total_debt': safe_float(bal.get('totalDebt')) / 1e6,
            'cash': safe_float(bal.get('cashAndCashEquivalents')) / 1e6,
            'revenue': safe_float(inc.get('revenue')) / 1e6,
            'ebit': safe_float(inc.get('operatingIncome')) / 1e6,
        }
        
        # Marj Hesabı
        if data['revenue'] > 0:
            data['ebit_margin'] = data['ebit'] / data['revenue']
        else:
            data['ebit_margin'] = 0.15

        return data, None

    except Exception as e:
        return None, f"FMP Bağlantı Hatası: {str(e)}"

# --- 2. KAYNAK: YAHOO FINANCE (Yedek & BIST) ---
def get_data_yahoo(symbol):
    try:
        stock = yf.Ticker(symbol)
        
        # Hızlı Fiyat
        current_price = stock.fast_info.get('last_price', None)
        if not current_price: 
            hist = stock.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
            else:
                return None, "Fiyat çekilemedi."

        # Finansallar
        try:
            bs = stock.balance_sheet
            is_stmt = stock.financials
            
            total_debt = safe_float(bs.iloc[:, 0].get('Total Debt')) / 1e6 if not bs.empty else 0
            cash = safe_float(bs.iloc[:, 0].get('Cash And Cash Equivalents')) / 1e6 if not bs.empty else 0
            revenue = safe_float(is_stmt.iloc[:, 0].get('Total Revenue')) / 1e6 if not is_stmt.empty else 0
            ebit = safe_float(is_stmt.iloc[:, 0].get('EBIT')) / 1e6 if not is_stmt.empty else 0
            
            if ebit == 0: 
                 ebit = safe_float(is_stmt.iloc[:, 0].get('Operating Income')) / 1e6
        except:
             return None, "Finansal tablolar okunamadı (Yahoo Ban)."

        data = {
            'source': 'Yahoo Finance',
            'ticker': symbol,
            'currency': stock.fast_info.get('currency', 'TRY' if ".IS" in symbol else 'USD'),
            'current_price': safe_float(current_price),
            'shares': safe_float(stock.fast_info.get('shares', 0)) / 1e6,
            'beta': 1.0, 
            'age': 15,
            'revenue_growth': 0.05,
            'total_debt': total_debt, 'cash': cash, 'revenue': revenue, 'ebit': ebit,
        }
        
        if data['revenue'] > 0:
            data['ebit_margin'] = data['ebit'] / data['revenue']
        else:
            data['ebit_margin'] = 0.15
            
        return data, None

    except Exception as e:
        return None, f"Yahoo Hatası: {str(e)}"

# --- 3. AKILLI OTOPİLOT HESAPLAMA ---
def autopilot_calculate(data):
    age = data.get('age', 15)
    beta = data.get('beta', 1.0)
    
    # PROFİL
    if (age > 15) and (beta < 0.9): 
        profile = "🐄 NAKİT İNEĞİ (Cash Cow)"
        forecast_years = 7
        perpetual_g = 0.025
        reinvestment_rate = 0.05
        target_wacc_cap = 0.08
        used_beta = min(beta, 0.75) 
    elif (beta > 1.3) or (age < 10): 
        profile = "🚀 ROKET (High Growth)"
        forecast_years = 15
        perpetual_g = 0.035
        reinvestment_rate = 0.50
        target_wacc_cap = 0.12
        used_beta = max(beta, 1.2)
    else: 
        profile = "🏭 STANDART SANAYİ"
        forecast_years = 10
        perpetual_g = 0.030
        reinvestment_rate = 0.25
        target_wacc_cap = 0.10
        used_beta = beta

    # WACC
    rf = 0.04
    rm = 0.05
    if data['currency'] == 'TRY':
        rf = 0.25 
        target_wacc_cap = 0.35 
        perpetual_g = 0.15 
    
    cost_equity = rf + used_beta * rm
    
    market_cap = data['shares'] * data['current_price']
    total_val = market_cap + data['total_debt']
    if total_val <= 0: total_val = market_cap if market_cap > 0 else 1.0
    
    w_e = market_cap / total_val
    w_d = data['total_debt'] / total_val
    
    tax_rate = 0.25 if data['currency'] == 'TRY' else 0.21
    cost_debt = 0.35 if data['currency'] == 'TRY' else 0.06
    
    wacc = (w_e * cost_equity) + (w_d * cost_debt * (1 - tax_rate))
    
    if data['currency'] != 'TRY':
        wacc = max(0.06, min(wacc, target_wacc_cap))
    
    if perpetual_g >= wacc: perpetual_g = wacc - 0.005

    # DCF
    margins = np.linspace(data.get('ebit_margin', 0.15), 0.15, forecast_years)
    growth = np.linspace(0.10, perpetual_g, forecast_years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(forecast_years):
        rev = last_rev * (1 + growth[i])
        nopat = rev * margins[i] * (1-tax_rate)
        fcff = nopat * (1 - reinvestment_rate)
        fcffs.append(fcff)
        last_rev = rev
        
    term_val = fcffs[-1] * (1+perpetual_g) / (wacc - perpetual_g)
    pv = np.sum([f / ((1+wacc)**(i+1)) for i, f in enumerate(fcffs)]) + (term_val / ((1+wacc)**forecast_years))
    
    equity = pv - data['total_debt'] + data['cash']
    price = equity / data['shares']
    if price < 0: price = 0
    
    decisions = {"profile": profile, "wacc": wacc, "g": perpetual_g, "reinv": reinvestment_rate}
    return price, fcffs, decisions

# --- EKRAN ---
if st.button("ANALİZ ET", type="primary"):
    data = None
    log_msg = ""

    with st.spinner('FMP Stable API ile veriler çekiliyor...'):
        # 1. ROTA: FMP
        if ".IS" not in ticker:
            data, error = get_data_fmp(ticker, api_key)
            if error: log_msg += f"FMP Mesajı: {error} \n"
        
        # 2. ROTA: YAHOO
        if not data:
            if ".IS" in ticker: log_msg += "Türk hissesi -> Yahoo devreye girdi.\n"
            else: log_msg += "FMP yanıt vermedi -> Yahoo devreye girdi.\n"
            data, error_y = get_data_yahoo(ticker)
            if error_y: log_msg += f"Yahoo Hatası: {error_y}"

    # SONUÇ EKRANI
    if data:
        price, flows, dec = autopilot_calculate(data)
        
        if "FMP" in data['source']: st.success(f"✅ Kaynak: **{data['source']}**")
        else: st.warning(f"⚠️ Kaynak: **{data['source']}**")
        
        st.info(f"🧬 Profil: **{dec['profile']}**")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Fiyat", f"{data['current_price']:.2f} {data['currency']}")
        c2.metric("Otopilot Değeri", f"{price:.2f} {data['currency']}")
        
        upside = (price / data['current_price']) - 1 if data['current_price'] else 0
        c3.metric("Potansiyel", f"%{upside*100:.1f}", delta_color="normal" if upside > 0 else "inverse")
        
        with st.expander("Şeffaflık Raporu"):
            st.write(f"- WACC: %{dec['wacc']*100:.2f}")
            st.write(f"- Büyüme: %{dec['g']*100:.2f}")
            st.write(f"- Yatırım Oranı: %{dec['reinv']*100:.0f}")
            if log_msg: st.code(log_msg)
            
        st.bar_chart(flows)

    else:
        st.error("❌ Veri çekilemedi.")
        if log_msg: st.warning(f"Sistem Kayıtları:\n{log_msg}")
        
        with st.expander("📝 Manuel Giriş Yap", expanded=True):
            with st.form("manual"):
                c1, c2 = st.columns(2)
                m_price = c1.number_input("Fiyat", value=100.0)
                m_shares = c2.number_input("Hisse Adedi (Milyon)", value=100.0)
                m_rev = c1.number_input("Ciro (Milyon)", value=10000.0)
                m_ebit = c2.number_input("EBIT", value=2000.0)
                m_debt = c1.number_input("Borç", value=1000.0)
                m_cash = c2.number_input("Nakit", value=500.0)
                
                if st.form_submit_button("HESAPLA"):
                    st.info("Manuel hesaplama özelliği eklenebilir.")
