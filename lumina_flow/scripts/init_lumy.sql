    -- Lumy Chatbot Initialization Script
    -- Execute this in the Supabase SQL Editor

    -- Create lumy_qa table for quick actions
    CREATE TABLE IF NOT EXISTS lumy_qa (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        label VARCHAR(100) NOT NULL,
        keywords TEXT NOT NULL,
        answer TEXT NOT NULL,
        order_index INTEGER DEFAULT 0,
        is_popular BOOLEAN DEFAULT false,
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Create indexes for lumy_qa
    CREATE INDEX IF NOT EXISTS idx_lumy_qa_is_active ON lumy_qa(is_active);
    CREATE INDEX IF NOT EXISTS idx_lumy_qa_order_index ON lumy_qa(order_index);

    -- Insert initial Lumy Q&A pairs
    INSERT INTO lumy_qa (label, keywords, answer, order_index, is_popular, is_active) VALUES
    ('Orçamentos', 'orçamento, orcamento, budget, criar orçamento, como fazer orçamento, gerar orçamento, novo orçamento',
    'Para criar um orçamento:

    1. Acesse o menu "Orçamentos"
    2. Clique em "Novo Orçamento"
    3. Adicione os itens desejados
    4. Defina o cliente e validade
    5. Clique em "Gerar PDF"', 0, true, true),

    ('Pagamentos', 'pagamento, pagar, forma de pagamento, cartão, atualizar pagamento, mudar pagamento',
    'Para atualizar sua forma de pagamento:

    1. Acesse seu Perfil
    2. Vá até a seção "Informações do Plano"
    3. Clique em "Atualizar forma de pagamento"
    4. Você será redirecionado para o Stripe para atualizar seus dados', 1, false, true),

    ('Assinatura', 'assinatura, plano, cancelar, upgrade',
    'Gerencie sua assinatura em:

    1. Acesse seu Perfil
    2. Vá até a seção de assinatura
    3. Veja seu plano atual e opções disponíveis
    4. Para cancelar ou reativar, use os botões disponíveis', 2, false, true),

    ('PDF', 'pdf, download, imprimir, exportar, baixar, arquivo, documento',
    'Para baixar ou imprimir PDF:

    1. No orçamento desejado, clique no ícone de PDF
    2. Escolha entre "Baixar" ou "Imprimir"
    3. O PDF será gerado automaticamente

    Os PDFs incluem logo e dados do cliente.', 3, false, true),

    ('Conta', 'conta, perfil, login, senha, esqueci senha, recuperar senha, dados pessoais, acesso',
    'Gerencie sua conta em:

    1. Acesse seu Perfil
    2. Edite seus dados pessoais
    3. Altere sua senha em "Segurança"
    4. Para excluir a comunta, entre em contato com o suporte', 4, false, true),

    ('Suporte', 'suporte, ajuda, contato, falar com humano, atendimento, problema',
    'Para falar com o suporte:

    📱 WhatsApp: Clique no botão de suporte
    📧 Email: suporte@luminaflow.com
    ⏰ Horário: Seg-Sex, 9h às 18h', 5, false, true);

    -- Verify insertion
    SELECT label, order_index, is_active FROM lumy_qa ORDER BY order_index;
