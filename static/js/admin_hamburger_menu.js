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
    }
}
