import sys

with open('templates/user_dashboard.html', 'r') as f:
    lines = f.readlines()

# 1. Update Hamburger (line 74-77)
# Find: <button class="lg:hidden ... onclick="toggleMobileMenu()">
for i in range(70, 85):
    if 'class="lg:hidden' in lines[i] and 'toggleMobileMenu()' in lines[i]:
        lines[i] = '    <button class="p-2 rounded-xl border border-gray-200 hover:bg-gray-50 transition-colors mr-2 md:mr-4 flex items-center justify-center bg-white shadow-sm w-10 h-10" onclick="toggleMobileMenu()">\n'
        break

# 2. Update Search Bar (line 85-97)
for i in range(80, 105):
    if 'id="searchContainer"' in lines[i]:
        lines[i] = '  <div id="searchContainer"\n    class="flex justify-center flex-1 min-w-0 mx-4 lg:mx-10 searching mobile-hidden-search">\n'
    if 'class="relative w-full min-w-0 flex items-center"' in lines[i]:
        lines[i] = '    <div class="relative w-full max-w-2xl min-w-0 flex items-center">\n'
    if 'id="searchIconInner"' in lines[i+1] if i+1 < len(lines) else False:
        pass # The icon is updated below
    if 'id="globalSearch"' in lines[i]:
        # Replace the icon above it and the input
        # We know the structure:
        # <i id="searchIconInner" ...></i>
        # <input type="text" id="globalSearch" ... />
        pass

# It's safer to just replace the search block using string replace.
content = "".join(lines)

search_old = """      <i id="searchIconInner"
        class="bi bi-search absolute left-3 lg:left-4 top-1/2 transform -translate-y-1/2 text-fb-text-light text-base lg:text-lg"></i>
      <input type="text" id="globalSearch" placeholder="Search..."
        class="w-full pl-10 lg:pl-12 pr-3 lg:pr-4 py-2 bg-fb-gray rounded-full border border-gray-300 focus:border-fb-blue focus:ring-2 focus:ring-fb-blue focus:outline-none transition-all text-sm lg:text-base searching search_input" />"""

search_new = """      <i id="searchIconInner"
        class="bi bi-search absolute left-3 lg:left-4 top-1/2 transform -translate-y-1/2 text-gray-400 text-base"></i>
      <input type="text" id="globalSearch" placeholder="Search anything..."
        class="w-full pl-10 lg:pl-12 pr-16 py-2.5 bg-gray-50/80 rounded-xl border border-gray-200 focus:bg-white focus:border-purple-400 focus:ring-2 focus:ring-purple-100 focus:outline-none transition-all text-sm searching search_input shadow-sm" />
      <div class="absolute right-3 top-1/2 transform -translate-y-1/2 hidden md:flex items-center gap-1 text-gray-400" style="pointer-events: none;">
        <kbd class="px-1.5 py-0.5 text-[10px] font-semibold bg-white border border-gray-200 rounded shadow-sm font-sans">⌘</kbd>
        <kbd class="px-1.5 py-0.5 text-[10px] font-semibold bg-white border border-gray-200 rounded shadow-sm font-sans">K</kbd>
      </div>"""

content = content.replace(search_old, search_new)

# 3. Remove nav-icon-bar (lines 106-290ish)
# We find: <!-- Right side: Nav icons (same as sidebar) -->
# and delete until <!-- + Create Button -->
start_idx = content.find("  <!-- Right side: Nav icons (same as sidebar) -->")
end_idx = content.find("  <!-- + Create Button -->")
if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + content[end_idx:]

