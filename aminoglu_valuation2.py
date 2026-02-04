import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Otopilot", page_icon="🤖", layout="wide")

# --- BAŞLIK ---
st.title("🤖 Amınoğlu Otopilot (v7.0)")
st.markdown("Tam Otomatik Değerleme: Slider yok, ayar yok. Sadece sembol gir.")

# --- YAN MENÜ (SADECE SEMBOL) ---
with st.sidebar:
    st.header("🔍 Analiz")
    ticker = st.text_input("Hisse Sembolü", value="LMT").upper()
    st.info("💡 Model, şirketin yaşına, betasına ve büyüme hızına bakarak tüm ayarları (Yıl, WACC, Büyüme, Yatırım Oranı) kendi belirler.")

# --- YARDIMCI ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- VERİ ÇEKME (Anti-Ban & Yedekli) ---
@st.cache_data(ttl=3600)
def get_data(symbol):
    stock = yf.Ticker(symbol)
    data = {}
    
    try:
        # Hızlı veri
        current_price = stock.fast_info.get('last_price', None)
        shares = stock.fast_info.get('shares', None)
        
        if current_price is None or np.isnan(safe_float(current_price)):
            hist = stock.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
            else:
                return None, "Fiyat verisi çekilemedi."

        bs = stock.balance_sheet
        is_stmt = stock.financials
        
        if bs.empty or is_stmt.empty:
            return None, "Finansal tablolar boş (Yahoo Engeli)."

        # --- TEMEL VERİLER ---
        data['ticker'] = symbol
        data['currency'] = stock.fast_info.get('currency', 'USD')
        data['current_price'] = safe_float(current_price)
        data['shares'] = safe_float(shares) / 1e6 
        if data['shares'] <= 0: data['shares'] = 1.0

        # --- PROFİL VERİLERİ ---
        # 1. Risk (Beta)
        try:
            data['beta'] = stock.info.get('beta', 1.0)
        except:
            data['beta'] = 1.0
            
        # 2. Büyüme (Revenue Growth)
        try:
            data['revenue_growth'] = stock.info.get('revenueGrowth', 0.05)
        except:
            data['revenue_growth'] = 0.05

        # 3. Yaş (Age)
        first_trade = stock.info.get('firstTradeDateEpochUtc', None) if 'info' in dir(stock) else None
        if first_trade:
            ipo_year = datetime.datetime.fromtimestamp(first_trade).year
            data['age'] = datetime.datetime.now().year - ipo_year
        else:
            data['age'] = 15 # Bilinmiyorsa orta

        # Tablolar
        data['total_debt'] = safe_float(bs.iloc[:, 0].get('Total Debt')) / 1e6
        data['cash'] = safe_float(bs.iloc[:, 0].get('Cash And Cash Equivalents')) / 1e6
        data['revenue'] = safe_float(is_stmt.iloc[:, 0].get('Total Revenue')) / 1e6
        
        ebit = safe_float(is_stmt.iloc[:, 0].get('EBIT'))
        if ebit == 0: ebit = safe_float(is_stmt.iloc[:, 0].get('Operating Income'))
        data['ebit'] = ebit / 1e6
        
        if data['revenue'] > 0:
            data['ebit_margin'] = data['ebit'] / data['revenue']
        else:
            data['ebit_margin'] = 0.15
            
        return data, None

    except Exception as e:
        return None, str(e)

