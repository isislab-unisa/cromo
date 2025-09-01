document.addEventListener('DOMContentLoaded', function() {
    const select = document.getElementById('id_external_id');
    if (!select) return;

    fetch('https://cos2.cityopensource.com/api/cromo/spaces/5b165325-183f-86fb-0210-9718f29af21e/locations?format=json')
        .then(response => response.json())
        .then(data => {
            select.innerHTML = '<option value="">Seleziona un POI</option>';
            data.forEach(poi => {
                const opt = document.createElement('option');
                opt.value = poi.id;
                opt.text = poi.title;
                opt.dataset.lat = poi.lat;
                opt.dataset.lon = poi.lon;
                opt.dataset.image = poi.image;
                select.add(opt);
            });
        });

    select.addEventListener('change', function() {
        const opt = select.selectedOptions[0];
        if (!opt || !opt.value) return;

        document.getElementById('id_title').value = opt.text;

        const lat = opt.dataset.lat;
        const lon = opt.dataset.lon;
        const locField = document.getElementById('id_location');
        if (locField) {
            locField.value = lat + ',' + lon;
        }

    });
});
