# Deploy no Render

## Arquivos de Configuração Criados

1. **runtime.txt** - Especifica a versão do Python (3.11.0)
2. **Procfile** - Comando para iniciar a aplicação (`web: gunicorn run:app`)
3. **requirements.txt** - Dependências do Python (já atualizado com gunicorn)

## Variáveis de Ambiente Necessárias no Render

No painel do Render, adicione as seguintes variáveis de ambiente:

### Configurações Básicas
- `FLASK_ENV` = `production`
- `SECRET_KEY` = (gere uma chave secreta forte)
- `DEBUG` = `False`

### Supabase
- `SUPABASE_URL` = (sua URL do Supabase)
- `SUPABASE_KEY` = (sua chave pública do Supabase)
- `SUPABASE_SERVICE_ROLE_KEY` = (sua chave de serviço do Supabase)

### Stripe
- `STRIPE_PUBLIC_KEY` = (sua chave pública do Stripe)
- `STRIPE_SECRET_KEY` = (sua chave secreta do Stripe)
- `STRIPE_WEBHOOK_SECRET` = (seu segredo do webhook do Stripe)
- `STRIPE_PRICE_ID_BR_MONTHLY` = (ID do preço mensal Brasil)
- `STRIPE_PRICE_ID_BR_YEARLY` = (ID do preço anual Brasil)
- `STRIPE_PRICE_ID_UK_MONTHLY` = (ID do preço mensal UK)
- `STRIPE_PRICE_ID_UK_YEARLY` = (ID do preço anual UK)

### Email (Brevo)
- `BREVO_API_KEY` = (sua chave da API do Brevo)
- `BREVO_SENDER_EMAIL` = (seu email de envio, ex: noreply@luminaflow.com)

### URLs
- `BASE_URL` = (URL do seu site no Render, ex: https://seu-app.onrender.com)

## Passos para Deploy

1. **Fazer push do código para o GitHub**
   ```bash
   git add .
   git commit -m "Add Render deployment files"
   git push
   ```

2. **Criar conta no Render**
   - Acesse https://render.com
   - Crie uma conta ou faça login

3. **Criar novo Web Service**
   - Clique em "New +" → "Web Service"
   - Conecte seu repositório do GitHub
   - Selecione o repositório do Lumina Flow
   - Configure as opções:
     - **Name**: lumina-flow (ou o nome que preferir)
     - **Region**: Escolha a região mais próxima
     - **Branch**: main
     - **Runtime**: Python 3
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `gunicorn run:app`

4. **Configurar Variáveis de Ambiente**
   - Vá para a seção "Environment" na configuração do serviço
   - Adicione todas as variáveis listadas acima

5. **Deploy**
   - Clique em "Create Web Service"
   - O Render vai fazer o deploy automaticamente
   - Aguarde o build terminar (pode levar alguns minutos)

6. **Acessar a Aplicação**
   - O Render vai fornecer uma URL (ex: https://lumina-flow.onrender.com)
   - Acesse a URL para verificar se está funcionando

## Troubleshooting

### Erro de Módulo Não Encontrado
- Verifique se todas as dependências estão no `requirements.txt`
- Execute `pip install -r requirements.txt` localmente para testar

### Erro de Variável de Ambiente
- Verifique se todas as variáveis de ambiente foram adicionadas no Render
- Verifique se os nomes estão exatamente iguais (case-sensitive)

### Erro de Conexão com Supabase
- Verifique se as credenciais do Supabase estão corretas
- Verifique se as tabelas foram criadas no Supabase

### Erro de Stripe
- Verifique se as chaves do Stripe estão corretas
- Verifique se os webhooks estão configurados corretamente

## Observações Importantes

- O arquivo `.env` NÃO deve ser commitado (já está no .gitignore)
- A pasta `venv/` NÃO deve ser commitada (já está no .gitignore)
- O Render instala automaticamente as dependências do `requirements.txt`
- O Render usa automaticamente a porta 80 (HTTP) e 443 (HTTPS)
- O Render fornece HTTPS gratuito com certificados SSL automáticos
