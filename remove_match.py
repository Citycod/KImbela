import re

with open('templates/user_dashboard.html', 'r') as f:
    content = f.read()

# Remove the sidebar <li>...</li>
content = re.sub(r'\s*<li>\s*<a href="\{\{\s*url_for\(\'match\.requests\'\)\s*\}\}">\s*<i class="bi bi-heart"></i> Match\s*</a>\s*</li>', '', content)

# Remove the `mobile-feed-ad lg:hidden` wrappers that contain matchmaking-banner
content = re.sub(r'\s*<div class="mobile-feed-ad lg:hidden">\s*<div class="matchmaking-banner.*?</div>\s*</div>\s*</div>', '', content, flags=re.DOTALL)

# Remove standalone matchmaking-banners
content = re.sub(r'\s*<!-- Add a Matchmaking Banner.*?-->', '', content, flags=re.DOTALL)
content = re.sub(r'\s*<div class="matchmaking-banner.*?<div class="matchmaking-orbits".*?</div>\s*</div>\s*</div>', '', content, flags=re.DOTALL)
content = re.sub(r'\s*<div class="matchmaking-banner.*?<div class="matchmaking-orbits".*?</div>\s*</div>', '', content, flags=re.DOTALL)

# Remove all match.requests / view_requests <a> tags with preceding comments
content = re.sub(r'\s*<!-- Match Making Request Form -->\s*<a href="\{\{\s*url_for\(\'match\.requests\'\)\s*\}\}".*?</a>', '', content, flags=re.DOTALL)
content = re.sub(r'\s*<!-- View Match Requests -->\s*<a href="\{\{\s*url_for\(\'match\.view_requests\'\)\s*\}\}".*?</a>', '', content, flags=re.DOTALL)
content = re.sub(r'\s*<a href="\{\{\s*url_for\(\'match\.requests\'\)\s*\}\}".*?</a>', '', content, flags=re.DOTALL)
content = re.sub(r'\s*<a href="\{\{\s*url_for\(\'match\.view_requests\'\)\s*\}\}".*?</a>', '', content, flags=re.DOTALL)

with open('templates/user_dashboard.html', 'w') as f:
    f.write(content)

print("Done removing Match features")
