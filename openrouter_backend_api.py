# Módulo 21: Suporte Multi-Linguagem (Python Idioms)
# Servidor Flask que expõe um endpoint para que o frontend possa 
# chamar a API OpenRouter de forma segura (sem expor a chave de API no cliente).

from flask import Flask, request, jsonify
import requests
import json
import os
from typing import Dict, Any

# Módulo 4: Simulação de Integrações - Chave de API vinculada
# ATENÇÃO: Em produção, carregue a chave de uma variável de ambiente (ex: os.environ['OPENROUTER_API_KEY']).
OPENROUTER_API_KEY = "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"
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "tngtech/deepseek-r1t2-chimera:free"

app = Flask(__name__)

# Configuração para permitir requisições CORS do frontend.
# Em um ambiente de produção real, use um domínio específico em vez de "*".
@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'POST')
    return response

def _call_openrouter_api(ai_prompt: str, api_key: str) -> Dict[str, Any]:
    """Função interna para chamar a API OpenRouter."""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": ai_prompt
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://127.0.0.1:5000", # Referência para o backend
        "X-Title": "Python Flask Backend", 
    }

    try:
        response = requests.post(
            url=API_URL,
            headers=headers,
            json=payload,
            timeout=30 
        )
        response.raise_for_status() 
        return response.json()

    except requests.exceptions.RequestException as err:
        app.logger.error(f"Erro ao chamar OpenRouter API: {err}")
        return {"error": "Falha na comunicação com a IA."}

@app.route('/api/detect-columns', methods=['POST'])
def detect_columns_endpoint():
    """
    Endpoint de API para receber dados do frontend e chamar a IA.
    Recebe: { "headers": [...], "sample_row": {...} }
    """
    if not request.is_json:
        return jsonify({"error": "Missing JSON in request"}), 400
    
    data = request.get_json()
    headers = data.get('headers')
    sample_row = data.get('sample_row')

    if not headers or not sample_row:
        return jsonify({"error": "Missing 'headers' or 'sample_row' in request body"}), 400

    # Módulo 40: Deployment Wrapper - Prompt Estruturado (ATUALIZADO com Deep System Prompt e Vetor Textual)
    # Este é o prompt unificado, garantindo que o System Prompt venha "antes de qualquer coisa".
    ai_prompt = f"""
# DEEP SYSTEM PROMPT: ANALISTA DE DADOS E MAPEAMENTO
Você é um Analista de Dados de Alto Nível com foco em extração de metadados de planilhas.
Sua única tarefa é mapear colunas de planilhas para campos semânticos.
Você DEVE retornar APENAS um objeto JSON válido, contendo as chaves 'name_key' e 'number_key'.
- 'name_key' deve ser o nome EXATO da coluna que representa o nome completo ou nome de contato.
- 'number_key' deve ser o nome EXATO da coluna que representa o telefone ou número de contato.
Não inclua texto explicativo, introdução, ou qualquer formatação Markdown extra (como ```json).
O seu trabalho se resume a retornar o JSON final.

# DADOS CONVERTIDOS DA TABELA EXCEL (VETOR TEXTUAL)
A tabela Excel foi convertida para o seguinte formato de vetor textual para análise:

COLUNAS (Títulos):
[{', '.join(headers)}]

LINHA DE AMOSTRA (Valores):
{json.dumps(sample_row, ensure_ascii=False, indent=2)}
Com base nas COLUNAS e na LINHA DE AMOSTRA fornecidas, identifique as chaves 'name_key' e 'number_key'.

Retorne APENAS o JSON conforme instruído no Deep System Prompt.
"""
        
    # Chama a função principal que interage com a API OpenRouter
    api_result = _call_openrouter_api(ai_prompt, OPENROUTER_API_KEY)
    
    if "error" in api_result:
        return jsonify(api_result), 500
        
    try:
        ai_response_text = api_result['choices'][0]['message']['content'].strip()
        # Limpa e tenta parsear a string JSON da IA
        clean_json_text = ai_response_text.replace('```json', '').replace('```', '').strip()
        final_result = json.loads(clean_json_text)
        
        # Módulo 26: Retorna a resposta JSON limpa para o frontend
        return jsonify(final_result), 200

    except (KeyError, IndexError, json.JSONDecodeError) as e:
        app.logger.error(f"Erro de parsing ou estrutura de resposta da IA: {e}")
        return jsonify({"error": "Invalid response structure from AI model"}), 500


if __name__ == '__main__':
    # Instrução: Para rodar o servidor, abra o terminal e execute: python openrouter_backend_api.py
    print("--- INICIANDO SERVIDOR FLASK ---")
    print("Execute este script e mantenha-o rodando.")
    print("O frontend (index.html) fará requisições para [http://127.0.0.1:5000/api/detect-columns](http://127.0.0.1:5000/api/detect-columns)")
    app.run(debug=True, port=5000)