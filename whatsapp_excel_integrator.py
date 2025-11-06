import streamlit as st
import pandas as pd
import requests
import re
import json
import time
from io import BytesIO
from typing import Optional, Dict, Any, Tuple

# --- CONSTANTES DE AI REMOVIDAS ---
# Nenhuma chave ou constante de AI é necessária, pois o mapeamento é fixo.
# ----------------------------------

# --- CONSTANTES DE MAPEAMENTO FIXO (NOVO REQUISITO) ---
# O aplicativo agora espera que a planilha tenha EXATAMENTE estas colunas.
FIXED_COLUMNS_MAP = {
    "turma_name_col": "Turma",
    "student_name_col": "Aluno",
    "phone_col": "Telefone",
    "responsible_name_col": "Responsável",
}
# ----------------------------------------------------


# --- I. FUNÇÕES CRÍTICAS DE PROCESSAMENTO (Simplificadas) ---

# Funções de AI para explicação e detecção foram removidas.

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
    
    # --- NOVIDADE: Pré-validação do formato visual do hífen (Corrigido) ---
    raw_number_str = str(number)
    if '-' in raw_number_str:
        parts = raw_number_str.split('-')
        
        # Deve ter exatamente um hífen
        if len(parts) != 2:
             return None, "Formato do hífen inválido. Deve ter exatamente um hífen."
        
        # Remove caracteres não-dígitos das partes para contagem
        part2_clean = re.sub(r'\D', '', parts[1])

        # Se a parte 2 não tiver 4 dígitos, falha conforme regra do usuário.
        # Esta é a validação rigorosa para rejeitar números como XXXX-147 (3 dígitos).
        if len(part2_clean) != 4:
            return None, f"A segunda parte do número (após o hífen) deve conter exatamente 4 dígitos. Encontrado: {len(part2_clean)} dígitos."
            
    
    # 1. Converte para string e remove todos os caracteres não-dígitos
    cleaned_number = re.sub(r'\D', '', str(number))
    phone_length = len(cleaned_number)

    # ----------------------------------------------------------------------
    # LÓGICA AVANÇADA DE PADRONIZAÇÃO (Baseado em 55 e 31)
    # ----------------------------------------------------------------------
    
    # Verifica se o número já tem o CC (Ex: 55)
    has_cc = cleaned_number.startswith(CC)
    
    # Tratamento de números de 12 dígitos que são 55 + DD + 8 dígitos (faltando o '9')
    if phone_length == 12 and has_cc:
        # Padrão: 55 + DD + 8 dígitos. (Ex: 553187654321)
        inferred_number = cleaned_number[:4] + '9' + cleaned_number[4:]
        return inferred_number, None
        
    # Número com exatamente 10 dígitos (DD + 8 dígitos, assumindo falta de 55 e '9')
    if phone_length == 10:
        # O número é DD + 8 dígitos (ex: 3187654321).
        inferred_number = CC + cleaned_number[:2] + '9' + cleaned_number[2:]
        return inferred_number, None 

    # Caso 1: Número Local (8 ou 9 dígitos). Faltam CC e DD.
    if phone_length in [8, 9]:
        return CC + DD + cleaned_number, None

    # Caso 2: Número com DDD (11 dígitos). Falta o CC.
    if phone_length == 11:
        if cleaned_number.startswith(DD):
            return CC + cleaned_number, None
        else:
            return CC + cleaned_number, None

    # Caso 3: Número Internacional Completo (13 dígitos).
    if phone_length == 13:
        if has_cc:
            return cleaned_number, None
        
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
    """
    if not e164_number or len(e164_number) != 13:
        return e164_number 
        
    # Exemplo: 55 31 9 8765 4321
    cc = e164_number[0:2] 
    ddd = e164_number[2:4] 
    part1 = e164_number[4:9] 
    part2 = e164_number[9:13] 
    
    # Formato: +55 (31) 98765-4321
    return f"+{cc} ({ddd}) {part1}-{part2}"

# --- PATH A: VCF (vCard) GENERATION ---

def generate_vcf_content(df: pd.DataFrame, responsible_name_col: str, student_name_col: str, phone_col: str, turma_name_col: str, default_country_code: str, failed_contacts: list, successful_contacts: list) -> str:
    """
    Gera o conteúdo de um único arquivo VCF (vCard) a partir do DataFrame.
    Preenche as listas `failed_contacts` e `successful_contacts`.
    """
    vcf_blocks = []
    
    for index, row in df.iterrows():
        # Mapeamento fixo conforme as colunas esperadas
        responsible_name = str(row.get(responsible_name_col, '')).strip()
        student_name = str(row.get(student_name_col, '')).strip()
        turma_name = str(row.get(turma_name_col, '')).strip() 
        original_phone = str(row.get(phone_col, '')).strip()
        
        # Monta o nome completo do contato (Responsável + Aluno) para o VCF
        full_name_for_vcf = f"{responsible_name} - {student_name}" if student_name else responsible_name
        
        # Limpeza do número
        cleaned_phone_e164, failure_reason = clean_and_standardize_phone(original_phone, default_country_code)
        
        if responsible_name and cleaned_phone_e164:
            # Formata o número SOMENTE para o bloco VCF para visualização
            formatted_phone = format_phone_for_vcf(cleaned_phone_e164)
            
            # Bloco VCF usa o nome composto
            vcf_block = f"""BEGIN:VCARD
