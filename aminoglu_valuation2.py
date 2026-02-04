import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Ultra Boğa", page_icon="🚀", layout="wide")

# --- BAŞLIK ---
st.title("🚀 Amınoğlu Ultra Boğa (v13.0)")
st.markdown("İyimser, Frensiz ve Hızlı. **Hedef: Ayı piyasasını bitirmek.**")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("🔍 Analiz")
    ticker = st.text_input("Hisse Sembolü", value="THYAO.IS").upper()
    
    st.markdown("---")
    st.subheader("🔑 API Ayarları")
    default_key = "XcQER6LvWluszHZVly18nqMMxz8Xj1GO"
    api_key = st.text_input("FMP API Key", value=default_key, type="password")
    
    st.success("Mod: **ULTRA BOĞA** (İyimser Varsayımlar Aktif)")

# --- YARDIMCI ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- 1. KAYNAK: FMP STABLE API ---
def get_data_fmp(symbol, key):
    BASE_URL = "https://financialmodelingprep.com/stable"
    
    # Sadece .IS değil, FMP'de olmayan her şeyi Yahoo'ya salalım
    # (Genelde FMP sadece US stocks için iyidir)
    if "." in symbol and ".IS" in symbol: 
        return None, "Yerel borsa tespiti -> Yahoo'ya yönlendiriliyor."

    try:
        url_quote = f"{BASE_URL}/quote?symbol={symbol}&apikey={key}"
        res_quote = requests.get(url_quote, timeout=2)
        
        if res_quote.status_code != 200: return None, "API Hatası"
        
        quote_data = res_quote.json()
        if not quote_data: return None, "Bulunamadı"
        quote = quote_data[0]

        url_profile = f"{BASE_URL}/profile?symbol={symbol}&apikey={key}"
        prof_res = requests.get(url_profile).json()
        profile = prof_res[0] if prof_res else {}

        url_inc = f"{BASE_URL}/income-statement?symbol={symbol}&limit=1&apikey={key}"
        url_bal = f"{BASE_URL}/balance-sheet-statement?symbol={symbol}&limit=1&apikey={key}"
        
        inc = requests.get(url_inc).json()[0]
        bal = requests.get(url_bal).json()[0]

        data = {
            'source': 'FMP (Resmi)',
            'ticker': symbol,
            'currency': profile.get('currency', 'USD'),
            'current_price': safe_float(quote.get('price')),
            'shares': safe_float(quote.get('marketCap')) / safe_float(quote.get('price')) / 1e6,
            'beta': safe_float(profile.get('beta', 1.1)), # Beta yoksa 1.1 al (Agresif)
            'age': 20, # Varsayılan
            'revenue_growth': 0.10, # Varsayılan büyüme yüksek
            'total_debt': safe_float(bal.get('totalDebt')) / 1e6,
            'cash': safe_float(bal.get('cashAndCashEquivalents')) / 1e6,
            'revenue': safe_float(inc.get('revenue')) / 1e6,
            'ebit': safe_float(inc.get('operatingIncome')) / 1e6,
        }
        
        if data['revenue'] > 0:
            data['ebit_margin'] = data['ebit'] / data['revenue']
        else:
            data['ebit_margin'] = 0.20 # Gelir yoksa yüksek marj

        return data, None

    except:
        return None, "FMP Bağlantı Hatası"

# --- 2. KAYNAK: YAHOO FINANCE (Yedek & Tüm Dünya) ---
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
                return None, "Fiyat Yok"

        try:
            bs = stock.balance_sheet
            is_stmt = stock.financials
            
            # Veri yoksa 0 dön, manuel doldurturuz
            total_debt = safe_float(bs.iloc[:, 0].get('Total Debt')) / 1e6 if not bs.empty else 0
            cash = safe_float(bs.iloc[:, 0].get('Cash And Cash Equivalents')) / 1e6 if not bs.empty else 0
            revenue = safe_float(is_stmt.iloc[:, 0].get('Total Revenue')) / 1e6 if not is_stmt.empty else 0
            
            # EBIT yoksa Operating Income, o da yoksa Gross Profit (Abartalım)
            ebit = safe_float(is_stmt.iloc[:, 0].get('EBIT')) / 1e6 if not is_stmt.empty else 0
            if ebit == 0: 
                 ebit = safe_float(is_stmt.iloc[:, 0].get('Operating Income')) / 1e6
        except:
             return None, "Tablo Hatası"

        data = {
            'source': 'Yahoo (Global)',
            'ticker': symbol,
            'currency': stock.fast_info.get('currency', 'USD'),
            'current_price': safe_float(current_price),
            'shares': safe_float(stock.fast_info.get('shares', 0)) / 1e6,
            'beta': 1.0, 
            'age': 15,
            'revenue_growth': 0.10, # İyimser varsayılan
            'total_debt': total_debt, 'cash': cash, 'revenue': revenue, 'ebit': ebit,
        }
        
        if data['revenue'] > 0:
            data['ebit_margin'] = data['ebit'] / data['revenue']
        else:
            data['ebit_margin'] = 0.20
            
        return data, None

    except Exception as e:
        return None, str(e)

