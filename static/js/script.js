document.addEventListener('DOMContentLoaded', function() {
    // ... (codul pentru meniul hamburger - rămâne la fel ca în varianta funcțională) ...
    const hamburgerMenuIcon = document.getElementById('hamburgerMenuIcon');
    const mobileDropdownMenu = document.getElementById('mobileDropdownMenu');

    if (hamburgerMenuIcon && mobileDropdownMenu) {
        hamburgerMenuIcon.addEventListener('click', function(event) {
            event.stopPropagation(); 
            const isMenuOpen = mobileDropdownMenu.classList.toggle('open');
            hamburgerMenuIcon.setAttribute('aria-expanded', isMenuOpen);
            mobileDropdownMenu.setAttribute('aria-hidden', !isMenuOpen);
            
            if (isMenuOpen) {
                hamburgerMenuIcon.innerHTML = '&#x2715;'; 
            } else {
                hamburgerMenuIcon.innerHTML = '&#9776;'; 
            }
        });

        document.addEventListener('click', function(event) {
            if (!mobileDropdownMenu || !hamburgerMenuIcon) return;
            const isClickInsideMenu = mobileDropdownMenu.contains(event.target);
            const isClickOnHamburger = hamburgerMenuIcon.contains(event.target);

            if (!isClickInsideMenu && !isClickOnHamburger && mobileDropdownMenu.classList.contains('open')) {
                mobileDropdownMenu.classList.remove('open');
                hamburgerMenuIcon.setAttribute('aria-expanded', 'false');
                mobileDropdownMenu.setAttribute('aria-hidden', 'true');
                hamburgerMenuIcon.innerHTML = '&#9776;';
            }
        });
    }

    // --- Codul pentru ratele de schimb ---
    const currentRatesBtn = document.getElementById('fetchCurrentRatesBtn');
    const currentRatesContainer = document.getElementById('currentRatesContainer');
    
    const frankfurterBtn = document.getElementById('fetchFrankfurterBtn');
    const frankfurterDateInput = document.getElementById('frankfurterDateInput');
    const frankfurterRatesContainer = document.getElementById('frankfurterRatesContainer');

    const baseCurrencySelect = document.getElementById('baseCurrencySelect');
    let currentSelectedBaseCurrency = 'USD'; 

    if (baseCurrencySelect) {
        baseCurrencySelect.value = currentSelectedBaseCurrency; 
        baseCurrencySelect.addEventListener('change', function() {
            currentSelectedBaseCurrency = this.value;
            if(currentRatesContainer) currentRatesContainer.innerHTML = '<p class="placeholder">Moneda de bază schimbată. Apasă butonul pentru actualizare.</p>';
            if(frankfurterRatesContainer) frankfurterRatesContainer.innerHTML = '<p class="placeholder">Moneda de bază schimbată. Selectează o dată și apasă butonul.</p>';
        });
    }

    function renderRates(data, containerElement) {
        if (!containerElement) return;
        if (data.error) {
            let errorMsg = `<p class="error">Eroare: ${data.error}</p>`;
            if(data.details && data.details['error-type']) {
                errorMsg += `<p class="error-detail">Tip eroare API: ${data.details['error-type']}</p>`;
            } else if (data.details && data.details.message) { 
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
            const targetCurrencies = ['EUR', 'RON', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF', 'USD']; 
            for (const currency of targetCurrencies) {
                if (currency === (data.base_code || data.base)) continue; 
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
        if (!containerElement) return;
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
            fetchDataAndDisplay(`/get-exchange-rates?base=${currentSelectedBaseCurrency}`, currentRatesContainer);
        });
    }

    // --- ÎNCEPE BLOCUL CORECTAT PENTRU FRANKFURTER ---
    if (frankfurterBtn) {
        const todayJS = new Date();
        const yesterdayJS = new Date(todayJS);
        yesterdayJS.setDate(todayJS.getDate() - 1);
        
        // CORECTURĂ AICI: Numele variabilei a fost corectat din 'constइस्लामाबाद' în 'const yyyy'
        const yyyy = yesterdayJS.getFullYear(); 
        const mm = String(yesterdayJS.getMonth() + 1).padStart(2, '0');
        const dd = String(yesterdayJS.getDate()).padStart(2, '0');
        
        // Acum 'yyyy' este definit corect și poate fi folosit mai jos
        const maxDateString = `${yyyy}-${mm}-${dd}`; 
        const minDateString = "1999-01-04";

        if (frankfurterDateInput) {
            frankfurterDateInput.value = maxDateString; 
            frankfurterDateInput.max = maxDateString;
            frankfurterDateInput.min = minDateString; 
        }

        frankfurterBtn.addEventListener('click', function() {
            const selectedDateStr = frankfurterDateInput.value;
            if (!selectedDateStr) {
                if(frankfurterRatesContainer) frankfurterRatesContainer.innerHTML = '<p class="error">Te rog selectează o dată.</p>';
                return;
            }

            const selectedDateParts = selectedDateStr.split('-').map(Number);
            const selectedDateObj = new Date(Date.UTC(selectedDateParts[0], selectedDateParts[1] - 1, selectedDateParts[2]));

            const minDateParts = minDateString.split('-').map(Number);
            const minDateObj = new Date(Date.UTC(minDateParts[0], minDateParts[1] - 1, minDateParts[2]));
            
            const maxDateParts = maxDateString.split('-').map(Number); // Folosește maxDateString care utilizează yyyy, mm, dd corecte
            const maxDateObj = new Date(Date.UTC(maxDateParts[0], maxDateParts[1] - 1, maxDateParts[2]));
            
            if (selectedDateObj < minDateObj || selectedDateObj > maxDateObj) {
                 if(frankfurterRatesContainer) frankfurterRatesContainer.innerHTML = `<p class="error">Data trebuie să fie între ${minDateString.split('-').reverse().join('.')} și ${maxDateString.split('-').reverse().join('.')}.</p>`;
                 return;
            }
            fetchDataAndDisplay(`/get-frankfurter-historical-rates?date=${selectedDateStr}&base=${currentSelectedBaseCurrency}`, frankfurterRatesContainer);
        });
    }
});