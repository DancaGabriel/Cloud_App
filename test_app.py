import pytest, os
from app import app as flask_app 
from app import EXCHANGE_RATE_API_KEY as flask_module_api_key


@pytest.fixture()
def app():
 
    yield flask_app
@pytest.fixture()
def client(app):
    return app.test_client()

def test_home_page_status_code(client):
    response = client.get('/') 
    assert response.status_code == 200 

def test_api_key_loading_in_app_module():
    
    environment_set_key = os.getenv('EXCHANGE_RATE_API_KEY')

    if environment_set_key:
        print(f"INFO: Test rulează cu EXCHANGE_RATE_API_KEY='{environment_set_key}' setat în mediu.")
        assert flask_module_api_key == environment_set_key
    else:
        print("INFO: Test rulează FĂRĂ EXCHANGE_RATE_API_KEY setat în mediu.")
        assert flask_module_api_key is None

