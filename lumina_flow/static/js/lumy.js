/**
 * Lumy Chatbot JavaScript - Simplified Version
 * Simple predefined Q&A without API dependencies
 */

(function() {
    'use strict';

    // DOM Elements
    const chatButton = document.getElementById('lumyChatButton');
    const chatModal = document.getElementById('lumyChatModal');
    const chatContainer = chatModal ? chatModal.querySelector('.lumy-chat-container') : null;
    const closeBtn = document.getElementById('lumyCloseBtn');
    const chatMessages = document.getElementById('lumyChatMessages');

    const SUPPORT_URL = 'https://wa.me/5511999999999';

    // State
    let isOpen = false;
    let qaPairs = [];
    let qaLoadPromise = null;
    let quickActionsRendered = false;

    function getDefaultQAs() {
        return [
            {
                label: 'Orçamentos',
                keywords: ['orçamento', 'orcamento', 'budget', 'criar orçamento', 'como fazer orçamento', 'gerar orçamento', 'novo orçamento'],
                answer: `Para criar um orçamento:

1. Acesse o menu "Orçamentos"
2. Clique em "Novo Orçamento"
3. Adicione os itens desejados
4. Defina o cliente e validade
5. Clique em "Gerar PDF"`,
                is_popular: true,
                order_index: 0
            },
            {
                label: 'Pagamentos',
                keywords: ['pagamento', 'pagar', 'forma de pagamento', 'cartão', 'atualizar pagamento', 'mudar pagamento'],
                answer: `Para atualizar sua forma de pagamento:

1. Acesse seu Perfil
2. Vá até a seção "Informações do Plano"
3. Clique em "Atualizar forma de pagamento"
4. Você será redirecionado para o Stripe para atualizar seus dados`,
                order_index: 1
            },
            {
                label: 'Assinatura',
                keywords: ['assinatura', 'plano', 'cancelar', 'upgrade'],
                answer: `Gerencie sua assinatura em:

1. Acesse seu Perfil
2. Vá até a seção de assinatura
3. Veja seu plano atual e opções disponíveis
4. Para cancelar ou reativar, use os botões disponíveis`,
                order_index: 2
            },
            {
                label: 'PDF',
                keywords: ['pdf', 'download', 'imprimir', 'exportar', 'baixar', 'arquivo', 'documento'],
                answer: `Para baixar ou imprimir PDF:

1. No orçamento desejado, clique no ícone de PDF
2. Escolha entre "Baixar" ou "Imprimir"
3. O PDF será gerado automaticamente

Os PDFs incluem logo e dados do cliente.`,
                order_index: 3
            },
            {
                label: 'Conta',
                keywords: ['conta', 'perfil', 'login', 'senha', 'esqueci senha', 'recuperar senha', 'dados pessoais', 'acesso'],
                answer: `Gerencie sua conta em:

1. Acesse seu Perfil
2. Edite seus dados pessoais
3. Altere sua senha em "Segurança"
4. Para excluir a conta, entre em contato com o suporte`,
                order_index: 4
            },
            {
                label: 'Suporte',
                keywords: ['suporte', 'ajuda', 'contato', 'falar com humano', 'atendimento', 'problema'],
                answer: `Para falar com o suporte:

📱 WhatsApp: Clique no botão de suporte
📧 Email: suporte@luminaflow.com
⏰ Horário: Seg-Sex, 9h às 18h`,
                order_index: 5
            }
        ];
    }

    function ensureQAsInitialized() {
        if (!qaPairs.length) {
            qaPairs = getDefaultQAs();
        }
    }

    // Load Q&A from backend
    async function loadQAPairs() {
        try {
            const response = await fetch('/dashboard/api/lumy/qa');
            if (!response.ok) {
                throw new Error(`Failed to load Q&A (${response.status})`);
            }
            const result = await response.json();
            
            if (result.success && result.qa_pairs) {
                qaPairs = [];
                result.qa_pairs.forEach(qa => {
                    if (qa.is_active) {
                        const keywords = (qa.keywords || '')
                            .split(',')
                            .map(k => k.trim())
                            .filter(Boolean);

                        if (!keywords.length && qa.label) {
                            keywords.push(qa.label.toLowerCase());
                        }

                        qaPairs.push({
                            id: qa.id,
                            label: qa.label || keywords[0] || 'Pergunta',
                            keywords,
                            answer: qa.answer,
                            is_popular: !!qa.is_popular,
                            order_index: qa.order_index ?? 0
                        });
                    }
                });

                qaPairs.sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0));
            }
            ensureQAsInitialized();
            if (isOpen && quickActionsRendered) {
                showQuickActions();
            }
        } catch (error) {
            console.error('Error loading Q&A pairs:', error);
            // Fallback to hardcoded Q&A if API fails
            qaPairs = getDefaultQAs();
            if (isOpen && quickActionsRendered) {
                showQuickActions();
            }
        }
    }

    // Initialize
    function init() {
        if (!chatButton || !chatModal) return;

        chatButton.addEventListener('click', toggleChat);
        if (closeBtn) closeBtn.addEventListener('click', closeChat);

        chatModal.addEventListener('click', (e) => {
            if (e.target === chatModal) closeChat();
        });

        // Load Q&A pairs from backend
        qaLoadPromise = loadQAPairs();
    }

    function toggleChat() {
        isOpen ? closeChat() : openChat();
    }

    async function openChat() {
        if (!qaLoadPromise) {
            qaLoadPromise = loadQAPairs();
        }
        try {
            await qaLoadPromise;
        } catch (error) {
            console.error('Error waiting Q&A load', error);
        }

        isOpen = true;
        chatModal.classList.add('lumy-open');

        if (chatMessages.children.length === 0) {
            showWelcomeMessage();
        }
    }

    function closeChat() {
        isOpen = false;
        chatModal.classList.remove('lumy-open');
    }

    function showWelcomeMessage() {
        const greeting = getGreeting();
        addMessage(greeting, 'bot');
        showQuickActions();
    }

    function getGreeting() {
        const hour = new Date().getHours();
        if (hour < 12) return 'Bom dia! 👋 Eu sou a Lumy. Como posso te ajudar?';
        if (hour < 18) return 'Boa tarde! 👋 Eu sou a Lumy. Como posso te ajudar?';
        return 'Boa noite! 👋 Eu sou a Lumy. Como posso te ajudar?';
    }

    function showQuickActions() {
        ensureQAsInitialized();

        const existing = chatMessages.querySelector('.lumy-quick-actions');
        if (existing) existing.remove();

        const quickActionsDiv = document.createElement('div');
        quickActionsDiv.className = 'lumy-quick-actions';

        qaPairs.forEach(action => {
            const btn = document.createElement('button');
            btn.className = 'lumy-quick-btn' + (action.is_popular ? ' lumy-quick-btn-popular' : '');
            btn.textContent = action.label || 'Pergunta';
            btn.addEventListener('click', () => {
                handleQuickAction(action);
            });
            quickActionsDiv.appendChild(btn);
        });

        chatMessages.appendChild(quickActionsDiv);
        quickActionsRendered = true;
    }

    function handleQuickAction(actionOrQuery) {
        ensureQAsInitialized();

        let actionData = null;
        if (typeof actionOrQuery === 'string') {
            actionData = qaPairs.find(qa => qa.keywords.some(keyword => actionOrQuery.toLowerCase().includes(keyword.toLowerCase())));
        } else {
            actionData = actionOrQuery;
        }

        const userLabel = actionData?.label || (typeof actionOrQuery === 'string' ? actionOrQuery : 'Pergunta');
        const answer = actionData?.answer || findAnswer(actionOrQuery || userLabel);

        removeTypingIndicator();
        addMessage(userLabel, 'user');
        addTypingIndicator();

        setTimeout(() => {
            removeTypingIndicator();
            addMessage(answer, 'bot');
        }, 500);
    }

    function addMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `lumy-message lumy-message-${sender}`;

        const avatar = sender === 'bot' ? `
            <div class="lumy-message-avatar">
                <img src="/static/images/lumy-profile.png" alt="Lumy" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                <div class="lumy-avatar-fallback" style="display: none;">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/>
                    </svg>
                </div>
            </div>
        ` : '';

        const content = `
            <div class="lumy-message-content">
                <p class="lumy-message-text">${escapeHtml(text)}</p>
            </div>
        `;

        messageDiv.innerHTML = avatar + content;
        chatMessages.appendChild(messageDiv);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function findAnswer(query) {
        ensureQAsInitialized();
        const lowerQuery = (query || '').toLowerCase();

        for (const qa of qaPairs) {
            for (const keyword of qa.keywords) {
                if (lowerQuery.includes(keyword.toLowerCase())) {
                    return qa.answer;
                }
            }
        }

        return `Selecione uma opção acima para obter ajuda:

📄 Orçamentos
💳 Pagamentos
📦 Assinatura
📑 PDF
👤 Conta
📞 Suporte`;
    }

    function addTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'lumy-message lumy-message-bot';
        typingDiv.id = 'lumyTyping';
        typingDiv.innerHTML = `
            <div class="lumy-message-avatar">
                <img src="/static/images/lumy-profile.png" alt="Lumy" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                <div class="lumy-avatar-fallback" style="display: none;">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/>
                    </svg>
                </div>
            </div>
            <div class="lumy-message-content">
                <div class="lumy-typing">
                    <div class="lumy-typing-dot"></div>
                    <div class="lumy-typing-dot"></div>
                    <div class="lumy-typing-dot"></div>
                </div>
            </div>
        `;
        chatMessages.appendChild(typingDiv);
    }

    function removeTypingIndicator() {
        const typing = document.getElementById('lumyTyping');
        if (typing) typing.remove();
    }

    function delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose to global scope
    window.Lumy = {
        open: openChat,
        close: closeChat,
        toggle: toggleChat
    };

})();
