# app.py - Versão Consolidada Final

import streamlit as st
import pandas as pd
import warnings

# Ignorar avisos que podem poluir a saída
warnings.filterwarnings('ignore', category=FutureWarning)

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Calculadora de WACC",
    page_icon="📊",
    layout="centered"
)

# --- FUNÇÕES DE BUSCA DE DADOS (COM CACHE) ---
# O decorator @st.cache_data garante que os dados sejam baixados apenas uma vez,
# deixando a aplicação muito mais rápida após o primeiro carregamento.
@st.cache_data
def get_beta_data():
    """Busca a tabela de Betas por setor do site do Damodaran."""
    try:
        url = 'https://www.stern.nyu.edu/~adamodar/pc/datasets/betas.xls'
        df = pd.read_excel(url, sheet_name='Industry Averages', skiprows=9)
        df.columns = df.columns.str.strip()
        df.dropna(how='all', inplace=True)
        df = df[['Industry Name', 'Beta']].dropna(subset=['Industry Name'])
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados de Beta: {e}")
        return pd.DataFrame()

@st.cache_data
def get_brazil_risk_premiums():
    """Busca o Prêmio de Risco (ERP) para o Brasil."""
    try:
        url = 'https://www.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xlsx'
        df = pd.read_excel(url, sheet_name='ERPs by country', header=6)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        brazil_data = df[df.iloc[:, 0] == 'Brazil']
        erp = brazil_data['Total Equity Risk Premium'].iloc[0]
        return erp
    except Exception as e:
        st.error(f"Erro ao carregar Prêmio de Risco: {e}")
        return None

@st.cache_data
def get_risk_free_rate():
    """
    Busca a Taxa Livre de Risco usando o Tesouro Prefixado com Juros Semestrais
    de vencimento mais longo, para a data mais recente disponível na base.
    """
    try:
        url = 'https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv'
        df = pd.read_csv(url, sep=';', decimal=',')

        # 1. Converter as colunas de data e taxa para os tipos corretos
        df['Data Base'] = pd.to_datetime(df['Data Base'], dayfirst=True)
        df['Data Vencimento'] = pd.to_datetime(df['Data Vencimento'], dayfirst=True)
        df['Taxa Compra Manha'] = pd.to_numeric(df['Taxa Compra Manha'])

        # 2. Encontrar a data mais recente na base de dados
        data_mais_recente = df['Data Base'].max()
        
        # 3. Filtrar o DataFrame para conter apenas os dados da data mais recente
        df_recente = df[df['Data Base'] == data_mais_recente].copy()

        # 4. Filtrar pelo tipo de título exato: "Tesouro Prefixado com Juros Semestrais"
        df_filtrado = df_recente[df_recente['Tipo Titulo'] == 'Tesouro Prefixado com Juros Semestrais']
        
        # 5. Ordenar os títulos filtrados pelo vencimento mais longo
        df_final = df_filtrado.sort_values(by='Data Vencimento', ascending=False)
        
        if df_final.empty:
            st.warning("Aviso: Nenhum título 'Tesouro Prefixado com Juros Semestrais' encontrado para a data mais recente. Verifique a fonte de dados.")
            return None # Retorna None se não encontrar o título específico
            
        # Pega a taxa do título mais longo e converte para decimal
        risk_free_rate = df_final['Taxa Compra Manha'].iloc[0] / 100
        
        # Adiciona uma mensagem de sucesso no sidebar para informar o usuário
        titulo_usado = df_final['Tipo Titulo'].iloc[0]
        vencimento_usado = df_final['Data Vencimento'].iloc[0].strftime('%d/%m/%Y')
        st.sidebar.success(f"Rf de {risk_free_rate:.2%} (Tesouro {vencimento_usado}) usada no cálculo.")
        
        return risk_free_rate
        
    except Exception as e:
        st.error(f"Erro ao carregar Taxa Livre de Risco: {e}")
        return None

