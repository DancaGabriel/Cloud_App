document.addEventListener('DOMContentLoaded', function() {
    const currentRatesBtn = document.getElementById('fetchCurrentRatesBtn');
    const currentRatesContainer = document.getElementById('currentRatesContainer');
    
    const frankfurterBtn = document.getElementById('fetchFrankfurterBtn');
    const frankfurterDateInput = document.getElementById('frankfurterDateInput');
    const frankfurterRatesContainer = document.getElementById('frankfurterRatesContainer');

    function renderRates(data, containerElement) {
        if (data.error) {
            let errorMsg = `<p class="error">Eroare: ${data.error}</p>`;
            if(data.details && data.details['error-type']) {
                errorMsg += `<p class="error-detail">Tip eroare API: ${data.details['error-type']}</p>`;
            } else if (data.details && data.details.message) { // Specific pentru erori Frankfurter
                 errorMsg += `<p class="error-detail">Mesaj API: ${data.details.message}</p>`;
            }
            containerElement.innerHTML = errorMsg;
            console.error("API Error details:", data.details || data.error);
        } else if (data.rates) {
            let content = `<h2>Rate de schimb pentru ${data.base_code || data.base}</h2>`;
            if (data.last_update || data.date) { 
                content += `<p class="update-time">Data cursurilor: ${data.last_update || data.date}</p>`;
            }
            if (data.data_source) {
                content += `<p class="data-source-info"><i>Sursa datelor: ${data.data_source}</i></p>`;
            }
            content += '<ul>';
            const targetCurrencies = ['EUR', 'RON', 'GBP', 'JPY', 'CAD', 'AUD'];
            for (const currency of targetCurrencies) {
                if (data.rates[currency] !== undefined && data.rates[currency] !== null) {
                    content += `<li>1 ${data.base_code || data.base} = ${Number(data.rates[currency]).toFixed(4)} ${currency}</li>`;
                }
            }
            content += '</ul>';
            containerElement.innerHTML = content;
        } else {
            containerElement.innerHTML = '<p class="error">Nu s-au primit datele așteptate de la server.</p>';
        }
    }

    function fetchDataAndDisplay(apiUrl, containerElement) {
        containerElement.innerHTML = '<p class="loading">Se încarcă datele...</p>';
        fetch(apiUrl)
            .then(response => {
                return response.json().then(jsonResponse => {
                    if (!response.ok) {
                        jsonResponse.http_status = response.status; 
                        throw jsonResponse; 
                    }
                    return jsonResponse;
                });
            })
            .then(data => {
                renderRates(data, containerElement);
            })
            .catch(errorData => {
                console.error('Eroare la fetch sau procesare JSON:', errorData);
                renderRates({ 
                    error: errorData.error || errorData.message || `Eroare HTTP ${errorData.http_status || 'necunoscută'}`, 
                    details: errorData.details || errorData 
                }, containerElement);
            });
    }

    if (currentRatesBtn) {
        currentRatesBtn.addEventListener('click', function() {
            fetchDataAndDisplay('/get-exchange-rates', currentRatesContainer);
        });
    }

    if (frankfurterBtn) {
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(today.getDate() - 1);
        const yyyy = yesterday.getFullYear();
        const mm = String(yesterday.getMonth() + 1).padStart(2, '0');
        const dd = String(yesterday.getDate()).padStart(2, '0');
        
        if (frankfurterDateInput) {
            frankfurterDateInput.max = `${yyyy}-${mm}-${dd}`;
            frankfurterDateInput.min = "1999-01-04"; 
        }

        frankfurterBtn.addEventListener('click', function() {
            const selectedDate = frankfurterDateInput.value;
            if (!selectedDate) {
                frankfurterRatesContainer.innerHTML = '<p class="error">Te rog selectează o dată.</p>';
                return;
            }
            const dateObj = new Date(selectedDate);
            const minDate = new Date("1999-01-04");
            if (dateObj < minDate || dateObj > yesterday) {
                 frankfurterRatesContainer.innerHTML = `<p class="error">Data trebuie să fie între 04-01-1999 și ziua de ieri.</p>`;
                 return;
            }
            fetchDataAndDisplay(`/get-frankfurter-historical-rates?date=${selectedDate}&base=USD`, frankfurterRatesContainer);
        });
    }
});