(function($) {
    $(document).ready(function() {
        // Aggiungi l'attributo 'multiple' al campo file
        const inputField = $('#id_images');  // Campo di input per l'upload
        inputField.attr('multiple', true);  // Forza la selezione multipla

        inputField.on('change', function() {
            const files = inputField[0].files;
            const fileList = $('#file-list');
            
            // Pulisce la lista dei file precedenti
            fileList.empty();

            // Mostra i file selezionati
            for (let i = 0; i < files.length; i++) {
                fileList.append('<li>' + files[i].name + '</li>');
            }
        });
    });
})(django.jQuery);
