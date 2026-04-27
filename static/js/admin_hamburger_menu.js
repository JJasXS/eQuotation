// Admin Hamburger Menu Functions
function toggleAdminHamburgerMenu() {
    const dropdown = document.getElementById('admin-hamburger-dropdown');
    const overlay = document.getElementById('admin-hamburger-overlay');
    if (dropdown) {
        dropdown.classList.toggle('active');
    }
    if (overlay) {
        overlay.classList.toggle('active');
    }
}

function toggleAdminSubmenu(event, submenuId) {
    event.preventDefault();
    event.stopPropagation();
    
    const submenu = document.getElementById(submenuId);
    const parentLink = event.currentTarget;
    
    if (submenu && parentLink) {
        submenu.classList.toggle('active');
        parentLink.classList.toggle('active');

        // Persist expanded state so the menu stays open after navigation.
        try {
            const key = 'adminHamburgerExpandedSubmenus';
            const raw = window.localStorage ? localStorage.getItem(key) : null;
            const current = raw ? JSON.parse(raw) : {};
            current[submenuId] = submenu.classList.contains('active');
            if (window.localStorage) {
                localStorage.setItem(key, JSON.stringify(current));
            }
        } catch (e) {
            // ignore storage errors
        }
    }
}

function restoreAdminHamburgerExpandedState() {
    try {
        const key = 'adminHamburgerExpandedSubmenus';
        const raw = window.localStorage ? localStorage.getItem(key) : null;
        if (!raw) return;
        const current = JSON.parse(raw);
        if (!current || typeof current !== 'object') return;

        Object.entries(current).forEach(([submenuId, isActive]) => {
            const submenu = document.getElementById(submenuId);
            if (!submenu) return;
            submenu.classList.toggle('active', Boolean(isActive));

            // Also toggle the matching parent link (.has-submenu) for arrow rotation.
            const parentLink = document.querySelector(`[onclick*="'${submenuId}'"]`);
            if (parentLink) {
                parentLink.classList.toggle('active', Boolean(isActive));
            }
        });
    } catch (e) {
        // ignore
    }
}

document.addEventListener('DOMContentLoaded', function () {
    restoreAdminHamburgerExpandedState();
});
