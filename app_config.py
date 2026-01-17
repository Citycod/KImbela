# app_config.py - UPDATED (fix eventlet issues)
from flask import Flask, g, request, flash, redirect, url_for, render_template
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
from flask import jsonify
from werkzeug.exceptions import RequestEntityTooLarge
import time
from scheduler import init_birthday_scheduler
from flask import send_from_directory, abort

# Import extensions (make sure socketio is initialized with threading)
from extensions import db, bcrypt, login_manager, mail, csrf, cache, socketio

load_dotenv()

# Initialize birthday scheduler
init_birthday_scheduler()


def create_app():
    app = Flask(__name__)

    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["PREFERRED_URL_SCHEME"] = "https"

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(error):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "File is too large! Maximum size is 100MB.",
                    }
                ),
                413,
            )
        else:
            flash("File is too large! Maximum file size is 100MB.", "danger")
            return redirect(url_for("user.user_dashboard"))

    @app.route("/uploads/<path:filename>")
    def serve_uploads(filename):
        upload_folder = app.config["UPLOAD_FOLDER"]
        file_path = os.path.join(upload_folder, filename)

        if not os.path.exists(file_path):
            abort(404)

        return send_from_directory(upload_folder, filename)

    # ========== BASIC APP CONFIG ==========
    app.config["MAX_CONTENT_LENGTH"] = 400 * 1024 * 1024  # 100MB
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "uploads")
    app.config["ALLOWED_EXTENSIONS"] = {"jpg", "jpeg", "png", "gif", "mp4", "mov"}
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ========== SECURITY & SESSION ==========
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-12345")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)

    # ========== CACHE CONFIG ==========
    app.config["CACHE_TYPE"] = "SimpleCache"
    app.config["CACHE_DEFAULT_TIMEOUT"] = 300

    # ========== DATABASE CONFIG ==========
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("SQLALCHEMY_DATABASE_URI")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": 20,
        "max_overflow": 40,
        "pool_timeout": 30,
    }

    import resend

    # ========== EMAIL CONFIG ==========
    # app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    # app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
    # app.config["MAIL_USE_TLS"] = True
    # app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    # app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    # app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")

    # ========== EMAIL CONFIG ==========
    # Configure Resend
    resend.api_key = os.getenv("RESEND_API_KEY", "")
    app.config["RESEND_API_KEY"] = os.getenv("RESEND_API_KEY", "")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv(
        "MAIL_DEFAULT_SENDER", "noreply@resend.dev"
    )

    # ========== SOCKET.IO CONFIG ==========
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-12345")

    # ========== INITIALIZE EXTENSIONS ==========
    csrf.init_app(app)
    cache.init_app(app)
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    mail.init_app(app)

    # IMPORTANT: Initialize Socket.IO with minimal config
    # Don't pass extra parameters that cause issues
    socketio.init_app(app)

    # ========== REGISTER BLUEPRINTS ==========
    def register_blueprints():
        """Register all blueprints"""
        from authentication.authenticate import auth
        from users.user import user as user_blueprint
        from marketplace.market import market as market_blueprint
        from admin.admin import admin as admin_blueprint
        from matchmaking.matchmake import match as matchmaking_blueprint
        from payments.payments import payments as payments_blueprint
        from messages.messaging import messaging as message_blueprint

        app.register_blueprint(auth)
        app.register_blueprint(user_blueprint)
        app.register_blueprint(message_blueprint)
        app.register_blueprint(admin_blueprint)
        app.register_blueprint(payments_blueprint)
        app.register_blueprint(matchmaking_blueprint)
        app.register_blueprint(market_blueprint)

    register_blueprints()

    # ========== IMPORT SOCKET.IO EVENT HANDLERS ==========
    # Use the simplified version
    try:
        import socketio_events

        print("✅ Socket.IO event handlers imported successfully")
    except Exception as e:
        print(f"⚠️ Could not import Socket.IO handlers: {e}")

    # ========== CONTEXT PROCESSORS ==========
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf())

    @app.context_processor
    def inject_now():
        return {"now": datetime.utcnow()}

    # ========== TEMPLATE FILTERS ==========
    @app.template_filter("time_ago")
    def time_ago_filter(timestamp):
        if timestamp is None:
            return "Never"

        cache_key = f"time_ago_{hash(str(timestamp))}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        now = datetime.utcnow()
        diff = now - timestamp

        if diff.days > 365:
            result = f"{diff.days // 365}y ago"
        elif diff.days > 30:
            result = f"{diff.days // 30}mo ago"
        elif diff.days > 0:
            result = f"{diff.days}d ago"
        elif diff.seconds > 3600:
            result = f"{diff.seconds // 3600}h ago"
        elif diff.seconds > 60:
            result = f"{diff.seconds // 60}m ago"
        else:
            result = "just now"

        cache.set(cache_key, result, timeout=30)
        return result

    # ========== DATABASE SESSION CLEANUP ==========
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    # ========== PERFORMANCE MONITORING ==========
    @app.before_request
    def before_request():
        g.start_time = time.time()

    @app.after_request
    def after_request(response):
        if hasattr(g, "start_time"):
            diff = time.time() - g.start_time
            if diff > 1.0:
                app.logger.warning(
                    f"Slow request: {request.method} {request.path} "
                    f"took {diff:.2f} seconds"
                )
        return response

    # ========== UPDATE LAST SEEN ==========
    @app.before_request
    def update_last_seen():
        from flask_login import current_user

        if current_user.is_authenticated:
            if (
                not current_user.last_seen
                or (datetime.utcnow() - current_user.last_seen).seconds > 300
            ):
                current_user.last_seen = datetime.utcnow()
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()

    # ========== SIMPLE TEST ROUTE ==========
    @app.route("/socket-test")
    def socket_test():
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Socket.IO Test</title>
            <script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>
        </head>
        <body>
            <h1>Socket.IO Test</h1>
            <button onclick="connect()">Connect</button>
            <button onclick="ping()">Ping</button>
            <div id="output"></div>

            <script>
                let socket = null;
                const output = document.getElementById('output');

                function log(msg) {
                    output.innerHTML += '<div>' + msg + '</div>';
                }

                function connect() {
                    socket = io();
                    socket.on('connect', () => log('✅ Connected'));
                    socket.on('disconnect', () => log('❌ Disconnected'));
                    socket.on('connect_error', (err) => log('❌ Error: ' + err.message));
                }

                function ping() {
                    if (socket) {
                        socket.emit('ping', {}, (response) => {
                            log('🏓 Response: ' + JSON.stringify(response));
                        });
                    }
                }
            </script>
        </body>
        </html>
        """

    return app


# Create the app instance
app = create_app()
print("✅ App created successfully")


@app.route("/test-messaging")
def test_messaging():
    """Test messaging functionality"""
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Messaging Test</title>
        <script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; }}
            .log {{ background: #f5f5f5; padding: 10px; border-radius: 5px; margin: 10px 0; height: 300px; overflow-y: auto; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
            button {{ padding: 10px; margin: 5px; }}
        </style>
    </head>
    <body>
        <h1>Messaging System Test</h1>
        <p>User: {current_user.full_name} (ID: {current_user.id})</p>

        <div>
            <button onclick="connect()">Connect Socket</button>
            <button onclick="ping()">Test Ping</button>
            <button onclick="getFriends()">Load Friends</button>
        </div>

        <div>
            <input id="friendId" placeholder="Friend ID" type="number">
            <input id="message" placeholder="Message">
            <button onclick="sendMessage()">Send Message</button>
        </div>

        <div id="log" class="log"></div>

        <script>
            let socket = null;
            const logElement = document.getElementById('log');

            function log(msg, type = 'info') {{
                const time = new Date().toLocaleTimeString();
                const div = document.createElement('div');
                div.className = type;
                div.textContent = `[${{time}}] ${{msg}}`;
                logElement.appendChild(div);
                logElement.scrollTop = logElement.scrollHeight;
            }}

            function connect() {{
                if (socket) socket.disconnect();

                socket = io({{
                    transports: ['websocket', 'polling']
                }});

                socket.on('connect', () => {{
                    log('✅ Connected to Socket.IO', 'success');
                }});

                socket.on('connected', (data) => {{
                    log(`📨 Server: ${{JSON.stringify(data)}}`, 'success');
                }});

                socket.on('disconnect', (reason) => {{
                    log(`⚠️ Disconnected: ${{reason}}`);
                }});

                socket.on('error', (data) => {{
                    log(`❌ Error: ${{JSON.stringify(data)}}`, 'error');
                }});

                socket.on('new_message', (data) => {{
                    log(`📨 New message: ${{JSON.stringify(data)}}`, 'success');
                }});

                socket.on('message_sent', (data) => {{
                    log(`✅ Message sent: ${{JSON.stringify(data)}}`, 'success');
                }});

                socket.on('chat_joined', (data) => {{
                    log(`💬 Joined chat: ${{JSON.stringify(data)}}`, 'success');
                }});
            }}

            function ping() {{
                if (socket && socket.connected) {{
                    socket.emit('ping', {{test: 'data'}}, (response) => {{
                        log(`🏓 Ping response: ${{JSON.stringify(response)}}`, 'success');
                    }});
                }} else {{
                    log('⚠️ Not connected', 'error');
                }}
            }}

            function getFriends() {{
                fetch('/api/messaging/friends')
                    .then(r => r.json())
                    .then(data => {{
                        if (data.success) {{
                            log(`👥 Friends loaded: ${{data.friends.length}}`, 'success');
                            data.friends.forEach(friend => {{
                                log(`  • ${{friend.name}} (ID: ${{friend.id}}, Online: ${{friend.online}})`);
                            }});
                        }} else {{
                            log(`❌ Failed to load friends: ${{data.error}}`, 'error');
                        }}
                    }})
                    .catch(e => log(`❌ Error: ${{e}}`, 'error'));
            }}

            function sendMessage() {{
                const friendId = document.getElementById('friendId').value;
                const message = document.getElementById('message').value;

                if (!friendId || !message) {{
                    log('⚠️ Please enter friend ID and message', 'error');
                    return;
                }}

                if (socket && socket.connected) {{
                    socket.emit('send_message', {{
                        friend_id: parseInt(friendId),
                        content: message
                    }});
                    log(`📤 Sending message to ${{friendId}}: "${{message}}"`);
                }} else {{
                    log('⚠️ Not connected to Socket.IO', 'error');
                }}
            }}

            // Auto-connect
            window.onload = connect;
        </script>
    </body>
    </html>
    """