# 4. Replace right side icons
right_old = """  <!-- + Create Button -->
  <button class="kb-create-btn inline-flex" onclick="window.openModal('postModal')">
    <i class="bi bi-plus-lg"></i>
    <span class="btn-text hidden sm:inline">Create</span>
  </button>

  <!-- Messenger & Notifications (keep these on far right) -->
  <div
    class="flex items-center flex-shrink-0 space-x-1 lg:space-x-2 ml-1 sm:ml-2 lg:ml-4 border-l border-gray-200 pl-1 sm:pl-2 lg:pl-4">
    <!-- Mobile Search Toggle -->
    <button class="p-2 rounded-full hover:bg-fb-gray transition-colors md:hidden" onclick="toggleMobileSearch()">
      <i class="bi bi-search text-xl font-bold"></i>
    </button>
    <button id="openMessaging" onclick="window.openMessenger()"
      class="p-2 rounded-full hover:bg-fb-gray transition-colors relative">
      <img src="{{ url_for('static', filename='assets/img/message 1.png') }}" alt="chat" class="h-6 mr-2" />
      <span id="unreadMessagesBadge"
        class="notification-badge absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center hidden">0</span>
    </button>

    <div class="dropdown relative">
      <div class="p-2 rounded-full hover:bg-fb-gray transition-colors cursor-pointer relative" data-kb-toggle="dropdown"
        id="notificationDropdown">
        <img src="{{ url_for('static', filename='assets/img/notify 2.png') }}" alt="chat" class="h-6 mr-2" />
        <span
          class="notification-badge absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center hidden"
          id="notificationBadge">0</span>
      </div>"""

right_new = """  <div class="flex items-center flex-shrink-0 space-x-2 sm:space-x-4 ml-auto border-l border-gray-200 pl-3 sm:pl-5">
    
    <!-- Mobile Search Toggle -->
    <button class="p-2 rounded-full hover:bg-gray-100 transition-colors md:hidden text-gray-600" onclick="toggleMobileSearch()">
      <i class="bi bi-search text-xl"></i>
    </button>

    <!-- + Create Button -->
    <button class="w-10 h-10 rounded-xl bg-purple-600 hover:bg-purple-700 text-white flex items-center justify-center transition-colors shadow-sm hidden sm:flex" onclick="window.openModal('postModal')">
      <i class="bi bi-plus-lg text-lg"></i>
    </button>

    <!-- Messenger -->
    <button id="openMessaging" onclick="window.openMessenger()"
      class="w-10 h-10 rounded-full hover:bg-gray-100 flex items-center justify-center transition-colors relative text-gray-600">
      <i class="bi bi-chat-left-dots text-xl"></i>
      <span id="unreadMessagesBadge"
        class="notification-badge absolute top-0 -right-1 bg-purple-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center border border-white hidden">0</span>
    </button>

    <!-- Notifications -->
    <div class="dropdown relative">
      <div class="w-10 h-10 rounded-full hover:bg-gray-100 flex items-center justify-center transition-colors cursor-pointer relative text-gray-600" data-kb-toggle="dropdown"
        id="notificationDropdown">
        <i class="bi bi-bell text-xl"></i>
        <span
          class="notification-badge absolute top-0 -right-1 bg-yellow-400 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center border border-white hidden"
          id="notificationBadge">0</span>
      </div>"""

content = content.replace(right_old, right_new)

# 5. Replace User Avatar
avatar_old = """    <!-- User Avatar -->
    <a href="{{ url_for('user.profile', user_id=current_user.id) }}">
      <img src="{{ current_user.profile_pic or url_for('static', filename='assets/img/default-avatar.png') }}"
        alt="{{ current_user.first_name }}" class="kb-nav-avatar" />
    </a>"""

avatar_new = """    <!-- User Avatar -->
    <a href="{{ url_for('user.profile', user_id=current_user.id) }}" class="flex items-center p-1 pr-2 sm:pr-3 rounded-full hover:bg-gray-50 transition-colors border border-transparent hover:border-gray-200 ml-1">
      <div class="relative">
        <img src="{{ current_user.profile_pic or url_for('static', filename='assets/img/default-avatar.png') }}"
          alt="{{ current_user.first_name }}" class="w-8 h-8 rounded-full object-cover border border-gray-200" />
        <div class="absolute bottom-0 right-0 w-2.5 h-2.5 bg-green-500 border-2 border-white rounded-full"></div>
      </div>
      <span class="ml-2 text-sm font-semibold text-gray-700 hidden md:block">{{ current_user.first_name }}</span>
      <i class="bi bi-chevron-down ml-1 text-xs text-gray-500 hidden md:block"></i>
    </a>"""

content = content.replace(avatar_old, avatar_new)

with open('templates/user_dashboard.html', 'w') as f:
    f.write(content)

print("Done")
