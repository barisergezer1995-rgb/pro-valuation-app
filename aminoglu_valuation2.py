import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Değerleme", page_icon="🦄", layout="wide")

# --- BAŞLIK ---
st.title("🚀 Amınoğlu Değerleme Motoru (v2.0)")
st.markdown("İskontolanmış Nakit Akışı (DCF) ve Akıllı Startup Analizi")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Parametreler")
    ticker = st.text_input("Hisse Sembolü (Örn: NVDA, UBER, THYAO.IS)", value="UBER").upper()
    
    st.subheader("İnce Ayarlar")
    forecast_years = st.slider("Tahmin Yılı", 3, 10, 5)
    perpetual_growth = st.slider("Sonsuz Büyüme (g)", 1.0, 5.0, 2.5, 0.1) / 100
    wacc_manual = st.checkbox("WACC'ı Manuel Gir")
    
    if wacc_manual:
        wacc_input = st.slider("WACC Oranı (%)", 5.0, 25.0, 10.0, 0.5) / 100
    else:
        wacc_input = None
    
    st.markdown("---")
    st.subheader("🦄 Değerleme Modu")
    
    force_startup = st.checkbox("Startup Modunu Zorla (Manuel)")
    if force_startup:
        sector_multiple = st.slider("Sektör Çarpanı (Price/Sales)", 1.0, 50.0, 5.0, 0.5)
    else:
        sector_multiple = 5.0

# --- FONKSİYONLAR ---
@st.cache_data(ttl=3600)
def get_data(symbol):
    stock = yf.Ticker(symbol)
    
    data = {}
    error_msg = None
    
    try:
        # 1. YÖNTEM: fast_info (Daha az banlanır)
        # Yahoo'nun info endpointi yerine fast_info kullanıyoruz.
        current_price = stock.fast_info.get('last_price', None)
        shares = stock.fast_info.get('shares', None)
        
        if current_price is None:
            # Yedek yöntem: History
            hist = stock.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
            else:
                raise ValueError("Fiyat verisi çekilemedi.")

        # Finansal Tablolar
        bs = stock.balance_sheet
        is_stmt = stock.financials
        
        # Eğer tablolar boş gelirse (Yahoo engeli)
        if bs.empty or is_stmt.empty:
            raise ValueError("Finansal tablolar boş (Yahoo Engeli).")

        # Verileri Doldur
        data['ticker'] = symbol
        data['long_name'] = symbol # İsim bazen gelmez, sembol kalsın
        data['currency'] = "USD" # Varsayılan
        data['current_price'] = current_price
        data['shares'] = shares / 1e6 if shares else 0
        data['beta'] = 1.0 # Beta banlıysa 1.0 al
        
        # Tablolardan veri çekme
        data['total_debt'] = bs.iloc[:, 0].get('Total Debt', 0) / 1e6
        data['cash'] = bs.iloc[:, 0].get('Cash And Cash Equivalents', 0) / 1e6
        data['revenue'] = is_stmt.iloc[:, 0].get('Total Revenue', 0) / 1e6
        data['ebit'] = is_stmt.iloc[:, 0].get('EBIT', 0) / 1e6
        
        # Büyüme ve Yaş (Manuel hesap veya varsayılan)
        data['growth_start'] = 0.15 
        data['company_age'] = 10 # Info gelmezse varsayılan
        
        # Marjlar
        data['ebit_margin'] = data['ebit'] / data['revenue'] if data['revenue'] else 0.2
        
        pretax = is_stmt.iloc[:, 0].get('Pretax Income', 0)
        tax = is_stmt.iloc[:, 0].get('Tax Provision', 0)
        data['tax_rate'] = tax / pretax if pretax else 0.21
        
        return data, None

    except Exception as e:
        # HATA DURUMUNDA: Manuel Giriş için boş data döndür
        return None, f"Yahoo Veri Hatası: {str(e)}"

