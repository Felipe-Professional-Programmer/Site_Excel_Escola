import streamlit as st
import pandas as pd
import requests
import re
from io import BytesIO
import time
from typing import Optional, Dict, Any

# --- I. FUNÇÕES CRÍTICAS DE PROCESSAMENTO ---

# Módulo de Limpeza e Padronização de Número de Telefone (CRITICAL)
def clean_and_standardize_phone(number: str) -> Dict[str, Optional[str]]:
    """
    Limpa e padroniza o número de telefone de acordo com regras estritas:
    1. Sanitização completa (remove todos os caracteres não-dígitos).
    2. Validação de formato (11 ou 13 dígitos) para telefonia móvel brasileira.
    3. Validação do prefixo '55' (Código do País) e do '9' (Dígito de celular).
    4. Formatação EXATA: "+55 (DDD) 9XXXX-XXXX".

    Retorna um dicionário com o número formatado (formatted_number), o número limpo para API (api_number)
    e uma mensagem de erro (error_detail).
    """
    
    # 1. Sanitização Completa (remover todos os '+', '(', ')' e espaços em branco)
    if not number:
        return {"formatted_number": None, "api_number": None, "error_detail": "NÚMERO VAZIO."}
    
    # Remove todos os caracteres não-dígitos, garantindo que o número seja puro
    cleaned_number = re.sub(r'\D', '', str(number))
    
    phone_length = len(cleaned_number)
    
    # 2. Lógica de Padronização
    final_number = None
    error_detail = None

    if phone_length == 13:
        # Caso 1: Número já está no formato E.164 (55DD9XXXXXXXX)
        if cleaned_number.startswith('55'):
            final_number = cleaned_number
        else:
            # Tem 13 dígitos, mas não é 55 no início.
            error_detail = "ERRO: 13 dígitos, mas os 2 primeiros NÃO são '55' (CC Brasil)."
            
    elif phone_length == 11:
        # Caso 2: Número está no formato DD9XXXXXXXX (sem o 55)
        # Sua regra: Se tem 11 dígitos, se começar com 55, é INVÁLIDO (incompleto).
        if cleaned_number.startswith('55'):
            error_detail = "ERRO: 11 dígitos e começa com '55'. Número incompleto (DDD faltando)."
        else:
            # Assume que é DD9XXXXXXXX e corrige prefixando o 55
            final_number = '55' + cleaned_number
            
    elif phone_length == 10:
        # Caso 3: Descartar exatamente 10 dígitos (Formato ambíguo/inválido para celular)
        error_detail = "ERRO: 10 dígitos. Formato ambíguo ou inválido."

    else:
        # Caso 4: Outros comprimentos são descartados
        error_detail = f"ERRO: {phone_length} dígitos. Comprimento inválido (Esperado 11 ou 13)."


    # 3. Execução da Validação Estrita (Apenas se um final_number foi determinado)
    if final_number:
        # Garante que o número final tem 13 dígitos para as próximas verificações
        if len(final_number) != 13:
            # Proteção: Se chegou aqui e não tem 13 dígitos, é falha interna
            error_detail = "ERRO INTERNO: Número não padronizado para 13 dígitos."
            final_number = None
            
        # Verifica se o 5º dígito (após CC e DDD) é '9', indicando celular
        elif final_number[4] != '9':
            error_detail = "ERRO: Não é celular (5º dígito depois do CC+DDD não é '9')."
            final_number = None

    
    # 4. Montagem do Resultado e Formatação Final
    if final_number and not error_detail:
        # Extração das partes (garantida por ser 13 dígitos)
        country_code = final_number[0:2] # 55
        ddd = final_number[2:4]         # Ex: 31
        first_digit = final_number[4]   # O 9
        first_four = final_number[5:9]  # Primeiros 4 do número
        last_four = final_number[9:13]  # Últimos 4 do número
        
        # Formatação EXATA SOLICITADA: "+55 (DDD) 9XXXX-XXXX"
        formatted_number = f"+{country_code} ({ddd}) {first_digit}{first_four}-{last_four}"

        return {
            "formatted_number": formatted_number,
            "api_number": final_number, # 55DD9XXXXXXXX (somente dígitos)
            "error_detail": None 
        }

    return {
        "formatted_number": None,
        "api_number": None, 
        "error_detail": error_detail if error_detail else "FALHA DESCONHECIDA NA PADRONIZAÇÃO."
    }

# --- PATH A: VCF (vCard) GENERATION ---