# --- CARREGANDO DADOS ---
with st.spinner('Carregando dados de mercado... Por favor, aguarde.'):
    df_betas = get_beta_data()
    erp_brazil = get_brazil_risk_premiums()
    rf_rate = get_risk_free_rate()

# --- INTERFACE DA APLICAÇÃO ---
st.title("📊 Calculadora de WACC")
st.markdown("Ferramenta para calcular o Custo Médio Ponderado de Capital (WACC) de uma empresa.")
st.markdown("---")

# Verifica se os dados essenciais foram carregados
if not df_betas.empty and erp_brazil is not None and rf_rate is not None:
    
    # --- INPUTS DO USUÁRIO NA BARRA LATERAL ---
    st.sidebar.header("Inputs da Empresa")

    # Input 1: Setor
    industry_list = sorted(df_betas['Industry Name'].unique())
    selected_industry = st.sidebar.selectbox(
        "Selecione o Setor:",
        industry_list
    )

    # Input 2: Proporção de Dívida
    debt_ratio = st.sidebar.slider(
        "Proporção de Dívida (D/V):",
        min_value=0.0, max_value=1.0, value=0.30, step=0.01, format="%.0f%%"
    )
    
    # Input 3: Custo da Dívida
    cost_of_debt = st.sidebar.slider(
        "Custo da Dívida (Kd):",
        min_value=0.0, max_value=0.30, value=0.08, step=0.005, format="%.2f%%"
    )

    # Input 4: Alíquota de Imposto
    tax_rate = st.sidebar.slider(
        "Alíquota de Imposto (t):",
        min_value=0.0, max_value=0.50, value=0.34, step=0.01, format="%.0f%%"
    )

    # --- CÁLCULOS ---
    equity_ratio = 1 - debt_ratio
    beta = df_betas[df_betas['Industry Name'] == selected_industry]['Beta'].iloc[0]
    
    # Custo do Equity (Re) via CAPM
    cost_of_equity = rf_rate + beta * erp_brazil
    
    # WACC
    wacc = (equity_ratio * cost_of_equity) + (debt_ratio * cost_of_debt * (1 - tax_rate))

    # --- EXIBIÇÃO DOS RESULTADOS ---
    st.header("Resultados")

    col1, col2, col3 = st.columns(3)
    col1.metric("Custo do Equity (Re)", f"{cost_of_equity:.2%}")
    col2.metric("Custo da Dívida (após impostos)", f"{cost_of_debt * (1 - tax_rate):.2%}")
    col3.metric("WACC", f"{wacc:.2%}", delta_color="inverse")
    
    st.markdown("---")

    # Detalhamento dos cálculos em um "expander"
    with st.expander("Clique para ver o detalhamento do cálculo"):
        st.subheader("Parâmetros de Mercado")
        st.markdown(f"- **Prêmio de Risco de Mercado (ERP Brasil):** `{erp_brazil:.2%}`")
        st.markdown(f"- **Beta (β) do Setor '{selected_industry}':** `{beta:.4f}`")

        st.subheader("Cálculo do Custo de Equity (Re)")
        st.latex(r'''R_e = R_f + \beta \times ERP''')
        st.latex(f"R_e = {rf_rate:.2%} + {beta:.4f} \\times {erp_brazil:.2%} = \\textbf{{{cost_of_equity:.2%}}}")
        
        st.subheader("Cálculo do WACC")
        st.latex(r'''\text{WACC} = \left( \frac{E}{V} \times R_e \right) + \left( \frac{D}{V} \times R_d \times (1 - t) \right)''')
        st.latex(f"\\text{{WACC}} = ({equity_ratio:.0%} \\times {cost_of_equity:.2%}) + ({debt_ratio:.0%} \\times {cost_of_debt:.2%} \\times (1 - {tax_rate:.0%})) = \\textbf{{{wacc:.2%}}}")

else:
    st.error("❌ A aplicação não pôde ser iniciada. Verifique se as fontes de dados (Damodaran, Tesouro Direto) estão online e tente recarregar a página.")
