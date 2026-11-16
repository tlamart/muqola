const status = document.getElementById('request-status');
function restore() {
  document.querySelectorAll('form[aria-busy="true"]').forEach(form => {
    form.removeAttribute('aria-busy');
    form.querySelectorAll('button[data-submitting]').forEach(button => {
      button.disabled = false;
      delete button.dataset.submitting;
    });
  });
  if (status) { status.hidden = true; }
}
window.addEventListener('pageshow', restore);
window.addEventListener('offline', () => {
  if (status) {
    status.textContent = 'Connexion interrompue. Vérifiez Mes prêts avant de répéter une action.';
    status.hidden = false;
  }
});
document.addEventListener('submit', event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  form.setAttribute('aria-busy', 'true');
  if (status) { status.textContent = 'Envoi en cours…'; status.hidden = false; }
  setTimeout(() => form.querySelectorAll('button[type="submit"]').forEach(button => {
    button.disabled = true;
    button.dataset.submitting = 'true';
  }), 0);
});

// Amélioration progressive : sans JS, la navigation reste entièrement visible.
const navigation = document.getElementById('site-navigation');
const menuButton = document.querySelector('.menu-toggle');
if (navigation && menuButton) {
  const mobileNavigation = window.matchMedia('(max-width: 1023px)');
  const menuLabel = menuButton.querySelector('.menu-label');
  let menuOpen = false;
  function synchronizeNavigation() {
    const wasFocused = navigation.contains(document.activeElement);
    const buttonWasFocused = document.activeElement === menuButton;
    menuButton.hidden = !mobileNavigation.matches;
    navigation.hidden = mobileNavigation.matches && !menuOpen;
    menuButton.setAttribute('aria-expanded', String(menuOpen && mobileNavigation.matches));
    if (menuLabel) menuLabel.textContent = menuOpen ? 'Fermer le menu' : 'Ouvrir le menu';
    if (navigation.hidden && wasFocused) menuButton.focus();
    if (!mobileNavigation.matches && buttonWasFocused) navigation.querySelector('a')?.focus();
  }
  menuButton.addEventListener('click', () => {
    menuOpen = !menuOpen;
    synchronizeNavigation();
  });
  mobileNavigation.addEventListener('change', () => {
    menuOpen = false;
    synchronizeNavigation();
  });
  navigation.addEventListener('click', event => {
    if (mobileNavigation.matches && event.target instanceof Element && event.target.closest('a')) {
      menuOpen = false;
      synchronizeNavigation();
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const accountMenu = navigation.querySelector('details[open]');
    if (accountMenu) {
      accountMenu.open = false;
      accountMenu.querySelector('summary')?.focus();
    } else if (menuOpen) {
      menuOpen = false;
      synchronizeNavigation();
      menuButton.focus();
    }
  });
  synchronizeNavigation();
}

// Sans image disponible, conserver le visuel local ; aucun gestionnaire inline.
function restoreGameCover(image) {
  if (image instanceof HTMLImageElement && image.hasAttribute('data-commons-image')) {
    image.hidden = true;
  }
}
document.addEventListener('error', event => restoreGameCover(event.target), true);
document.querySelectorAll('img[data-commons-image]').forEach(image => {
  if (image.complete && image.naturalWidth === 0) restoreGameCover(image);
});