def calculate_dcf(data, years, g, manual_wacc=None, multiple=None):
    # WACC
    rf = 0.042
    rm = 0.05
    cost_equity = rf + data['beta'] * rm
    
    market_cap = data['shares'] * data['current_price']
    total_val = market_cap + data['total_debt']
    
    cost_debt = 0.045
    w_e = market_cap / total_val if total_val > 0 else 1
    w_d = data['total_debt'] / total_val if total_val > 0 else 0
    
    wacc = (w_e * cost_equity) + (w_d * cost_debt * (1 - data['tax_rate']))
    if manual_wacc: wacc = manual_wacc
        
    # DCF
    growth_rates = np.linspace(data['growth_start'], 0.04, years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for gr in growth_rates:
        rev = last_rev * (1 + gr)
        ebit = rev * data['ebit_margin']
        nopat = ebit * (1 - data['tax_rate'])
        reinvestment = nopat * 0.25
        
        fcff = nopat - reinvestment
        fcffs.append(fcff)
        last_rev = rev

    discount_factors = [1 / ((1 + wacc) ** (y - 0.5)) for y in range(1, years+1)]
    pv_fcff = np.sum(np.array(fcffs) * np.array(discount_factors))

    terminal_val = (fcffs[-1] * (1 + g)) / (wacc - g)
    pv_terminal = terminal_val / ((1 + wacc) ** years)
    
    enterprise_val = pv_fcff + pv_terminal
    equity_val = enterprise_val - data['total_debt'] + data['cash']
    dcf_price = equity_val / data['shares']
    
    multiple_price = 0
    if multiple:
        implied_cap = data['revenue'] * multiple
        multiple_price = implied_cap / data['shares']

    return dcf_price, wacc, fcffs, multiple_price

# --- ANA EKRAN MANTIĞI ---
if st.button("Analizi Başlat", type="primary"):
    with st.spinner('Veriler çekiliyor...'):
        fetched_data, error = get_data(ticker)
        
        # --- VERİ ÇEKME BAŞARISIZSA MANUEL MODU AÇ ---
        if error:
            st.warning(f"⚠️ Yahoo bağlantıyı reddetti ({error}). Lütfen verileri manuel girin:")
            
            with st.form("manuel_form"):
                col_m1, col_m2, col_m3 = st.columns(3)
                m_price = col_m1.number_input("Güncel Fiyat ($)", value=100.0)
                m_shares = col_m2.number_input("Hisse Sayısı (Milyon)", value=1000.0)
                m_rev = col_m3.number_input("Yıllık Ciro (Milyon $)", value=50000.0)
                
                col_m4, col_m5 = st.columns(2)
                m_ebit = col_m4.number_input("EBIT (Faiz Vergi Öncesi Kar)", value=5000.0)
                m_debt = col_m5.number_input("Toplam Borç", value=2000.0)
                m_cash = col_m5.number_input("Nakit", value=1000.0)
                
                submitted = st.form_submit_button("Manuel Verilerle Hesapla")
                
                if submitted:
                    fetched_data = {
                        'ticker': ticker, 'long_name': ticker, 'currency': 'USD',
                        'current_price': m_price, 'shares': m_shares, 'beta': 1.1,
                        'total_debt': m_debt, 'cash': m_cash, 'revenue': m_rev,
                        'ebit': m_ebit, 'growth_start': 0.15, 'company_age': 10,
                        'ebit_margin': m_ebit/m_rev, 'tax_rate': 0.21
                    }
                    error = None # Hatayı temizle
        
        # --- HESAPLAMA (Veri Otomatik veya Manuel geldiyse) ---
        if fetched_data and not error:
            data = fetched_data
            is_old_company = data['company_age'] > 15
            is_loss_making = data['ebit'] < 0
            
            use_startup_mode = force_startup or (is_loss_making and not is_old_company)
            
            dcf_val, used_wacc, flows, mult_val = calculate_dcf(
                data, forecast_years, perpetual_growth, wacc_input,
                 sector_multiple if use_startup_mode else None
            )
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Güncel Fiyat", f"{data['current_price']:.2f} {data['currency']}")
            
            if use_startup_mode:
                final_val = mult_val
                label = "Adil Değer (P/S Çarpanı)"
                col2.metric(label, f"{final_val:.2f} {data['currency']}")
            else:
                final_val = dcf_val
                label = "Adil Değer (DCF)"
                col2.metric(label, f"{final_val:.2f} {data['currency']}")
            
            upside = (final_val / data['current_price']) - 1
            delta_color = "normal" if upside > 0 else "inverse"
            col3.metric("Potansiyel", f"%{upside*100:.2f}", delta=f"{upside*100:.1f}%", delta_color=delta_color)

            st.bar_chart(pd.DataFrame({"Yıl": range(1, len(flows)+1), "Nakit Akışı": flows}).set_index("Yıl"))
