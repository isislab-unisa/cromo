document.addEventListener('DOMContentLoaded', function() {
    const select = document.getElementById('id_external_id');
    if (!select) return;

    if (window.jQuery && jQuery().select2) {
        $(select).select2({
            theme: 'unfold',
            placeholder: 'Select a Cromo POI or create from scratch',
            ajax: {
                url: '/proxy-id-cromopoi/',
                dataType: 'json',
                processResults: function(data) {
                    return {
                        results: data.map(poi => ({
                            id: poi.id,
                            text: poi.title,
                            lat: poi.lat,
                            lon: poi.lon,
                            image: poi.image
                        }))
                    };
                }
            }
        });

        $(select).on('select2:select', function(e) {
            const data = e.params.data;
            const titleField = document.getElementById('id_title');
            const locField = document.getElementById('id_location');
            const preview = document.getElementById('external-poi-preview');

            if (titleField) titleField.value = data.text;
            if (locField) locField.value = `${data.lat},${data.lon}`;
        });
    } else {
        console.error('jQuery o Select2 non trovati!');
    }
});
