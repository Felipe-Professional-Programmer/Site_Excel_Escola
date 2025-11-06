import streamlit as st
import pandas as pd
import requests
import re
from io import BytesIO
import time
from typing import Optional, Dict, Any, Tuple

# --- I. FUNÇÕES CRÍTICAS DE PROCESSAMENTO ---

# Módulo de Limpeza de Número de Telefone (CRITICAL)
def clean_and_standardize_phone(number: str, default_country_code: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Limpa o número de telefone, removendo caracteres não-dígitos e
    garantindo o formato E.164 (código do país + DDD + Número).
    
    Retorna uma tupla (numero_padronizado, motivo_falha).
    """
    if not number:
        return None, "Número de entrada vazio ou nulo."
    
    # Assume que o CC é os 2 primeiros dígitos e o DD é o restante da string de configuração
    CC = default_country_code[:2] if len(default_country_code) >= 2 else "55" 
    DD = default_country_code[2:4] if len(default_country_code) >= 4 else "31"
    
    # 1. Converte para string e remove todos os caracteres não-dígitos
    cleaned_number = re.sub(r'\D', '', str(number))
    phone_length = len(cleaned_number)

    # ----------------------------------------------------------------------
    # LÓGICA AVANÇADA DE PADRONIZAÇÃO (Baseado em 55 e 31)
    # ----------------------------------------------------------------------
    
    # Verifica se o número já tem o CC (Ex: 55)
    has_cc = cleaned_number.startswith(CC)
    
    # NOVO REQUISITO EXCLUSIVO: Número com exatamente 10 dígitos (DD + 8 dígitos)
    # Assumimos que falta o '9' para ser um celular brasileiro de 9 dígitos.
    if phone_length == 10:
        # O número é DD + 8 dígitos (ex: 3187654321).
        # A nova regra diz para inferir o '9' que estava faltando
        inferred_number = CC + cleaned_number[:2] + '9' + cleaned_number[2:]
        # Resultado: 55 + DD + 9 + 8 dígitos (total 13)
        return inferred_number, None 

    # Caso 1: Número Local (8 ou 9 dígitos). Faltam CC e DD.
    if phone_length in [8, 9]:
        # Completa com o CC e DD padrão (Ex: 55 + 31 + 987654321)
        return CC + DD + cleaned_number, None

    # Caso 2: Número com DDD (11 dígitos). Falta o CC.
    # Ex: 31987654321
    if phone_length == 11:
        # Verifica se começa com o DDD configurado (Ex: 31)
        if cleaned_number.startswith(DD):
            # Completa com o CC (Ex: 55 + 31987654321)
            return CC + cleaned_number, None
        else:
            # Não começa com o DDD configurado, mas tem 11 dígitos.
            # Assumimos que o CC está faltando, completamos para ser seguro.
            return CC + cleaned_number, None

    # Caso 3: Número Internacional Completo (12 ou 13 dígitos).
    # Ex: 5531987654321 (13 digitos) ou 551198765432 (12 digitos, fixo antigo)
    if phone_length in [12, 13]:
        # Se já começa com o CC (55), está correto.
        if has_cc:
            return cleaned_number, None
        # Se não tem o CC, e tem 12 ou 13, assumimos que o CC está faltando.
        return CC + cleaned_number, None
        
    # Caso 4: Outros tamanhos (Muito longo ou muito curto/Inválido)
    if phone_length < 8:
        return None, f"Número muito curto ({phone_length} dígitos)."
    if phone_length > 13 and not has_cc:
        return None, f"Número muito longo sem Código de País ({phone_length} dígitos)."

    # Se nenhuma regra de padronização se aplicou ou se o número é inválido
    return None, f"Tamanho inválido ou não padronizável ({phone_length} dígitos)."

def format_phone_for_vcf(e164_number: str) -> str:
    """
    Formata um número E.164 (ex: 5531987654321) para o formato visual solicitado: 
    +CC (DD) 9XXXX-XXXX
    
    A formatação VCF é importante para compatibilidade visual na agenda, 
    mas o formato TEL;TYPE=CELL geralmente aceita o formato limpo.
    Faremos a formatação visual conforme solicitado.
    """
    if not e164_number or len(e164_number) != 13:
        # Retorna o original se não estiver no formato 55DD9XXXXXXXX esperado
        return e164_number 
        
    # Exemplo: 55 31 9 8765 4321
    cc = e164_number[0:2] # 55
    ddd = e164_number[2:4] # 31
    part1 = e164_number[4:9] # 98765
    part2 = e164_number[9:13] # 4321
    
    # Formato: +55 (31) 98765-4321
    return f"+{cc} ({ddd}) {part1}-{part2}"

# --- PATH A: VCF (vCard) GENERATION ---

def generate_vcf_content(df: pd.DataFrame, name_col: str, phone_col: str, default_country_code: str, failed_contacts: list, successful_contacts: list) -> str:
    """
    Gera o conteúdo de um único arquivo VCF (vCard) a partir do DataFrame.
    Preenche as listas `failed_contacts` e `successful_contacts`.
    """
    vcf_blocks = []
    
    for index, row in df.iterrows():
        # Usa .get() para segurança, lidando com NaN e None
        name = str(row.get(name_col, '')).strip()
        original_phone = str(row.get(phone_col, '')).strip()
        
        # Limpeza do número
        cleaned_phone_e164, failure_reason = clean_and_standardize_phone(original_phone, default_country_code)
        
        if name and cleaned_phone_e164:
            # NOVIDADE: Formata o número SOMENTE para o bloco VCF para visualização
            formatted_phone = format_phone_for_vcf(cleaned_phone_e164)
            
            vcf_block = f"""BEGIN:VCARD
VERSION:3.0
FN:{name}
N:;{name};;;
TEL;TYPE=CELL:{formatted_phone}
END:VCARD"""
            vcf_blocks.append(vcf_block)
            
            # Adiciona à lista de sucesso para visualização
            successful_contacts.append({
                "Índice_Linha_Original": index + 1,
                "Nome": name,
                "Número Original": original_phone,
                "Número Padronizado (E.164)": cleaned_phone_e164, # Mantém E.164 limpo na lista de sucesso
                "Visualização VCF": formatted_phone # Adiciona a visualização VCF formatada
            })
            
        else:
            # Coleta os dados completos e o motivo da falha (Módulo 26: Construtor de Respostas)
            # Adiciona os metadados do erro à linha completa do DataFrame
            failed_entry = {
                "Índice_Linha_Original": index + 1,
                "Motivo_da_Falha": failure_reason or "Nome ou Número Limpo Inválido."
            }
            # Combina os metadados com todos os dados da linha original
            failed_contacts.append(failed_entry | row.to_dict()) 
            
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
                    "Código de País e DDD Padrão (Ex: 5531):", 
                    value="5531",
                    help="Código de País (Ex: 55) + DDD (Ex: 31). Essencial para padronizar números locais."
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
                    
                    # Listas para armazenar os contatos (Módulo 26)
                    failed_contacts = []
                    successful_contacts = [] 
                    
                    with st.spinner('Processando e limpando dados para VCF...'):
                        vcf_content = generate_vcf_content(
                            df, 
                            st.session_state['name_col'], 
                            st.session_state['phone_col'], 
                            st.session_state['default_cc'],
                            failed_contacts, # Lista de falhas
                            successful_contacts # Lista de sucesso
                        )
                    
                    # Calcula o total de blocos VCF gerados
                    valid_count = len(vcf_content.split('END:VCARD')) - 1
                    
                    # Resposta para o usuário
                    if valid_count > 0:
                        st.download_button(
                            label="✅ Clique para Baixar o VCF",
                            data=vcf_content.encode('utf-8'),
                            file_name=f"contatos_import_{int(time.time())}.vcf",
                            mime="text/vcard"
                        )
                        st.success(f"VCF gerado com sucesso! Total de **{valid_count}** contatos válidos.")
                    else:
                        st.error("Nenhum contato válido foi encontrado após a limpeza dos números. Verifique o Código de País e DDD.")

                    # --- NOVO REQUISITO: Relatório de Falhas e Sucessos ---
                    st.markdown("---")
                    # Módulo 26: Usando o título solicitado pelo usuário
                    st.header("3. Visualização e Validação dos Números") 
                    
                    # 1. VISUALIZAÇÃO DE SUCESSO
                    if successful_contacts:
                        st.subheader("✅ Contatos Padronizados (Incluídos no VCF)")
                        st.info(f"Total de {len(successful_contacts)} contatos validados.")
                        success_df = pd.DataFrame(successful_contacts)
                        st.dataframe(
                            success_df,
                            use_container_width=True,
                            height=300
                        )
                        st.markdown("---")
                    
                    # 2. VISUALIZAÇÃO DE FALHA
                    if failed_contacts:
                        st.subheader("❌ Lista de Números que Falharam (Dados Completos)")
                        st.warning(f"⚠️ **{len(failed_contacts)}** contato(s) falhou(aram) na padronização e NÃO foram incluídos no VCF.")
                        
                        # Converte a lista de dicionários para DataFrame para exibição no Streamlit
                        failed_df = pd.DataFrame(failed_contacts)
                        
                        st.dataframe(
                            failed_df, 
                            use_container_width=True,
                            height=300 
                        )
                        
                    elif valid_count > 0:
                        st.info("🎉 Todos os contatos do seu arquivo foram processados com sucesso!")
                    
                    st.markdown("---")


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
                        
                        # Módulo 22: Otimização de Código - Usa nova tupla de retorno
                        cleaned_phone, failure_reason = clean_and_standardize_phone(original_phone, st.session_state['default_cc'])
                        
                        current_result = {
                            "Nome": contact_name,
                            "Número Original": original_phone,
                            "Status": "...",
                            "Detalhe da Falha": ""
                        }

                        if not cleaned_phone:
                            failure_count += 1
                            current_result.update({"Status": "❌ Falha", "Detalhe da Falha": f"Número Limpo/Formatado Inválido. Motivo: {failure_reason or 'Desconhecido'}"})
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
