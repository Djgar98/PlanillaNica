document.addEventListener('DOMContentLoaded', function () {
    
    // 1. Ocultar alertas de mensajes flash automáticamente después de 4 segundos
    const alertList = document.querySelectorAll('.alert-dismissible');
    alertList.forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 4000);
    });

    // 2. Confirmación personalizada en acciones destructivas (Desactivar/Eliminar)
    const confirmButtons = document.querySelectorAll('[data-confirm]');
    confirmButtons.forEach(function (button) {
        button.addEventListener('click', function (e) {
            const message = this.getAttribute('data-confirm') || '¿Estás seguro de realizar esta acción?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });

    // 3. Auto-enfocar el primer campo en formularios al abrir una vista
    const firstInput = document.querySelector('form input:not([type="hidden"]):not([readonly])');
    if (firstInput) {
        firstInput.focus();
    }
});