def generate_vcf_content(df: pd.DataFrame, name_col: str, phone_col: str) -> str:
    """Gera o conteúdo completo do arquivo VCF a partir do DataFrame."""
    vcf_blocks = []
    
    # Adiciona um cabeçalho VCF universal
    vcf_blocks.append("BEGIN:VCARD\nVERSION:3.0\nPRODID:-//WhatsApp/Streamlit VCF Generator//EN")
    
    for index, row in df.iterrows():
        # Pega o nome e o número bruto
        full_name = str(row[name_col]).strip()
        raw_phone = row[phone_col]
        
        # Limpa e padroniza o número
        validation_result = clean_and_standardize_phone(raw_phone)
        api_number = validation_result['api_number']
        
        # Ignora contatos inválidos ou sem nome
        if not api_number or not full_name:
            continue
        
        # Monta o bloco VCF para cada contato
        vcf_block = f"""
BEGIN:VCARD
VERSION:3.0
FN:{full_name}
N:;{full_name};;;
TEL;TYPE=CELL:{api_number}
END:VCARD
"""
        vcf_blocks.append(vcf_block.strip())

    return "\n".join(vcf_blocks)

# --- PATH B: WHATSAPP CLOUD API INTEGRATION ---

def send_whatsapp_template_message(
    df: pd.DataFrame, 
    name_col: str, 
    phone_col: str, 
    access_token: str, 
    phone_number_id: str, 
    template_name: str
) -> pd.DataFrame:
    """Envia mensagens usando o WhatsApp Cloud API."""
    
    # URL da API da Meta (versão 19.0)
    API_URL = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    
    results = []

    for index, row in df.iterrows():
        full_name = str(row[name_col]).strip()
        raw_phone = row[phone_col]
        
        # 1. Validação e Padronização
        validation_result = clean_and_standardize_phone(raw_phone)
        api_number = validation_result['api_number'] # Número limpo (55DD9XXXXXXXX)
        
        if not api_number:
            # Adiciona erro ao relatório e continua
            results.append({
                'Nome': full_name,
                'Número Original': raw_phone,
                'Status': 'FALHA',
                'Detalhe do Erro': validation_result['error_detail']
            })
            continue

        # 2. Construção do Payload (JSON) para a Meta API
        # O número deve ser prefixado com "+" para o 'to' da API, mas 'api_number' já é E.164 limpo.
        payload = {
            "messaging_product": "whatsapp",
            "to": api_number, 
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": "pt_BR" # Assumindo Português do Brasil para o template
                },
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                # Passa o nome completo como primeiro parâmetro do template ({{1}})
                                "text": full_name 
                            }
                        ]
                    }
                ]
            }
        }
        
        # 3. Envio da Requisição POST
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                # Sucesso: Extrai o ID da mensagem
                message_id = response.json().get('messages', [{}])[0].get('id', 'N/A')
                results.append({
                    'Nome': full_name,
                    'Número Original': raw_phone,
                    'Status': 'SUCESSO',
                    'Detalhe do Erro': f'Mensagem ID: {message_id}'
                })
            else:
                # Falha da API: Retorna o erro
                error_data = response.json().get('error', {}).get('message', 'Erro desconhecido da API')
                results.append({
                    'Nome': full_name,
                    'Número Original': raw_phone,
                    'Status': 'FALHA',
                    'Detalhe do Erro': f'HTTP {response.status_code}: {error_data}'
                })
        
        except requests.exceptions.RequestException as e:
            # Erro de conexão/timeout
            results.append({
                'Nome': full_name,
                'Número Original': raw_phone,
                'Status': 'FALHA',
                'Detalhe do Erro': f'Erro de Conexão: {e}'
            })
        
        # Pausa para evitar limites de taxa de API (rate limits)
        time.sleep(0.5) 
        
    return pd.DataFrame(results)

# --- II. INTERFACE DO USUÁRIO (STREAMLIT) ---

