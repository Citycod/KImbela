# test_minimal_socket.py - UPDATED (fix handle_ping)
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-secret'

# Initialize Socket.IO with threading
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

@socketio.on('connect')
def handle_connect():
    print('✅ Client connected')
    emit('connected', {'message': 'Welcome!'})

@socketio.on('disconnect')
def handle_disconnect():
    print('❌ Client disconnected')

@socketio.on('ping')
def handle_ping(data=None):  # Accept optional data parameter
    print(f'🏓 Ping received: {data}')
    return {'message': 'pong', 'data_received': data}

@app.route('/')
def index():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Socket.IO Minimal Test</title>
            <script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>
        </head>
        <body>
            <h1>Minimal Socket.IO Test</h1>
            <div id="log"></div>
            <script>
                const log = (msg) => {
                    document.getElementById('log').innerHTML += '<div>' + msg + '</div>';
                };
                
                // Connect
                const socket = io();
                
                socket.on('connect', () => log('✅ Connected'));
                socket.on('connected', (data) => log('📨: ' + JSON.stringify(data)));
                socket.on('disconnect', () => log('❌ Disconnected'));
                
                // Test ping after 1 second
                setTimeout(() => {
                    socket.emit('ping', {test: 'data'}, (response) => {
                        log('🏓 Response: ' + JSON.stringify(response));
                    });
                }, 1000);
            </script>
        </body>
        </html>
    ''')

if __name__ == '__main__':
    print("🚀 Starting minimal Socket.IO test server on port 5001...")
    socketio.run(app, debug=True, port=5001, allow_unsafe_werkzeug=True)