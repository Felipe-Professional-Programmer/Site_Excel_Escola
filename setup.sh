#!/bin/bash

# Cria o diretório de configuração do Streamlit, se não existir
mkdir -p ~/.streamlit/

# Cria o arquivo de configuração do Streamlit.
# As configurações de segurança e host são cruciais para rodar em ambientes de nuvem.
echo "[server]" > ~/.streamlit/config.toml
echo "enableCORS = false" >> ~/.streamlit/config.toml
echo "enableXsrfProtection = false" >> ~/.streamlit/config.toml
echo "headless = true" >> ~/.streamlit/config.toml

# O Render irá fornecer a porta via variável de ambiente $PORT