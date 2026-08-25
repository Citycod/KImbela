import sys

with open('templates/user_dashboard.html', 'r') as f:
    content = f.read()

target = """      <!-- In MOBILE SIDEBAR section, replace the Groups item with: -->
      <!-- Mobile Groups Dropdown -->

      <div class="dropdown relative">
        <div
          class="sidebar-item flex items-center p-3 rounded-lg text-fb-text hover:bg-gradient-to-r hover:from-blue-50 hover:to-purple-50 transition-all duration-300 mb-2 cursor-pointer group"
          data-bs-toggle="groups-dropdown-mobile">
          <i
            class="bi bi-people-fill mr-3 text-lg text-blue-600 group-hover:text-purple-600 transition-colors duration-300"></i>
          <span class="font-medium group-hover:text-blue-700 transition-colors duration-300">Groups</span>
          <i
            class="bi bi-chevron-down ml-auto text-sm text-gray-400 group-hover:text-blue-500 transform group-hover:rotate-180 transition-all duration-300"></i>
        </div>

        <div
          class="dropdown-menu absolute left-0 mt-1 w-85 bg-white rounded-2xl shadow-2xl overflow-hidden z-10 hidden border border-gray-100"
          id="groupsDropdownMenuMobile" style="
                background: linear-gradient(135deg, #ffffff 0%, #f8faff 100%);
              ">
          <!-- Same beautiful content as desktop -->
          <div class="p-4 border-b border-gray-100 bg-gradient-to-r from-blue-600 to-purple-600 text-white">
            <div class="flex items-center justify-between">
              <div>
                <h4 class="font-bold text-lg">Discover Groups</h4>
                <p class="text-blue-100 text-sm mt-1">
                  Connect with amazing communities
                </p>
              </div>
              <div class="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center">
                <i class="bi bi-people-fill text-lg"></i>
              </div>
            </div>
          </div>

          <div class="max-h-64 overflow-y-auto custom-scrollbar bg-gradient-to-b from-white to-blue-50/30"
            id="groupsListMobile">
            <div class="flex flex-col items-center justify-center p-8 text-gray-500">
              <div class="relative mb-4">
                <div class="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
                <div class="absolute inset-0 flex items-center justify-center">
                  <i class="bi bi-people text-blue-600"></i>
                </div>
              </div>
              <p class="text-sm font-medium">Loading amazing groups...</p>
              <p class="text-xs mt-1 text-gray-400">
                Finding the best communities for you
              </p>
            </div>
          </div>
        </div>
      </div>"""

replacement = """      <a href="{{ url_for('user.groups_page') }}"
        class="sidebar-item flex items-center p-3 rounded-lg text-fb-text hover:bg-fb-gray transition-colors mb-2">
        <i class="bi bi-people mr-3 text-lg"></i> Groups
      </a>"""

if target in content:
    content = content.replace(target, replacement)
    with open('templates/user_dashboard.html', 'w') as f:
        f.write(content)
    print("Replaced successfully.")
else:
    print("Target not found.")

