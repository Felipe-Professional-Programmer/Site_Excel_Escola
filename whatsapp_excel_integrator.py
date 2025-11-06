import streamlit as st
import pandas as pd
import requests
import re
import json # Adicionado para manipulação de JSON da API
from io import BytesIO
import time
from typing import Optional, Dict, Any, Tuple

# --- CONSTANTES DE AI ---
# CHAVE FORNECIDA PELO USUÁRIO (OpenRouter)
OPENROUTER_API_KEY = "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"
OPENROUTER_MODEL = "tngtech/deepseek-r1t2-chimera:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# -------------------------


# --- I. FUNÇÕES CRÍTICAS DE PROCESSAMENTO ---

def explain_phone_defect_with_ai(original_number: str, reason: str, max_retries=3) -> str:
    """
    Chama o modelo Gemini para analisar e explicar o defeito de um número de telefone 
    que falhou na padronização, simulando o uso da AI para análise textual.
    """
    # Módulo 4: Simulação de Integrações - Configuração da API Gemini
    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent"
    API_KEY = ""  # Deixar vazio para uso em ambientes Canvas/Google

    # Módulo 26: Construtor de Respostas - Estruturação do Prompt
    user_query = f"""
    Analise o seguinte número de telefone original: "{original_number}".
    Ele falhou na padronização com o motivo: "{reason}".
    
    Explique em português, de forma concisa (máximo 2 frases), qual o formato correto esperado
    para um número de celular brasileiro (+55 DD 9XXXX-XXXX) e o que está faltando ou 
    incorreto no número fornecido, considerando as regras de 10 a 13 dígitos.
    """

    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "systemInstruction": {"parts": [{"text": "Você é um analista de telecomunicações focado em padrões de numeração brasileiros. Sua única tarefa é explicar o erro de formatação de um número, focando em Código de País (+55), DDD e o nono dígito (9), e o formato esperado (DD + 9XXXX-XXXX)."}]},
    }
    
    headers = {
        'Content-Type': 'application/json',
    }

    # Simulação de Loop de Retry com Backoff Exponencial
    for attempt in range(max_retries):
        try:
            # Tenta chamar a API
            response = requests.post(API_URL, headers=headers, json=payload, timeout=15)
            response.raise_for_status() 
            
            result = response.json()
            # Extrai o texto gerado
            text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'Não foi possível obter a explicação da AI.')
            return text
            
        except requests.exceptions.RequestException as e:
            # Atraso exponencial
            wait_time = 2 ** attempt
            if attempt < max_retries - 1:
                time.sleep(wait_time)
            else:
                # Retorna uma explicação local robusta em caso de falha da API
                return (f"Falha ao consultar a AI ({reason}). O formato brasileiro requer 13 dígitos (55 + DDD + 9 dígitos), "
                        f"e seu número não se encaixou nos padrões de correção automática.")
        except Exception:
            return "Erro desconhecido ao processar a resposta da AI."
            
    return "Erro desconhecido."

