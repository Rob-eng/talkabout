# English Teacher AI Bot

Este é um bot de Telegram construído em Python, atuando como um Professor de Inglês Particular com IA. O bot utiliza a API da OpenAI para fornecer conversação, correções em tempo real e relatórios de feedback em profundidade.

## Funcionalidades
1. **Conversação Adaptativa:** Responde pelo contexto e mantém conversas engajantes.
2. **Correções em Tempo Real:** Fornece correções `[Quick Correction]` curtas no final das frases.
3. **Modo Tradutor:** Para palavras isoladas, fornece tradução, classe gramatical e um exemplo, auxiliando no aprendizado.
4. **Trigger de 5 Minutos (Feedback Profundo):** Um monitoramento de inatividade que, após 5 minutos, gera um `[Deep Feedback Report]` das últimas interações.

## Arquitetura e Deploy (Railway + Docker)
O bot está conteinerizado utilizando **Docker**, feito sob medida para ser hospedado no **Railway.app** ou outro provedor de nuvem. 

### Variáveis de Ambiente Necessárias
Crie um arquivo `.env` na raiz (baseado no `.env.example`) ou adicione as seguintes variáveis na plataforma (Railway):
- `TELEGRAM_BOT_TOKEN`: Token gerado pelo BotFather no Telegram.
- `OPENAI_API_KEY`: Chave da API da OpenAI (com créditos e acesso a Whisper/TTS/GPT-4o).

## Como rodar localmente (via Docker)
1. Construa a imagem: `docker build -t eng-bot .`
2. Rode o container: `docker run --env-file .env eng-bot`
