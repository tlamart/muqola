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
