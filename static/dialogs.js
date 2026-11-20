"use strict";

// Sans JS, le contenu reste dépliable. Le dialogue natif gère le focus modal.
if (typeof HTMLDialogElement !== "undefined" && HTMLDialogElement.prototype.showModal) {
  for (const disclosure of document.querySelectorAll("[data-dialog]")) {
    const trigger = disclosure.querySelector(":scope > summary");
    const content = disclosure.querySelector(":scope > [data-dialog-content]");
    const title = content?.querySelector("[data-dialog-title]");
    if (!trigger || !content || !title?.id) continue;
    const openInitially = disclosure.open;
    const dialog = document.createElement("dialog");
    dialog.className = "modal";
    dialog.setAttribute("aria-labelledby", title.id);
    dialog.append(content);
    document.body.append(dialog);
    disclosure.open = false;
    trigger.setAttribute("aria-haspopup", "dialog");
    trigger.setAttribute("aria-expanded", "false");
    title.tabIndex = -1;

    function open() {
      dialog.showModal();
      trigger.setAttribute("aria-expanded", "true");
      title.focus();
    }
    trigger.addEventListener("click", event => { event.preventDefault(); open(); });
    for (const close of content.querySelectorAll("[data-dialog-close]")) {
      close.hidden = false;
      close.addEventListener("click", () => dialog.close());
    }
    dialog.addEventListener("close", () => {
      trigger.setAttribute("aria-expanded", "false");
      trigger.focus();
    });
    dialog.addEventListener("click", event => {
      if (event.target !== dialog) return;
      const bounds = dialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right ||
          event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
    });
    if (openInitially) open();
  }
}
