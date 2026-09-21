document.addEventListener('DOMContentLoaded', function () {
    // 1. Máscara Cédula (000-000000-0000X)
    const inputCedula = document.getElementById('cedula');
    if (inputCedula) {
        inputCedula.addEventListener('input', function (e) {
            let val = e.target.value.replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
            let numeros = val.replace(/[^0-9]/g, '').substring(0, 13);
            let letra = val.replace(/[^A-Z]/g, '').slice(-1);
            let formateado = '';

            if (numeros.length > 0) formateado += numeros.substring(0, 3);
            if (numeros.length > 3) formateado += '-' + numeros.substring(3, 9);
            if (numeros.length > 9) formateado += '-' + numeros.substring(9, 13);
            if (numeros.length === 13 && letra) formateado += letra;

            e.target.value = formateado;
        });
    }

    // 2. Máscara INSS (0000000-0)
    const inputInss = document.getElementById('numero_inss');
    if (inputInss) {
        inputInss.addEventListener('input', function (e) {
            let val = e.target.value.replace(/[^0-9]/g, '').substring(0, 8);
            e.target.value = (val.length > 7) ? val.substring(0, 7) + '-' + val.substring(7, 8) : val;
        });
    }

    // 3. Formato de Salario
    const salarioDisplay = document.getElementById('salario_display');
    const salarioBaseHidden = document.getElementById('salario_base');

    if (salarioDisplay && salarioBaseHidden) {
        function formatMoneda(valor) {
            let num = parseFloat(valor);
            return isNaN(num) ? '' : 'C$ ' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }

        if (salarioBaseHidden.value && salarioBaseHidden.value !== '0') {
            salarioDisplay.value = formatMoneda(salarioBaseHidden.value);
        }

        salarioDisplay.addEventListener('focus', function () {
            salarioDisplay.value = (salarioBaseHidden.value && salarioBaseHidden.value !== '0') ? salarioBaseHidden.value : '';
        });

        salarioDisplay.addEventListener('blur', function () {
            let rawVal = salarioDisplay.value.replace(/[^0-9.]/g, '');
            let num = parseFloat(rawVal);
            if (!isNaN(num)) {
                salarioBaseHidden.value = num;
                salarioDisplay.value = formatMoneda(num);
            } else {
                salarioBaseHidden.value = '0';
                salarioDisplay.value = '';
            }
        });

        salarioDisplay.addEventListener('input', function () {
            salarioBaseHidden.value = salarioDisplay.value.replace(/[^0-9.]/g, '') || '0';
        });
    }
});