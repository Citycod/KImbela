from flask import current_app, send_from_directory, render_template
import os
from . import core_bp

@core_bp.route('/sw.js')
def service_worker():
    """Serve the Service Worker from the root scope."""
    # Ensure it's served as application/javascript
    response = send_from_directory(
        os.path.join(current_app.root_path, 'static'), 
        'sw.js',
        mimetype='application/javascript'
    )
    # Browsers might cache sw.js, we prevent it here for safety, though PWA standards also bypass cache
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@core_bp.route('/offline')
def offline():
    """Serve the offline fallback page."""
    return render_template('offline.html')
