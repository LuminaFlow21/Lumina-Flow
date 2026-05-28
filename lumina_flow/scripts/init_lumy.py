"""
Initialize Lumy Chatbot
Creates tables and inserts initial help articles
"""

import sys
import os

# Add parent directory to path
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, parent_dir)

from lumina_flow.help_handler import get_help_handler

def initialize_lumy():
    """Initialize Lumy chatbot tables and initial articles"""
    
    help_handler = get_help_handler()
    
    # Create tables
    print("Creating tables...")
    result = help_handler.create_tables()
    if result.get('success'):
        print("✓ Tables created successfully")
    else:
        print(f"✗ Error creating tables: {result.get('error')}")
        return
    
    # Insert initial articles
    print("\nInserting initial help articles...")
    
    articles = [
        {
            'category': 'Assinatura',
            'question': 'Como cancelar meu plano?',
            'answer': 'Você pode cancelar seu plano acessando:\n\nPerfil → Plano → Cancelar plano.\n\nSeu acesso continuará ativo até o final do período já pago. Após isso, você não será cobrado novamente.',
            'keywords': ['cancelar', 'plano', 'assinatura', 'desativar', 'encerrar'],
            'order_index': 1
        },
        {
            'category': 'PDF',
            'question': 'Como baixar PDF?',
            'answer': 'Para baixar o PDF do orçamento:\n\n1. Acesse o orçamento desejado\n2. Clique no botão "Baixar PDF" no topo da página\n3. O PDF será gerado e baixado automaticamente',
            'keywords': ['pdf', 'baixar', 'download', 'imprimir'],
            'order_index': 2
        },
        {
            'category': 'Orçamentos',
            'question': 'Como editar orçamento?',
            'answer': 'Para editar um orçamento:\n\n1. Acesse a lista de orçamentos\n2. Clique no orçamento que deseja editar\n3. Clique no botão "Editar"\n4. Faça as alterações desejadas\n5. Clique em "Salvar"',
            'keywords': ['editar', 'orçamento', 'modificar', 'alterar'],
            'order_index': 3
        },
        {
            'category': 'Pagamentos',
            'question': 'Como atualizar forma de pagamento?',
            'answer': 'Para atualizar sua forma de pagamento:\n\n1. Acesse seu Perfil\n2. Vá até a seção "Plano"\n3. Clique em "Atualizar forma de pagamento"\n4. Insira os novos dados do cartão\n5. Confirme a alteração',
            'keywords': ['pagamento', 'cartão', 'atualizar', 'alterar', 'forma'],
            'order_index': 4
        },
        {
            'category': 'Orçamentos',
            'question': 'Como compartilhar orçamento?',
            'answer': 'Para compartilhar um orçamento:\n\n1. Acesse o orçamento desejado\n2. Clique no botão "Compartilhar"\n3. Copie o link gerado\n4. Envie o link para seu cliente\n\nO cliente poderá visualizar o orçamento diretamente pelo link.',
            'keywords': ['compartilhar', 'enviar', 'link', 'cliente'],
            'order_index': 5
        },
        {
            'category': 'Assinatura',
            'question': 'Como mudar de plano?',
            'answer': 'Para mudar de plano:\n\n1. Acesse seu Perfil\n2. Vá até a seção "Plano"\n3. Clique em "Fazer upgrade" ou "Fazer downgrade"\n4. Escolha o novo plano\n5. Complete o processo de pagamento se necessário',
            'keywords': ['plano', 'mudar', 'upgrade', 'downgrade', 'trocar'],
            'order_index': 6
        },
        {
            'category': 'Conta',
            'question': 'Como alterar meu e-mail?',
            'answer': 'Para alterar seu e-mail:\n\n1. Acesse seu Perfil\n2. Clique no campo de e-mail\n3. Insira o novo e-mail\n4. Clique em "Salvar"\n\nVocê precisará verificar o novo e-mail antes de poder usá-lo.',
            'keywords': ['email', 'e-mail', 'alterar', 'mudar'],
            'order_index': 7
        },
        {
            'category': 'Pagamentos',
            'question': 'Pagamento não foi processado',
            'answer': 'Se seu pagamento não foi processado:\n\n1. Verifique se os dados do cartão estão corretos\n2. Confirme se há saldo suficiente\n3. Tente atualizar a forma de pagamento\n4. Se o problema persistir, entre em contato com o suporte',
            'keywords': ['pagamento', 'erro', 'falha', 'processado', 'cobrança'],
            'order_index': 8
        },
        {
            'category': 'Orçamentos',
            'question': 'Como criar novo orçamento?',
            'answer': 'Para criar um novo orçamento:\n\n1. Acesse o Dashboard\n2. Clique em "Criar Novo Orçamento"\n3. Preencha os dados do cliente\n4. Adicione os itens do orçamento\n5. Escolha o template\n6. Clique em "Criar"',
            'keywords': ['criar', 'novo', 'orçamento', 'adicionar'],
            'order_index': 9
        },
        {
            'category': 'Conta',
            'question': 'Como recuperar minha senha?',
            'answer': 'Para recuperar sua senha:\n\n1. Na tela de login, clique em "Esqueceu a senha?"\n2. Insira seu e-mail\n3. Clique em "Enviar link"\n4. Verifique seu e-mail e clique no link de recuperação\n5. Crie uma nova senha',
            'keywords': ['senha', 'recuperar', 'esqueci', 'reset'],
            'order_index': 10
        },
        {
            'category': 'PDF',
            'question': 'PDF não está sendo gerado',
            'answer': 'Se o PDF não está sendo gerado:\n\n1. Verifique se todos os campos obrigatórios estão preenchidos\n2. Tente recarregar a página\n3. Limpe o cache do navegador\n4. Se o problema persistir, entre em contato com o suporte',
            'keywords': ['pdf', 'erro', 'gerar', 'problema'],
            'order_index': 11
        },
        {
            'category': 'Problemas Técnicos',
            'question': 'O site está lento',
            'answer': 'Se o site está lento:\n\n1. Verifique sua conexão com a internet\n2. Limpe o cache do navegador\n3. Tente usar outro navegador\n4. Feche outras abas e programas que estejam consumindo recursos\n5. Se o problema persistir, tente novamente mais tarde',
            'keywords': ['lento', 'performance', 'carregando', 'demora'],
            'order_index': 12
        }
    ]
    
    success_count = 0
    for article in articles:
        result = help_handler.create_article(**article)
        if result.get('success'):
            success_count += 1
            print(f"✓ Created: {article['question']}")
        else:
            print(f"✗ Error creating article: {result.get('error')}")
    
    print(f"\n✓ {success_count}/{len(articles)} articles inserted successfully")
    print("\nLumy chatbot initialized successfully! 🎉")

if __name__ == '__main__':
    initialize_lumy()
