import streamlit as st
import pandas as pd
import requests
import re
from io import BytesIO
import time
from typing import Optional, Dict, Any

# --- I. FUNÇÕES CRÍTICAS DE PROCESSAMENTO ---

# Módulo de Limpeza de Número de Telefone (CRITICAL)
def clean_and_standardize_phone(number: str, default_country_code: str) -> Optional[str]:
    """
    Limpa o número de telefone, removendo caracteres não-dígitos e
    garantindo o formato E.164 (código do país + DDD + Número).
    
    A lógica foca no Brasil (55) mas é ajustável via `default_country_code`.
    """
    if not number:
        return None
    
    # 1. Converte para string e remove todos os caracteres não-dígitos
    cleaned_number = re.sub(r'\D', '', str(number))
    
    country_code_only = default_country_code[:2]
    
    # 2. Se o número já começa com o código do país, assume que está completo.
    if cleaned_number.startswith(country_code_only) and len(cleaned_number) >= 10:
        return cleaned_number
    
    # 3. Trata números que não têm prefixo internacional.
    
    # Se o número tiver 10 ou 11 dígitos, assume-se que o DDD está incluso.
    if len(cleaned_number) in [10, 11]:
        return country_code_only + cleaned_number
    
    # Se o número tiver 8 ou 9 dígitos (apenas local), assume-se que o DDD está faltando
    # e usa o DDD fornecido no 'default_country_code' (ex: '11' de '5511').
    if len(cleaned_number) in [8, 9]:
        ddd = default_country_code[2:] 
        if ddd:
            return country_code_only + ddd + cleaned_number
        else:
            # Caso o usuário tenha fornecido apenas "55" e o número seja local (8/9 dígitos)
            return None # Não é possível inferir o DDD
            
    # Se a limpeza falhar ou o número for muito curto/estranho, retorna None
    return None

# --- PATH A: VCF (vCard) GENERATION ---

def generate_vcf_content(df: pd.DataFrame, name_col: str, phone_col: str, default_country_code: str) -> str:
    """Gera o conteúdo de um único arquivo VCF (vCard) a partir do DataFrame."""
    vcf_blocks = []
    
    for _, row in df.iterrows():
        # Usa .get() para segurança, lidando com NaN e None
        name = str(row.get(name_col, '')).strip()
        original_phone = str(row.get(phone_col, '')).strip()
        
        # Limpeza do número
        cleaned_phone = clean_and_standardize_phone(original_phone, default_country_code)
        
        if name and cleaned_phone:
            vcf_block = f"""BEGIN:VCARD
VERSION:3.0
FN:{name}
N:;{name};;;
TEL;TYPE=CELL:{cleaned_phone}
END:VCARD"""
            vcf_blocks.append(vcf_block)
            
    return '\n'.join(vcf_blocks)

# --- PATH B: WHATSAPP CLOUD API INTEGRATION ---

def send_whatsapp_template_message(
    phone_number_id: str, 
    access_token: str, 
    recipient_number: str, 
    template_name: str, 
    contact_name: str
) -> Dict[str, Any]:
    """Envia uma mensagem de template via WhatsApp Cloud API."""
    
    # 1. Constrói o URL da API
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    
    # 2. Constrói o payload da mensagem (assumindo o placeholder {{1}} para o nome)
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": "pt_BR"
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            # Substitui o placeholder {{1}} pelo nome do contato
                            "type": "text",
                            "text": contact_name 
                        }
                    ]
                }
            ]
        }
    }
    
    # 3. Define os cabeçalhos de autenticação
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status() # Lança exceção para códigos de status HTTP 4xx/5xx
        return {"status": "Success", "data": response.json()}
    except requests.exceptions.HTTPError as e:
        # Erros da API (ex: token inválido, template não encontrado)
        error_detail = e.response.json().get('error', {}).get('message', 'Erro HTTP desconhecido.')
        return {"status": "Failure", "detail": f"HTTP Error: {e.response.status_code}. Detalhe: {error_detail}"}
    except requests.exceptions.RequestException as e:
        # Erros de conexão (ex: timeout, DNS)
        return {"status": "Failure", "detail": f"Erro de Conexão: {e}"}