def detect_columns_with_ai(columns: list, sample_row: Dict[str, Any], max_retries=3) -> Dict[str, str]:
    """
    Calls the OpenRouter AI to semantically map required fields to column headers.
    Returns a dictionary of mapped column names or raises an exception on failure.
    """
    # Módulo 40: Deployment Wrapper - Prompt Estruturado para detecção de colunas
    
    required_fields = ["Nome do Responsável", "Nome do Aluno", "Nome da Turma", "Telefone"]
    
    # Prepara a matriz textual da linha de amostra para a IA
    sample_text = ', '.join(map(str, sample_row.values()))
    
    ai_prompt = f"""
# DEEP SYSTEM PROMPT: ANALISTA DE DADOS E MAPEAMENTO DE COLUNAS
Você é um Analista de Dados de Alto Nível com foco em mapeamento de colunas para campos semânticos.
Sua única tarefa é mapear as colunas fornecidas abaixo para os QUATRO campos semânticos requeridos.
Você DEVE retornar APENAS um objeto JSON válido, sem texto explicativo, introdução, ou formatação Markdown (como ```json).

# CAMPOS SEMÂNTICOS REQUERIDOS:
1. responsible_name_col: Nome EXATO da coluna que representa o Nome do Responsável ou Contato Principal.
2. student_name_col: Nome EXATO da coluna que representa o Nome do Aluno.
3. turma_name_col: Nome EXATO da coluna que representa a Turma ou Classe.
4. phone_col: Nome EXATO da coluna que representa o Telefone ou Número de Contato.

Se você não conseguir identificar uma coluna, use o valor 'NÃO ENCONTRADO' para aquela chave.
O seu trabalho se resume a retornar o JSON final.

# DADOS DA TABELA EXCEL (MATRIZ UNIDIMENSIONAL DE TEXTO PARA CONTEXTO)
COLUNAS (Títulos):
[{', '.join(columns)}]

LINHA DE AMOSTRA (Valores em ordem):
[{sample_text}]

Com base nas COLUNAS, identifique as chaves e retorne APENAS o JSON.
"""

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": ai_prompt
            }
        ],
        "response_mime_type": "application/json",
        "response_schema": {
            "type": "object",
            "properties": {
                "responsible_name_col": {"type": "string"},
                "student_name_col": {"type": "string"},
                "turma_name_col": {"type": "string"},
                "phone_col": {"type": "string"}
            }
        }
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "[https://canvas.google.com](https://canvas.google.com)", 
        "X-Title": "AI Excel-to-WhatsApp Sender"
    }

    # Módulo 37: Gerenciamento de Dependências (Retry Loop)
    for attempt in range(max_retries):
        try:
            response = requests.post(
                url=OPENROUTER_URL,
                headers=headers,
                data=json.dumps(payload),
                timeout=30 
            )
            response.raise_for_status() 
            api_result = response.json()
            
            ai_response_text = api_result['choices'][0]['message']['content'].strip()
            # Módulo 35: Output Polisher - Limpa e tenta parsear a string JSON da IA
            clean_json_text = ai_response_text.replace('```json', '').replace('```', '').strip()
            final_result = json.loads(clean_json_text)
            
            # Módulo 14: Verificação Dedutiva - Valida a estrutura JSON
            required_keys = ['responsible_name_col', 'student_name_col', 'turma_name_col', 'phone_col']
            if not all(key in final_result for key in required_keys):
                 raise ValueError(f"AI returned incomplete mapping. Missing keys.")
            
            # Verifica se os nomes mapeados realmente existem nas colunas fornecidas
            for key, col_name in final_result.items():
                if col_name and col_name != 'NÃO ENCONTRADO' and col_name not in columns:
                    st.warning(f"Atenção: A IA mapeou '{col_name}' para {key}, mas essa coluna não foi encontrada no seu arquivo. Retornando 'NÃO ENCONTRADO' para segurança.")
                    final_result[key] = 'NÃO ENCONTRADO'
                    
            return final_result

        except (requests.exceptions.RequestException, KeyError, IndexError, json.JSONDecodeError, ValueError) as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Backoff exponencial
                continue
            else:
                error_message = f"Falha na detecção automática de colunas por AI (Tentativas: {max_retries}). Erro: {e}"
                if 'response' in locals() and response.status_code == 401:
                    error_message += " (Token de API Inválido ou Expirado)"
                elif 'response' in locals():
                    error_message += f" (Status HTTP: {response.status_code})"
                raise Exception(error_message)
                
    # Fallback return (should be unreachable)
    return {}


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

