# Usa uma imagem oficial leve do Python
FROM python:3.11-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Instala ffmpeg e dependências do sistema (necessário para processar arquivos de áudio ogg/mp4 do Telegram)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Copia os arquivos de requerimentos e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o restante do código para o container
COPY . .

# Comando para iniciar o bot
CMD ["python", "bot.py"]
