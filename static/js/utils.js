/* ============================================================================
   ICP Ladda Admin — Shared Utilities
   Toast notifications + Confirm modal (replaces alert/confirm)
   ============================================================================ */

/**
 * Show a toast notification
 * @param {string} message - Text to display
 * @param {'info'|'success'|'error'|'warning'} type - Toast type
 * @param {number} duration - Auto-dismiss in ms (default 4000)
 */
function showToast(message, type, duration) {
  if (type === undefined) type = 'info';
  if (duration === undefined) duration = 4000;

  var container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    container.setAttribute('role', 'alert');
    container.setAttribute('aria-live', 'polite');
    document.body.appendChild(container);
  }

  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.innerHTML = '<span>' + escapeHtmlUtil(message) + '</span><button class="toast-dismiss" aria-label="Dismiss">&times;</button>';
  container.appendChild(toast);

  toast.querySelector('.toast-dismiss').onclick = function() { removeToast(toast); };
  setTimeout(function() { removeToast(toast); }, duration);
}

/**
 * Remove a toast with animation
 */
function removeToast(toast) {
  if (!toast || !toast.parentNode) return;
  toast.style.animation = 'toast-out 0.3s ease forwards';
  setTimeout(function() {
    if (toast.parentNode) toast.parentNode.removeChild(toast);
  }, 300);
}

/**
 * Show a confirm modal (replaces window.confirm)
 * @param {string} message - Question to ask
 * @param {Function} onConfirm - Callback if user confirms
 * @param {string} [confirmText] - Confirm button text (default "Confirm")
 * @param {string} [cancelText] - Cancel button text (default "Cancel")
 */
function showConfirm(message, onConfirm, confirmText, cancelText) {
  if (!confirmText) confirmText = 'Confirm';
  if (!cancelText) cancelText = 'Cancel';

  var overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML =
    '<div class="modal-box">' +
      '<div class="modal-body">' + escapeHtmlUtil(message) + '</div>' +
      '<div class="modal-actions">' +
        '<button class="btn btn-ghost" id="modalCancel">' + cancelText + '</button>' +
        '<button class="btn btn-primary" id="modalConfirm">' + confirmText + '</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(overlay);

  overlay.querySelector('#modalCancel').onclick = function() {
    document.body.removeChild(overlay);
  };
  overlay.querySelector('#modalConfirm').onclick = function() {
    document.body.removeChild(overlay);
    onConfirm();
  };
  overlay.onclick = function(e) {
    if (e.target === overlay) document.body.removeChild(overlay);
  };

  // Focus the confirm button
  overlay.querySelector('#modalConfirm').focus();
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtmlUtil(str) {
  var div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
