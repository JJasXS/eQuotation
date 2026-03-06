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
