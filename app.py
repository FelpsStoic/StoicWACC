# app.py - Versão Final com a biblioteca st-copy-to-clipboard

import streamlit as st
import pandas as pd
import warnings
from datetime import date, datetime
from urllib.error import URLError
from st_copy_to_clipboard import st_copy_to_clipboard # NOVA IMPORTAÇÃO para o botão de copiar

# Ignorar avisos que podem poluir a saída
warnings.filterwarnings('ignore', category=FutureWarning)

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Calculadora de WACC",
    page_icon="📊",
    layout="centered"
)

# --- FUNÇÕES DE BUSCA DE DADOS (COM CACHE) ---
# ... (as funções de busca de dados continuam as mesmas) ...
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
    Busca a Taxa Livre de Risco do Tesouro Direto usando o título Prefixado com Juros Semestrais
    de vencimento mais longo, para a data mais recente disponível na base.
    """
    try:
        url = 'https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv'
        df = pd.read_csv(url, sep=';', decimal=',')
        df['Data Base'] = pd.to_datetime(df['Data Base'], dayfirst=True)
        df['Data Vencimento'] = pd.to_datetime(df['Data Vencimento'], dayfirst=True)
        df['Taxa Compra Manha'] = pd.to_numeric(df['Taxa Compra Manha'])
        data_mais_recente = df['Data Base'].max()
        df_recente = df[df['Data Base'] == data_mais_recente].copy()
        df_filtrado = df_recente[df_recente['Tipo Titulo'] == 'Tesouro Prefixado com Juros Semestrais']
        df_final = df_filtrado.sort_values(by='Data Vencimento', ascending=False)
        
        if df_final.empty:
            st.warning("Aviso: Nenhum título 'Tesouro Prefixado com Juros Semestrais' encontrado na fonte do Tesouro Direto.")
            return None, None, None
            
        risk_free_rate = df_final['Taxa Compra Manha'].iloc[0] / 100
        rf_info = f"Rf de {risk_free_rate:.2%} (Tesouro {df_final['Data Vencimento'].iloc[0].strftime('%d/%m/%Y')})".replace('.',',')
        
        return risk_free_rate, rf_info, data_mais_recente
        
    except URLError:
        st.error(
            "**Dados do Tesouro Direto temporariamente indisponíveis.** "
            "O servidor do governo não respondeu. Por favor, tente novamente mais tarde.",
            icon="📡"
        )
        return None, None, None
        
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado ao processar os dados do Tesouro: {e}", icon="⚠️")
        return None, None, None


# --- CARREGANDO DADOS ---
with st.spinner('Carregando dados de mercado... Por favor, aguarde.'):
    df_betas = get_beta_data()
    erp_brazil = get_brazil_risk_premiums()
    rf_rate, rf_info_str, data_base_rf = get_risk_free_rate()

# --- TÍTULO E DESCRIÇÃO COM LOGO ---
col1, col2 = st.columns([1, 4])
with col1:
    try:
        st.image("assets/logo.png", width=100)
    except FileNotFoundError:
        st.write("")
with col2:
    st.title("Calculadora de WACC")
    st.markdown("Ferramenta para calcular o Custo Médio Ponderado de Capital (WACC).")
    st.markdown("1. Selecione o Setor que a empresa está inserida")
    st.markdown("2. Digite o Custo da Dívida, e a Proporação da Dívida no capital total")
    st.markdown("3. Adicione o Prêmio de Tamanho")
st.markdown("---")


# Verifica se os dados essenciais foram carregados
if not df_betas.empty and erp_brazil is not None and rf_rate is not None:
    
    # --- SEÇÃO DE INPUTS ---
    st.subheader("1. Insira os Parâmetros da Empresa")
    
    col_input1, col_input2, col_input3 = st.columns(3)

    with col_input1:
        industry_list = sorted(df_betas['Industry Name'].unique())
        selected_industry = st.selectbox("Selecione o Setor:",industry_list)
        debt_ratio_pct = st.number_input("Proporção de Dívida (D/V) (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0, format="%.1f")
        debt_ratio = debt_ratio_pct / 100.0
        
    with col_input2:
        cost_of_debt_pct = st.number_input("Custo da Dívida (Kd) (%)", min_value=0.0, value=0.0, step=0.10, format="%.2f")
        cost_of_debt = cost_of_debt_pct / 100.0
        tax_rate_pct = st.number_input("Alíquota de Imposto (t) (%)", min_value=0.0, max_value=100.0, value=34.0, step=1.0, format="%.1f")
        tax_rate = tax_rate_pct / 100.0

    with col_input3:
        size_premium_pct = st.number_input("Prêmio de Tamanho (%)", min_value=0.0, value=0.0, step=0.1, format="%.2f")
        size_premium = size_premium_pct / 100.0


    # --- CÁLCULOS ---
    equity_ratio = 1 - debt_ratio
    beta = df_betas[df_betas['Industry Name'] == selected_industry]['Beta'].iloc[0]
    cost_of_equity = rf_rate + beta * erp_brazil + size_premium
    wacc = (equity_ratio * cost_of_equity) + (debt_ratio * cost_of_debt * (1 - tax_rate))

    # --- SEÇÃO DE RESULTADOS ---
    st.markdown("---")
    st.subheader("2. Resultados do Cálculo")
    
    res_col1, res_col2, res_col3 = st.columns(3)
    res_col1.metric("Custo do Equity (Re)", f"{cost_of_equity:.2%}".replace('.',','))
    res_col2.metric("Custo da Dívida (após impostos)", f"{cost_of_debt * (1 - tax_rate):.2%}".replace('.',','))
    res_col3.metric("WACC", f"{wacc:.2%}".replace('.',','))
    
    # --- TABELA PARA COPIAR ---
    with st.expander("📋 Tabela para Copiar e Colar (Excel, Google Sheets)"):
        summary_data = {
            "Métrica": [
                "Data do Cálculo", "Data Base (Dados de Mercado)", "Taxa Livre de Risco (Rf)",
                "Prêmio de Risco de Mercado (ERP)", "Setor Selecionado", "Beta (β) do Setor",
                "Prêmio de Tamanho", "Proporção de Equity (E/V)", "Proporção de Dívida (D/V)",
                "Custo da Dívida (Kd)", "Alíquota de Imposto (t)"
            ],
            "Valor": [
                date.today().strftime('%d/%m/%Y'),
                data_base_rf.strftime('%d/%m/%Y'),
                f"{rf_rate:.2%}".replace('.', ','),
                f"{erp_brazil:.2%}".replace('.', ','),
                selected_industry,
                f"{beta:.4f}".replace('.', ','),
                f"{size_premium:.2%}".replace('.', ','),
                f"{equity_ratio:.2%}".replace('.', ','),
                f"{debt_ratio:.2%}".replace('.', ','),
                f"{cost_of_debt:.2%}".replace('.', ','),
                f"{tax_rate:.2%}".replace('.', ','),
            ]
            
        }
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, hide_index=True, use_container_width=True)
        
        # BOTÃO ATUALIZADO usando st-copy-to-clipboard
        tabela_para_copiar = summary_df.to_csv(sep='\t', index=False)
        st_copy_to_clipboard(tabela_para_copiar, "Copiar Tabela para a Área de Transferência")

    # --- DETALHAMENTO DAS FÓRMULAS ---
    with st.expander("🔎 Detalhamento das Fórmulas"):
        st.info(rf_info_str, icon="📄")
        st.subheader("Cálculo do Custo de Equity (Re)")
        st.latex(r'''K_e = R_f + (\beta \times ERP) + \text{Prêmio de Tamanho}''')
        st.latex(f"K_e = {rf_rate:.2%} + ({beta:.4f} \\times {erp_brazil:.2%}) + {size_premium:.2%} = \\textbf{{{cost_of_equity:.2%}}}".replace('.',','))
        st.subheader("Cálculo do WACC")
        st.latex(r'''\text{WACC} = \left( \frac{E}{V} \times K_e \right) + \left( \frac{D}{V} \times K_d \times (1 - t) \right)''')
        st.latex(f"\\text{{WACC}} = ({equity_ratio:.0%} \\times {cost_of_equity:.2%}) + ({debt_ratio:.0%} \\times {cost_of_debt:.2%} \\times (1 - {tax_rate:.0%})) = \\textbf{{{wacc:.2%}}}".replace('.',','))

else:
    st.warning("A aplicação não pode continuar pois um ou mais dados de mercado não foram carregados. Verifique as mensagens de erro acima.")
