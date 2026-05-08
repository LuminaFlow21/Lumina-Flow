
import os
from lumina_flow import create_app

# Cria a aplicação usando a factory, com base no ambiente definido
env = os.getenv('FLASK_ENV', 'development')
app = create_app(env)

if __name__ == '__main__':
    # Executa a aplicação
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=app.config['DEBUG']
    )