# --- 3. ULTRA BOĞA HESAPLAMA MOTORU ---
def autopilot_calculate_bull(data):
    # Bu motor "Şirket batmaz, sonsuza kadar büyür" varsayımıyla çalışır.
    
    # PROFİL BELİRLEME (Hepsi iyi şirket varsayımı)
    beta = data.get('beta', 1.0)
    if beta > 2.0: beta = 1.5 # Çok riskli görünüyorsa riskini manuel düşür
    
    # 1. WACC (İskonto Oranı) - DÜŞÜK TUTUYORUZ
    # Faizler ne olursa olsun, biz %4 risksiz faiz alıyoruz.
    rf = 0.04 
    rm = 0.05 
    
    # TR ise enflasyon var ama yine de WACC'ı boğmayalım
    if data['currency'] == 'TRY':
        rf = 0.15 # %15 (Reel faiz kafası)
        target_wacc = 0.20 # %20 ile sınırlayalım
    else:
        target_wacc = 0.08 # ABD için %8 (Çok iyi oran)

    cost_equity = rf + (beta * rm)
    
    market_cap = data['shares'] * data['current_price']
    total_val = market_cap + data['total_debt']
    if total_val <= 0: total_val = market_cap if market_cap > 0 else 1.0
    
    w_e = market_cap / total_val
    w_d = data['total_debt'] / total_val
    
    # Vergi avantajını kullanalım
    wacc = (w_e * cost_equity) + (w_d * 0.05 * (1 - 0.20))
    
    # BOĞA MÜDAHALESİ: WACC çok yüksekse aşağı çek
    if data['currency'] == 'TRY':
        wacc = min(wacc, 0.25) # TR için tavan %25
    else:
        wacc = max(0.06, min(wacc, 0.09)) # ABD için %6-%9 arası (Hisse dostu)

    # 2. BÜYÜME (g) - YÜKSEK TUTUYORUZ
    # Sonsuz büyüme WACC'ın hemen dibinde olsun ki değer uçsun.
    perpetual_g = wacc - 0.015 # %1.5 marj (Çok agresif)
    
    # 3. YATIRIM ORANI (Reinvestment) - DÜŞÜK TUTUYORUZ
    # Şirket parasını yatırıma gömmesin, nakit üretsin.
    reinvestment_rate = 0.10 # %10 (Çok düşük)
    
    # 4. PROJEKSİYON
    years = 10
    
    # Marj İyileştirmesi: Mevcut marj düşükse %20'ye çıksın
    current_margin = data.get('ebit_margin', 0.15)
    target_margin = max(current_margin, 0.20)
    
    margins = np.linspace(current_margin, target_margin, years)
    growth_rates = np.linspace(0.12, perpetual_g, years) # İlk yıllar %12 büyüme
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(years):
        rev = last_rev * (1 + growth_rates[i])
        nopat = rev * margins[i] * (1 - 0.20) # Vergi %20
        
        # Yatırım az -> Nakit Çok
        fcff = nopat * (1 - reinvestment_rate)
        fcffs.append(fcff)
        last_rev = rev
        
    # Değerleme
    term_val = fcffs[-1] * (1+perpetual_g) / (wacc - perpetual_g)
    pv = np.sum([f / ((1+wacc)**(i+1)) for i, f in enumerate(fcffs)]) + (term_val / ((1+wacc)**years))
    
    equity = pv - data['total_debt'] + data['cash']
    price = equity / data['shares']
    if price < 0: price = 0.01 # Negatif çıkmasın
    
    decisions = {
        "profile": "🐂 BOĞA MODU", 
        "wacc": wacc, 
        "g": perpetual_g, 
        "reinv": reinvestment_rate
    }
    return price, fcffs, decisions

# --- EKRAN ---
if st.button("ANALİZ ET (BOĞA)", type="primary"):
    data = None
    log_msg = ""

    with st.spinner('Piyasa taranıyor...'):
        # 1. ROTA: FMP
        data, error = get_data_fmp(ticker, api_key)
        if error: log_msg += f"FMP: {error}\n"
        
        # 2. ROTA: YAHOO (Bulamadıysa veya Hata Verdiyse)
        if not data:
            log_msg += "Yahoo deneniyor...\n"
            data, error_y = get_data_yahoo(ticker)
            if error_y: log_msg += f"Yahoo: {error_y}"

    # SONUÇ
    if data:
        price, flows, dec = autopilot_calculate_bull(data)
        
        # Kaynak Bilgisi
        source_color = "green" if "FMP" in data['source'] else "orange"
        st.markdown(f":{source_color}[**Veri Kaynağı: {data['source']}**]")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} {data['currency']}")
        c2.metric("Boğa Değeri", f"{price:.2f} {data['currency']}")
        
        upside = (price / data['current_price']) - 1 if data['current_price'] else 0
        c3.metric("Potansiyel", f"%{upside*100:.1f}", delta_color="normal") # Hep yeşil olsun :D
        
        with st.expander("Neden Yüksek Çıktı? (Boğa Ayarları)"):
            st.write(f"- **Düşük Faiz (WACC):** %{dec['wacc']*100:.2f}")
            st.write(f"- **Yüksek Büyüme (g):** %{dec['g']*100:.2f}")
            st.write(f"- **Minimum Yatırım:** Kazancın sadece %{dec['reinv']*100:.0f}'u harcanıyor.")
            if log_msg: st.code(log_msg)
            
        st.bar_chart(flows)

    else:
        st.error("❌ Veri Yok. Manuel Giriş Yapınız.")
        with st.expander("Manuel Giriş", expanded=True):
             with st.form("manual"):
                c1, c2 = st.columns(2)
                m_price = c1.number_input("Fiyat", value=100.0)
                m_shares = c2.number_input("Hisse Adedi (Milyon)", value=100.0)
                m_rev = c1.number_input("Ciro (Milyon)", value=10000.0)
                m_ebit = c2.number_input("EBIT", value=3000.0) # Yüksek EBIT varsay
                m_debt = c1.number_input("Borç", value=1000.0)
                m_cash = c2.number_input("Nakit", value=500.0)
                
                if st.form_submit_button("HESAPLA"):
                    st.info("Hesaplama butonu yukarıda çalışır.")