def generate_vcf_content(df: pd.DataFrame, responsible_name_col: str, student_name_col: str, phone_col: str, turma_name_col: str, default_country_code: str, failed_contacts: list, successful_contacts: list) -> str:
    """
    Gera o conteúdo de um único arquivo VCF (vCard) a partir do DataFrame.
    Preenche as listas `failed_contacts` e `successful_contacts`.
    """
    vcf_blocks = []
    
    for index, row in df.iterrows():
        # Usa .get() para segurança, lidando com NaN e None
        responsible_name = str(row.get(responsible_name_col, '')).strip()
        student_name = str(row.get(student_name_col, '')).strip()
        turma_name = str(row.get(turma_name_col, '')).strip() # Novo
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
                "Nome da Turma": turma_name, # Novo
                "Número Original": original_phone,
                "Número Padronizado (E.164)": cleaned_phone_e164, 
                "Visualização VCF": formatted_phone 
            })
            
        else:
            # Coleta os dados completos e o motivo da falha (Módulo 26: Construtor de Respostas)
            
            # Chama a AI para explicar o defeito
            ai_explanation = explain_phone_defect_with_ai(original_phone, failure_reason)
            
            # Adiciona os metadados do erro à linha completa do DataFrame
            failed_entry = {
                "Índice_Linha_Original": index + 1,
                "Nome do Responsável": responsible_name, 
                "Nome do Aluno": student_name, 
                "Nome da Turma": turma_name, # Novo
                "Telefone": original_phone, # Novo
                "Motivo_da_Falha": failure_reason or "Nome ou Número Limpo Inválido.",
                "Explicação_AI": ai_explanation
            }
            # Combina os metadados com todos os dados da linha original
            # O operador '|' para dicionários (PEP 584) é usado para mesclar
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
            
            # --- NOVO: Chamada da AI para Mapeamento de Colunas ---
            try:
                # Módulo 16: Geração de Meta-Prompts
                # Módulo 26: Construtor de Respostas
                sample_row = df.iloc[0].to_dict()
                
                with st.spinner("🤖 Analisando cabeçalhos com IA para mapeamento automático de colunas..."):
                    mapped_cols = detect_columns_with_ai(columns, sample_row)
                    
                # Extrai os resultados mapeados
                responsible_name_col = mapped_cols.get('responsible_name_col')
                student_name_col = mapped_cols.get('student_name_col')
                phone_col = mapped_cols.get('phone_col')
                turma_name_col = mapped_cols.get('turma_name_col')
                
                # Verifica se a AI conseguiu identificar todas as colunas (ou se retornou 'NÃO ENCONTRADO')
                required_fields_map = {
                    "Nome do Responsável": responsible_name_col,
                    "Nome do Aluno": student_name_col,
                    "Telefone": phone_col,
                    "Nome da Turma": turma_name_col
                }
                
                missing_or_unfound_cols = {friendly_name: col_name for friendly_name, col_name in required_fields_map.items() if col_name is None or col_name == 'NÃO ENCONTRADO' or col_name not in columns}
                
                if missing_or_unfound_cols:
                    unfound_names = ", ".join(missing_or_unfound_cols.keys())
                    st.error(f"❌ A IA não conseguiu mapear automaticamente as seguintes colunas: {unfound_names}. Por favor, verifique se os nomes das colunas no seu arquivo são claros.")
                    return
                
                # Se o mapeamento foi bem-sucedido
                st.success("✅ Mapeamento de colunas concluído com sucesso via IA!")

            except Exception as e:
                st.error(f"❌ Erro Crítico na Detecção Automática por IA. O aplicativo não pode prosseguir. Detalhes: {e}")
                return
            
            # =========================================================================
            # Mapeamento de Colunas FIXO (Resultado da AI)
            # =========================================================================
            
            # Exibe as colunas fixas (Somente para informação do usuário)
            st.subheader("Colunas Mapeadas Automaticamente:")
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.markdown(f"**Nome do Responsável:** `{responsible_name_col}`")
                st.markdown(f"**Nome do Aluno:** `{student_name_col}`")
            with col_info2:
                st.markdown(f"**Nome da Turma:** `{turma_name_col}`")
                st.markdown(f"**Número de Telefone:** `{phone_col}`")

            
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
                            st.session_state['turma_name_col'], # Novo
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
                        st.subheader("❌ Lista de Números que Falharam (Dados Completos + Explicação AI)")
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
                            "Explicação_AI": st.column_config.Column(
                                "Explicação_AI",
                                width="large",
                                help="Diagnóstico da AI para o formato incorreto."
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
                            "Explicação_AI"
                        ]
                        
                        # Garante que apenas colunas existentes sejam usadas
                        existing_cols = [col for col in failed_columns_order if col in failed_df.columns]
                        failed_df = failed_df[existing_cols]

                        # Filtrar o column_config para apenas colunas existentes e usáveis
                        config_to_use = {k: v for k, v in failed_columns_config.items() if k in existing_cols}

                        st.dataframe(
                            failed_df, 
                            column_config=config_to_use, # Aplica a configuração para estender a visualização
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
                        
                        contact_name = f"{responsible_name} / {student_name}" # Nome de exibição no log da API
                        
                        # Módulo 22: Otimização de Código - Usa nova tupla de retorno
                        cleaned_phone, failure_reason = clean_and_standardize_phone(original_phone, st.session_state['default_cc'])
                        
                        current_result = {
                            "Nome do Responsável": responsible_name, # Novo
                            "Nome do Aluno": student_name, # Novo
                            "Número Original": original_phone,
                            "Status": "...",
                            "Detalhe da Falha": ""
                        }

                        if not cleaned_phone:
                            failure_count += 1
                            # NOTE: Aqui não chamamos a AI para manter o foco do Streamlit na API, mas 
                            # a lógica de padronização é a mesma.
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
                                responsible_name # Passa o nome do responsável para o placeholder
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
