import os
import glob
import re

nav_html = '''<nav class="navbar">
    <a href="/" class="logo"><i class="fa-solid fa-bolt" style="color:#38bdf8; margin-right:5px;"></i> ReliefAI</a>
    <div class="nav-links">
        <a href="/"><i class="fa-solid fa-house"></i> Home</a>
        {% if session.get('user_id') %}
            <a href="/report"><i class="fa-solid fa-file-shield"></i> Report Emergency</a>
            {% if session.get('role') == 'admin' %}
                <a href="/dashboard"><i class="fa-solid fa-chart-line"></i> Dashboard</a>
                <a href="/admin"><i class="fa-solid fa-shield-halved"></i> Admin</a>
            {% endif %}
            <span style="color: #10b981; font-size: 13px; margin: 0 10px; border-left: 1px solid #334155; padding-left: 10px;">Hello, <b>{{ (session.get('user') or 'User').title() }}</b> <span style="color:#94a3b8; font-size:11px;">({{ session.get('role', 'user') }})</span></span>
            <a href="/logout" style="color: #ef4444;"><i class="fa-solid fa-right-from-bracket"></i> Logout</a>
        {% else %}
            <a href="/login"><i class="fa-solid fa-right-to-bracket"></i> Login</a>
            <a href="/register"><i class="fa-solid fa-user-plus"></i> Register</a>
        {% endif %}
    </div>
</nav>'''

for f_path in glob.glob('templates/*.html'):
    with open(f_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = re.sub(r'<nav class="navbar">.*?</nav>', nav_html, content, flags=re.DOTALL)
    
    with open(f_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
print("Updated navbars safely.")
