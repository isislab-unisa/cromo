document.addEventListener('DOMContentLoaded', function() {
    const select = document.getElementById('id_external_id');
    if (!select) return;

    if (window.jQuery && jQuery().select2) {
        let localExternalIds = [];

        fetch('/list/')
            .then(response => response.json())
            .then(localData => {
                localExternalIds = localData.features
                    .map(f => f.properties.cityopensource_id)
                    .filter(Boolean);

                $(select).select2({
                    theme: 'unfold',
                    placeholder: 'Select a Cromo POI or create from scratch',
                    ajax: {
                        url: '/proxy-id-cromopoi/',
                        dataType: 'json',
                        processResults: function(data) {
                            // Filter out POIs already in local DB
                            const filtered = data.filter(
                                poi => !localExternalIds.includes(poi.id)
                            );

                            return {
                                results: filtered.map(poi => ({
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
                    if (titleField) titleField.value = data.text;
                    if (locField) locField.value = `${data.lat},${data.lon}`;
                });
            })
            .catch(err => {
                console.error('Error fetching local POIs:', err);
            });
    } else {
        console.error('jQuery or Select2 not found!');
    }
});
