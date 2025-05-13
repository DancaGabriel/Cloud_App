document.getElementById('fetchRatesBtn').addEventListener('click', function() {
    const ratesContainer = document.getElementById('ratesContainer');
    ratesContainer.innerHTML = '<p class="loading">Se încarcă datele...</p>';

    fetch('/get-exchange-rates')
        .then(response => {
            if (!response.ok) {
                return response.json().then(errData => {
                    throw new Error(errData.error || `Eroare HTTP: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                ratesContainer.innerHTML = `<p class="error">Eroare: ${data.error}</p>`;
                if(data.details && data.details['error-type'] === 'invalid-key') {
                    ratesContainer.innerHTML += `<p class="error-detail">Verifică dacă API Key-ul este corect și activ.</p>`;
                } else if (data.details && data.details['error-type'] === 'unsupported-code') {
                    ratesContainer.innerHTML += `<p class="error-detail">Codul valutar de bază nu este suportat de API.</p>`;
                }
                console.error("API Error details:", data.details || data);
            } else if (data.rates) {
                let content = `<h2>Rate de schimb pentru ${data.base_code}</h2>`;
                content += `<p class="update-time">Ultima actualizare: ${data.last_update || 'N/A'}</p>`;
                content += '<ul>';
                const targetCurrencies = ['EUR', 'RON', 'GBP', 'JPY', 'CAD', 'AUD'];
                for (const currency of targetCurrencies) {
                    if (data.rates[currency]) {
                        content += `<li>1 ${data.base_code} = ${data.rates[currency].toFixed(4)} ${currency}</li>`;
                    }
                }
                content += '</ul>';
                ratesContainer.innerHTML = content;
            } else {
                ratesContainer.innerHTML = '<p class="error">Nu s-au primit datele așteptate de la server.</p>';
            }
        })
        .catch(error => {
            console.error('Eroare la fetch:', error);
            ratesContainer.innerHTML = `<p class="error">A apărut o eroare la preluarea datelor: ${error.message}. Verifică consola pentru detalii.</p>`;
        });
});