@app.route("/api/messaging/friends")
@login_required
def get_messaging_friends():
    """Get friends with last message info for messaging"""
    try:
        friends = []
        for friend in current_user.friends:
            # Get last message
            last_message = (
                Message.query.filter(
                    (
                        (Message.sender_id == current_user.id)
                        & (Message.receiver_id == friend.id)
                    )
                    | (
                        (Message.sender_id == friend.id)
                        & (Message.receiver_id == current_user.id)
                    )
                )
                .order_by(Message.timestamp.desc())
                .first()
            )

            # Count unread messages
            unread_count = Message.query.filter_by(
                sender_id=friend.id, receiver_id=current_user.id, status="delivered"
            ).count()

            friends.append(
                {
                    "id": friend.id,
                    "name": friend.full_name,
                    "avatar": friend.profile_pic
                    or url_for("static", filename="assets/img/default-avatar.png"),
                    "is_online": friend.is_online,
                    "last_message": last_message.content if last_message else None,
                    "last_message_time": (
                        last_message.timestamp.isoformat() if last_message else None
                    ),
                    "unread_count": unread_count,
                }
            )

        return jsonify({"success": True, "friends": friends})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/messaging/send", methods=["POST"])
@login_required
def send_message_api():
    """Send a message via HTTP (fallback)"""
    try:
        data = request.get_json()
        receiver_id = data.get("receiver_id")
        content = data.get("content")

        if not receiver_id or not content:
            return jsonify({"success": False, "error": "Missing data"}), 400

        receiver = User.query.get_or_404(receiver_id)

        # Create message
        message = Message(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            content=content,
            status="delivered",
        )
        db.session.add(message)
        db.session.commit()

        # Prepare response
        message_data = {
            "id": message.id,
            "sender_id": message.sender_id,
            "receiver_id": message.receiver_id,
            "content": message.content,
            "timestamp": message.timestamp.isoformat(),
            "status": message.status,
            "is_mine": True,
            "sender_name": current_user.full_name,
            "sender_avatar": current_user.profile_pic
            or url_for("static", filename="assets/img/default-avatar.png"),
        }

        return jsonify({"success": True, "message": message_data})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/messaging/mark-read/<int:friend_id>", methods=["POST"])
@login_required
def mark_messages_read(friend_id):
    """Mark all messages from friend as read"""
    try:
        Message.query.filter_by(
            sender_id=friend_id, receiver_id=current_user.id, status="delivered"
        ).update({"status": "read"})
        db.session.commit()

        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