# --- OTOPİLOT BEYNİ (TÜM KARARLARI BU ALIR) ---
def autopilot_dcf(data):
    # Girdiler
    age = data.get('age', 15)
    growth = data.get('revenue_growth', 0.05)
    beta = data.get('beta', 1.0)
    
    # --- KARAR MEKANİZMASI ---
    
    # SENARYO 1: NAKİT İNEĞİ (LMT, KO, PEP)
    # Yaşlı (>15), Düşük Risk (Beta < 0.9)
    if (age > 15) and (beta < 0.9):
        profile = "🐄 NAKİT İNEĞİ (Cash Cow)"
        
        forecast_years = 7        # Uzun tahmine gerek yok, stabil.
        perpetual_g = 0.025       # %2.5 (Enflasyon kadar büyür)
        reinvestment_rate = 0.05  # %5 Yatırım (Çok az harcar, çok dağıtır)
        target_wacc_cap = 0.075   # WACC'ı maksimum %7.5 yap (Değer artsın)
        
        # Beta düzeltmesi (Risk düşük)
        used_beta = min(beta, 0.75) 

    # SENARYO 2: ROKET (NVDA, TSLA, Startup)
    # Hızlı Büyüyen (>%15) veya Genç (<10)
    elif (growth > 0.15) or (age < 10):
        profile = "🚀 ROKET (High Growth)"
        
        forecast_years = 15       # Uzun tahmin lazım (S eğrisi)
        perpetual_g = 0.035       # %3.5 (Ekonomiden hızlı büyür)
        reinvestment_rate = 0.50  # %50 Yatırım (Büyümek için para yakar)
        target_wacc_cap = 0.12    # Riskli olduğu için WACC yüksek olabilir
        
        used_beta = max(beta, 1.2) # Beta yüksek

    # SENARYO 3: STANDART (THYAO, SISE, FORD)
    else:
        profile = "🏭 STANDART SANAYİ"
        
        forecast_years = 10
        perpetual_g = 0.030
        reinvestment_rate = 0.25
        target_wacc_cap = 0.10
        used_beta = beta

    # --- HESAPLAMA ---
    
    # 1. WACC
    rf = 0.04
    rm = 0.05
    cost_equity = rf + used_beta * rm
    
    market_cap = data['shares'] * data['current_price']
    total_val = market_cap + data['total_debt']
    if total_val <= 0: total_val = market_cap if market_cap > 0 else 1.0
    
    w_e = market_cap / total_val
    w_d = data['total_debt'] / total_val
    
    wacc = (w_e * cost_equity) + (w_d * 0.055 * (1 - 0.21))
    
    # Otopilot WACC Ayarı (Değerlemeyi makul sınırlarda tutmak için)
    # Hesaplanan WACC, hedeflenen tavandan yüksekse indir.
    # Ama %6'nın altına da inmesin.
    wacc = max(0.06, min(wacc, target_wacc_cap))
    
    # 2. BÜYÜME (g vs WACC Kilidi)
    # g, WACC'tan büyük olamaz.
    if perpetual_g >= wacc:
        perpetual_g = wacc - 0.005

    # 3. NAKİT AKIŞI
    current_margin = data['ebit_margin']
    
    # Marj Hedefi: Roketse iyileşir, İnekse korunur
    if profile == "🚀 ROKET (High Growth)" and current_margin < 0.20:
        target_margin = 0.25
    elif profile == "🐄 NAKİT İNEĞİ (Cash Cow)" and current_margin < 0.12:
        target_margin = 0.12 # En kötü %12 olsun
    else:
        target_margin = current_margin # Mevcudu koru

    margins = np.linspace(current_margin, target_margin, forecast_years)
    
    # Büyüme Hızı Projeksiyonu
    # Başlangıç büyümesi: Şirketin şu anki büyümesi ile %8 arasında makul bir yer
    start_g = max(min(data.get('revenue_growth', 0.05), 0.20), 0.05)
    growth_rates = np.linspace(start_g, perpetual_g, forecast_years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(forecast_years):
        rev = last_rev * (1 + growth_rates[i])
        ebit = rev * margins[i]
        nopat = ebit * (1 - 0.21)
        
        # Dinamik Yatırım: Nakit İneği ise az, Roket ise çok yatırım
        reinvestment = nopat * reinvestment_rate
        
        fcff = nopat - reinvestment
        fcffs.append(fcff)
        last_rev = rev

    # 4. DEĞERLEME
    discount_factors = [1 / ((1 + wacc) ** (y + 1)) for y in range(forecast_years)]
    pv_fcff = np.sum(np.array(fcffs) * np.array(discount_factors))
    
    terminal_val = (fcffs[-1] * (1 + perpetual_g)) / (wacc - perpetual_g)
    if terminal_val < 0: terminal_val = 0
        
    pv_terminal = terminal_val / ((1 + wacc) ** forecast_years)
    
    enterprise_val = pv_fcff + pv_terminal
    equity_val = enterprise_val - data['total_debt'] + data['cash']
    
    dcf_price = equity_val / data['shares']
    if dcf_price < 0: dcf_price = 0
    
    # AI Karar Raporu
    decisions = {
        "profile": profile,
        "years": forecast_years,
        "wacc": wacc,
        "g": perpetual_g,
        "reinv": reinvestment_rate,
        "margin_target": target_margin
    }
    
    return dcf_price, flows, decisions

# --- EKRAN ---
if st.button("ANALİZ ET", type="primary"):
    with st.spinner('Otopilot verileri analiz ediyor...'):
        fetched_data, error = get_data(ticker)
        
        # MANUEL GİRİŞ (YAHOO PATLARSA)
        if error:
            st.warning("⚠️ Yahoo veriyi vermedi. Mecburen manuel gireceğiz.")
            with st.form("manual"):
                c1, c2 = st.columns(2)
                m_price = c1.number_input("Fiyat ($)", value=100.0)
                m_shares = c2.number_input("Hisse Adedi (Milyon)", value=250.0)
                m_rev = c1.number_input("Ciro (Milyon $)", value=50000.0)
                m_ebit = c2.number_input("EBIT", value=8000.0)
                m_debt = c1.number_input("Borç", value=5000.0)
                m_cash = c2.number_input("Nakit", value=2000.0)
                
                # Otopilot için kritik sorular
                st.markdown("---")
                st.caption("Otopilotun karar vermesi için:")
                m_beta = c1.slider("Beta (Risk)", 0.5, 2.0, 0.8)
                m_age = c2.slider("Şirket Yaşı", 1, 100, 20)
                m_growth = c1.slider("Büyüme (%)", 0, 50, 5) / 100
                
                if st.form_submit_button("HESAPLA"):
                    fetched_data = {
                        'ticker': ticker, 'currency': 'USD',
                        'current_price': m_price, 'shares': m_shares, 
                        'total_debt': m_debt, 'cash': m_cash, 'revenue': m_rev,
                        'ebit': m_ebit, 'ebit_margin': m_ebit/m_rev if m_rev else 0,
                        'beta': m_beta, 'age': m_age, 'revenue_growth': m_growth
                    }
                    error = None

        if fetched_data and not error:
            data = fetched_data
            
            # OTOPİLOT DEVREYE GİRİYOR
            price, flows, decisions = autopilot_dcf(data)
            
            # --- SONUÇ EKRANI ---
            
            # 1. Profil Kartı
            st.info(f"🧬 **Algılanan Kimlik:** {decisions['profile']}")
            
            # 2. Rakamlar
            c1, c2, c3 = st.columns(3)
            c1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} $")
            c2.metric("Otopilot Değeri", f"{price:.2f} $")
            
            upside = (price / data['current_price']) - 1
            c3.metric("Potansiyel", f"%{upside*100:.1f}", delta_color="normal" if upside > 0 else "inverse")
            
            # 3. "Neden Böyle Yaptım?" Bölümü (Şeffaflık)
            with st.expander("🤔 Yapay Zeka bu sonuca nasıl ulaştı?"):
                st.write(f"""
                - **Süre:** Şirket yapısına uygun olarak **{decisions['years']} yıllık** projeksiyon yaptım.
                - **Büyüme (g):** Sonsuza kadar yıllık **%{decisions['g']*100:.1f}** büyüyeceğini varsaydım.
                - **Risk (WACC):** İskonto oranını **%{decisions['wacc']*100:.1f}** olarak belirledim.
                - **Yatırım:** Kazancının sadece **%{decisions['reinv']*100:.0f}**'ini yatırıma harcadığını (nakit akışının güçlü olduğunu) varsaydım.
                """)
            
            st.bar_chart(flows)