# --- II. ESTRUTURA E INTERFACE DO STREAMLIT ---

def main():
    st.set_page_config(
        page_title="AI Excel-to-WhatsApp Sender",
        layout="wide",
        initial_sidebar_state="collapsed" 
    )
    
    st.title("🚀 Conversor Excel/CSV para Contatos/WhatsApp")
    st.markdown("Automatize a integração de contatos da sua planilha para o celular (VCF) ou para o WhatsApp Business Cloud API.")
    st.markdown("---")

    # --- Step 1: Upload & Map ---
    
    st.header("1. Upload e Mapeamento de Dados")
    uploaded_file = st.file_uploader("Selecione seu arquivo (.xlsx, .xls ou .csv)", type=["xlsx", "xls", "csv"])

    if uploaded_file is not None:
        try:
            # Carrega o DataFrame
            if uploaded_file.name.endswith('.csv'):
                # Tenta ler CSV com detecção automática de delimitador/encoding
                df = pd.read_csv(uploaded_file, encoding='utf-8', sep=None, engine='python')
            else:
                # Usa BytesIO para garantir a compatibilidade com Streamlit e pandas
                df = pd.read_excel(uploaded_file, engine='openpyxl')
            
            st.session_state['df'] = df
            columns = df.columns.tolist()
            
            st.success(f"Arquivo '{uploaded_file.name}' carregado com sucesso. {len(df)} linhas encontradas.")
            
            # Mapeamento de Colunas
            col1, col2 = st.columns(2)
            
            with col1:
                name_col = st.selectbox("Coluna do Nome Completo:", columns, index=0, key='name_col_select')
            with col2:
                # Tentativa de pré-seleção para 'phone'
                default_phone_index = next((i for i, col in enumerate(columns) if 'phone' in col.lower() or 'numero' in col.lower()), 0)
                phone_col = st.selectbox("Coluna do Número de Telefone:", columns, index=default_phone_index, key='phone_col_select')
            
            cc_col, ddd_col = st.columns([1, 2])
            with ddd_col:
                default_cc_ddd = st.text_input(
                    "Código de País e DDD Padrão (Ex: 5511):", 
                    value="5511",
                    help="Código de País (Ex: 55) + DDD (Ex: 11). Essencial para padronizar números locais."
                )
            
            st.session_state['name_col'] = name_col
            st.session_state['phone_col'] = phone_col
            st.session_state['default_cc'] = re.sub(r'\D', '', default_cc_ddd) # Limpa e armazena
            
            st.markdown("---")

            # --- Step 2: Choose Path & Execute ---
            st.header("2. Escolha o Caminho de Integração")
            path = st.radio(
                "Selecione sua necessidade:",
                ('PATH A: Geração de VCF (Agenda Pessoal)', 'PATH B: Integração WhatsApp Cloud API (Empresarial)'),
                index=0, key='path_select'
            )

            if path == 'PATH A: Geração de VCF (Agenda Pessoal)':
                # --- PATH A: VCF EXECUTION ---
                st.subheader("Geração de VCF (vCard)")
                st.markdown("Gera um único arquivo `.vcf` pronto para importação em qualquer agenda de contatos (Google/iOS).")
                
                if st.button("📥 Gerar e Baixar Arquivo VCF", key="btn_vcf_gen"):
                    with st.spinner('Processando e limpando dados para VCF...'):
                        vcf_content = generate_vcf_content(
                            df, 
                            st.session_state['name_col'], 
                            st.session_state['phone_col'], 
                            st.session_state['default_cc']
                        )
                    
                    if vcf_content:
                        st.download_button(
                            label="✅ Clique para Baixar o VCF",
                            data=vcf_content.encode('utf-8'),
                            file_name=f"contatos_import_{int(time.time())}.vcf",
                            mime="text/vcard"
                        )
                        st.success(f"VCF gerado com sucesso! Total de {len(vcf_content.split('END:VCARD')) - 1} contatos válidos.")
                    else:
                        st.error("Nenhum contato válido foi encontrado após a limpeza dos números. Verifique o Código de País e DDD.")

            elif path == 'PATH B: Integração WhatsApp Cloud API (Empresarial)':
                # --- PATH B: API CREDENTIALS ---
                st.subheader("Configuração do WhatsApp Cloud API")
                st.warning("⚠️ **Atenção:** Certifique-se de que seu template está APROVADO.")
                
                # Campos dinâmicos para credenciais
                api_token = st.text_input("Access Token da Meta:", type="password", key='api_token_input')
                phone_id = st.text_input("Phone Number ID (ID do Telefone no Meta):", key='phone_id_input')
                template_name = st.text_input("Nome do Template Aprovado (Ex: 'ola_novo_cliente'):", key='template_name_input')
                
                st.info("Atenção: A lógica assume que o primeiro placeholder do seu template é o nome do contato.")

                if st.button("🚀 Iniciar Envio de Mensagens via API", key="btn_api_send"):
                    if not all([api_token, phone_id, template_name]):
                        st.error("Por favor, preencha todos os campos de credenciais da API.")
                        return

                    st.markdown("---")
                    st.header("Registro de Execução da API")
                    
                    results = []
                    status_log = st.empty()
                    
                    total_rows = len(df)
                    success_count = 0
                    failure_count = 0
                    
                    # Cria um DataFrame temporário para o relatório e o exibe para updates em tempo real
                    results_df = pd.DataFrame(columns=["Nome", "Número Original", "Status", "Detalhe da Falha"])
                    results_container = st.empty()
                    results_container.dataframe(results_df)

                    for index, row in df.iterrows():
                        contact_name = str(row.get(st.session_state['name_col'], 'Contato Desconhecido'))
                        original_phone = str(row.get(st.session_state['phone_col'], ''))
                        
                        cleaned_phone = clean_and_standardize_phone(original_phone, st.session_state['default_cc'])
                        
                        current_result = {
                            "Nome": contact_name,
                            "Número Original": original_phone,
                            "Status": "...",
                            "Detalhe da Falha": ""
                        }

                        if not cleaned_phone:
                            failure_count += 1
                            current_result.update({"Status": "❌ Falha", "Detalhe da Falha": "Número Limpo/Formatado Inválido."})
                        else:
                            # Simulação de atraso (boas práticas de API)
                            time.sleep(0.5) 
                            
                            # Chama a função da API
                            api_response = send_whatsapp_template_message(
                                phone_id,
                                api_token,
                                cleaned_phone,
                                template_name,
                                contact_name
                            )

                            if api_response['status'] == 'Success':
                                success_count += 1
                                current_result.update({
                                    "Status": "✅ Sucesso", 
                                    "Detalhe da Falha": f"ID da Mensagem: {api_response['data'].get('messages', [{}])[0].get('id', 'N/A')}"
                                })
                            else:
                                failure_count += 1
                                current_result.update({"Status": "❌ Falha", "Detalhe da Falha": api_response['detail']})

                        # Atualiza o DataFrame do relatório
                        results_df.loc[index] = current_result
                        results_container.dataframe(results_df.style.apply(lambda s: ['background-color: #ffcccc' if 'Falha' in v else '' for v in s], subset=['Status', 'Detalhe da Falha']))
                        
                        # Atualiza o log de progresso
                        status_log.write(f"Processando contato {index+1}/{total_rows}... (Sucessos: {success_count}, Falhas: {failure_count})")

                    # Relatório Final
                    st.markdown("---")
                    st.success(f"Processo Concluído! Total de Contatos: {total_rows}")
                    st.metric(label="Mensagens Enviadas com Sucesso", value=success_count)
                    st.metric(label="Falhas no Envio", value=failure_count)
                    
                    status_log.empty() # Remove o status de processamento

        except Exception as e:
            st.error(f"Ocorreu um erro no processamento do arquivo: {e}")
            st.warning("Verifique se as colunas e o formato do arquivo estão corretos. Erro técnico: " + str(e))

    else:
        st.info("Aguardando o upload do seu arquivo Excel ou CSV.")

if __name__ == '__main__':
    main()