VERSION:3.0
FN:{full_name_for_vcf}
N:;{responsible_name};;;
TEL;TYPE=CELL:{formatted_phone}
END:VCARD"""
            vcf_blocks.append(vcf_block)
            
            # Adiciona à lista de sucesso para visualização
            successful_contacts.append({
                "Índice_Linha_Original": index + 1,
                "Nome do Responsável": responsible_name, 
                "Nome do Aluno": student_name, 
                "Nome da Turma": turma_name, 
                "Número Original": original_phone,
                "Número Padronizado (E.164)": cleaned_phone_e164, 
                "Visualização VCF": formatted_phone 
            })
            
        else:
            # Adiciona os metadados do erro à linha completa do DataFrame
            failed_entry = {
                "Índice_Linha_Original": index + 1,
                "Nome do Responsável": responsible_name, 
                "Nome do Aluno": student_name, 
                "Nome da Turma": turma_name, 
                "Telefone": original_phone, 
                "Motivo_da_Falha": failure_reason or "Nome ou Número Limpo Inválido.",
                "Explicação_Manual": "O número não pôde ser padronizado. Verifique se ele contém o DDD e o 9º dígito se for celular." # Mensagem manual
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
    url = f"[https://graph.facebook.com/v19.0/](https://graph.facebook.com/v19.0/){phone_number_id}/messages"
    
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
        response.raise_for_status() 
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
    # Remove a interface do chat AI
    
    st.set_page_config(
        page_title="Excel-to-WhatsApp Sender",
        layout="wide",
        initial_sidebar_state="collapsed" 
    )
    
    st.title("🚀 Conversor Excel/CSV para Contatos/WhatsApp (Mapeamento Fixo)")
    st.markdown("Automatize a integração de contatos da sua planilha para o celular (VCF) ou para o WhatsApp Business Cloud API.")
    st.markdown("---")

    # --- Step 1: Upload & Map ---
    
    st.header("1. Upload e Mapeamento de Dados")
    st.markdown("⚠️ **Atenção:** Este aplicativo espera que seu arquivo Excel/CSV contenha as colunas **Turma**, **Aluno**, **Telefone** e **Responsável** com estes nomes exatos.")
    
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
            
            # --- Mapeamento Fixo e Validação ---
            
            # Mapeia diretamente para os nomes fixos
            responsible_name_col = FIXED_COLUMNS_MAP['responsible_name_col']
            student_name_col = FIXED_COLUMNS_MAP['student_name_col']
            phone_col = FIXED_COLUMNS_MAP['phone_col']
            turma_name_col = FIXED_COLUMNS_MAP['turma_name_col']
            
            required_cols = [responsible_name_col, student_name_col, phone_col, turma_name_col]
            missing_cols = [col for col in required_cols if col not in columns]

            if missing_cols:
                st.error(f"❌ Erro de Mapeamento: As seguintes colunas obrigatórias não foram encontradas em seu arquivo: **{', '.join(missing_cols)}**.")
                return
            
            st.success("✅ Todas as colunas necessárias foram encontradas.")

            # =========================================================================
            # Mapeamento de Colunas FIXO (Resultado da AI REMOVIDO)
            # =========================================================================
            
            # Exibe as colunas fixas (Somente para informação do usuário)
            st.subheader("Colunas Mapeadas Automaticamente (Nomes Fixos):")
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.markdown(f"**Responsável:** `{responsible_name_col}`")
                st.markdown(f"**Aluno:** `{student_name_col}`")
            with col_info2:
                st.markdown(f"**Turma:** `{turma_name_col}`")
                st.markdown(f"**Telefone:** `{phone_col}`")

            
            # Armazenamento das colunas fixas na session_state
            st.session_state['responsible_name_col'] = responsible_name_col
            st.session_state['student_name_col'] = student_name_col
            st.session_state['phone_col'] = phone_col
            st.session_state['turma_name_col'] = turma_name_col 
            # =========================================================================
            
            # Coluna para DDD/CC (mantida como input para flexibilidade do usuário)
            cc_col, ddd_col = st.columns([1, 2])
            with ddd_col:
                default_cc_ddd = st.text_input(
                    "Código de País e DDD Padrão (Ex: 5531):", 
                    value="5531",
                    help="Código de País (Ex: 55) + DDD (Ex: 31). Essencial para padronizar números locais."
                )
            
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
                            st.session_state['responsible_name_col'], 
                            st.session_state['student_name_col'],     
                            st.session_state['phone_col'], 
                            st.session_state['turma_name_col'], 
                            st.session_state['default_cc'],
                            failed_contacts, 
                            successful_contacts 
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
                        # Reordena colunas
                        columns_order = ["Índice_Linha_Original", "Nome do Responsável", "Nome do Aluno", "Nome da Turma", "Número Original", "Número Padronizado (E.164)", "Visualização VCF"]
                        success_df = success_df[columns_order]
                        st.dataframe(
                            success_df,
                            use_container_width=True,
                            height=300
                        )
                        st.markdown("---")
                    
                    # 2. VISUALIZAÇÃO DE FALHA
                    if failed_contacts:
                        st.subheader("❌ Lista de Números que Falharam (Dados Completos + Explicação Manual)")
                        st.warning(f"⚠️ **{len(failed_contacts)}** contato(s) falhou(aram) na padronização e NÃO foram incluídos no VCF.")
                        
                        # Converte a lista de dicionários para DataFrame para exibição no Streamlit
                        failed_df = pd.DataFrame(failed_contacts)
                        
                        # Definição das colunas de exibição e suas configurações
                        failed_columns_config = {
                            "Índice_Linha_Original": st.column_config.NumberColumn("Linha"),
                            "Nome do Responsável": st.column_config.TextColumn("Responsável"),
                            "Nome do Aluno": st.column_config.TextColumn("Aluno"),
                            "Nome da Turma": st.column_config.TextColumn("Turma"), 
                            "Telefone": st.column_config.TextColumn("Telefone"), 
                            # Configurações para estender o texto
                            "Motivo_da_Falha": st.column_config.Column(
                                "Motivo da Falha",
                                width="large",
                                help="Por que o número falhou na padronização.",
                            ),
                            "Explicação_Manual": st.column_config.Column(
                                "Explicação_Manual", # Trocado de AI para Manual
                                width="large",
                                help="Diagnóstico manual para o formato incorreto."
                            ),
                            # Adicionar as demais colunas do Excel para 'Dados Completos'
                        }
                        
                        # Reordena colunas para exibir as colunas chave primeiro
                        failed_columns_order = [
                            "Índice_Linha_Original", 
                            "Nome do Responsável", 
                            "Nome do Aluno", 
                            "Nome da Turma", 
                            "Telefone",
                            "Motivo_da_Falha", 
                            "Explicação_Manual"
                        ]
                        
                        # Garante que apenas colunas existentes sejam usadas
                        existing_cols = [col for col in failed_columns_order if col in failed_df.columns]
                        failed_df = failed_df[existing_cols]

                        # Filtrar o column_config para apenas colunas existentes e usáveis
                        config_to_use = {k: v for k, v in failed_columns_config.items() if k in existing_cols}

                        st.dataframe(
                            failed_df, 
                            column_config=config_to_use, 
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
                    results_df = pd.DataFrame(columns=["Nome do Responsável", "Nome do Aluno", "Número Original", "Status", "Detalhe da Falha"])
                    results_container = st.empty()
                    results_container.dataframe(results_df)

                    for index, row in df.iterrows():
                        # Obtém os nomes
                        responsible_name = str(row.get(st.session_state['responsible_name_col'], 'Responsável Desconhecido'))
                        student_name = str(row.get(st.session_state['student_name_col'], 'Aluno Desconhecido'))
                        original_phone = str(row.get(st.session_state['phone_col'], ''))
                        
                        contact_name = f"{responsible_name} / {student_name}" 
                        
                        # Módulo 22: Otimização de Código - Usa nova tupla de retorno
                        cleaned_phone, failure_reason = clean_and_standardize_phone(original_phone, st.session_state['default_cc'])
                        
                        current_result = {
                            "Nome do Responsável": responsible_name, 
                            "Nome do Aluno": student_name, 
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
                                responsible_name 
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