def main():
    """Função principal que constrói a interface do Streamlit."""
    
    st.set_page_config(
        page_title="Excel-to-WhatsApp Integrator",
        layout="centered",
        initial_sidebar_state="auto"
    )

    st.title("🤖 Excel/CSV para WhatsApp (v3.0)")
    st.caption("Ferramenta de padronização e envio em lote para contatos móveis brasileiros.")

    # 1. Upload do Arquivo
    uploaded_file = st.file_uploader(
        "1. Faça o upload do seu arquivo de contatos (.xlsx ou .csv)",
        type=['xlsx', 'xls', 'csv']
    )

    if uploaded_file is not None:
        try:
            # Determina o tipo de arquivo para o Pandas
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                # Assume Excel (.xlsx ou .xls)
                df = pd.read_excel(uploaded_file)
            
            # Limpa nomes de colunas (remove espaços extras)
            df.columns = df.columns.str.strip()
            
            st.success(f"Arquivo '{uploaded_file.name}' carregado com sucesso! Linhas: {len(df)}")

            # Nomes das colunas para os dropdowns
            column_names = df.columns.tolist()

            # --- Lógica de Pré-Seleção (Baseada na solicitação do usuário) ---
            
            # Tenta encontrar a coluna 'Responsável' (ignora case)
            default_name_index = next((i for i, col in enumerate(column_names) if 'RESPONSÁVEL' in col.upper()), 0)
            
            # Tenta encontrar a coluna 'Telefone' (ignora case)
            default_phone_index = next((i for i, col in enumerate(column_names) if 'TELEFONE' in col.upper()), 0)
            
            # 2. Mapeamento de Colunas
            st.subheader("2. Mapeamento de Colunas")

            name_col = st.selectbox(
                "Coluna do Nome Completo (Responsável):",
                column_names,
                index=default_name_index,
                help="Selecione a coluna que contém o nome da pessoa/responsável."
            )
            
            phone_col = st.selectbox(
                "Coluna do Número de Telefone:",
                column_names,
                index=default_phone_index,
                help="Selecione a coluna que contém o número de telefone (com ou sem formatação)."
            )

            # 3. Pré-visualização e Validação dos Números (Novo Módulo de Feedback)
            st.subheader("3. Visualização e Validação dos Números")
            
            # Aplica a validação e padronização para a pré-visualização (máx 100 linhas)
            preview_df = df.head(100).copy()
            
            # Usa a função de padronização para criar as colunas de status
            validation_results = [clean_and_standardize_phone(n) for n in preview_df[phone_col]]
            
            preview_df['Número Limpo Formatado'] = [r['formatted_number'] for r in validation_results]
            preview_df['Status Validação'] = ['✅ Válido' if r['api_number'] else '❌ FALHA' for r in validation_results]
            preview_df['Detalhe do Erro'] = [r['error_detail'] if r['error_detail'] else 'OK' for r in validation_results]
            
            # Exibe a pré-visualização (apenas colunas importantes)
            st.dataframe(
                preview_df[[name_col, phone_col, 'Número Limpo Formatado', 'Status Validação', 'Detalhe do Erro']],
                use_container_width=True
            )
            
            # --- 4. Escolha do Caminho ---
            st.subheader("4. Escolha o Caminho de Saída")
            
            path = st.radio(
                "Selecione a Ação:",
                ('PATH A: Gerar Arquivo VCF (Importar Contatos)', 'PATH B: Enviar Mensagem via WhatsApp Cloud API'),
                key='path_choice'
            )

            # --- PATH A: VCF Generation ---
            if path == 'PATH A: Gerar Arquivo VCF (Importar Contatos)':
                st.info("O VCF só incluirá contatos que passaram na validação (11 ou 13 dígitos, com '9' e '55' no lugar certo).")
                
                # Gera o conteúdo VCF
                vcf_content = generate_vcf_content(df, name_col, phone_col)
                
                if vcf_content.strip():
                    # Botão de download do Streamlit
                    st.download_button(
                        label="🚀 Baixar Arquivo VCF (.vcf)",
                        data=vcf_content.encode('utf-8'),
                        file_name=f"contatos_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.vcf",
                        mime="text/vcard",
                        help="Clique para baixar o arquivo VCF pronto para importação."
                    )
                    st.success(f"VCF gerado. Contém {len(vcf_content.split('END:VCARD')) - 1} contatos válidos.")
                else:
                    st.warning("Nenhum contato válido encontrado para gerar o VCF.")

            # --- PATH B: WhatsApp Cloud API ---
            elif path == 'PATH B: Enviar Mensagem via WhatsApp Cloud API':
                st.warning("Requer credenciais da Meta. Use apenas templates previamente aprovados.")
                
                # Campos de entrada para as credenciais
                with st.expander("Configurações da API", expanded=True):
                    access_token = st.text_input("Token de Acesso da Meta (Começa com EAAB...)", type="password")
                    phone_number_id = st.text_input("ID do Número de Telefone (da conta do WhatsApp Business)")
                    template_name = st.text_input("Nome do Template Aprovado (Ex: 'bem_vindo')")

                # Botão de Execução
                if st.button("🔴 Iniciar Envio de Mensagens via API (Alto Risco)", disabled=not (access_token and phone_number_id and template_name)):
                    
                    if not st.checkbox("Confirmo que o template está aprovado e entendo os limites de taxa da API.", key='confirm_api'):
                        st.error("Você deve confirmar a responsabilidade pelo uso da API.")
                        return

                    st.info("Iniciando envio... Isso pode demorar, não feche o navegador.")
                    
                    # Executa a função de envio
                    try:
                        report_df = send_whatsapp_template_message(
                            df, name_col, phone_col, access_token, phone_number_id, template_name
                        )
                        
                        st.subheader("Relatório de Execução da API")
                        
                        total_sent = len(report_df)
                        success_count = (report_df['Status'] == 'SUCESSO').sum()
                        fail_count = (report_df['Status'] == 'FALHA').sum()
                        
                        st.metric("Total de Contatos Processados", total_sent)
                        st.metric("Mensagens Enviadas com Sucesso", success_count)
                        st.metric("Falhas (Erros ou Números Inválidos)", fail_count)
                        
                        st.dataframe(report_df, use_container_width=True)
                        st.balloons()
                    
                    except Exception as e:
                        st.error(f"Ocorreu um erro crítico durante o processamento da API: {e}")

        except Exception as e:
            st.error(f"Erro ao processar o arquivo. Verifique se o formato está correto: {e}")

if __name__ == '__main__':
    main()
