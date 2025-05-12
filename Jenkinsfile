pipeline {
    agent any 

    stages {
        stage('Checkout SCM') { 
            steps {
                echo 'Preluare cod din GitHub...'
                checkout scm
                echo 'Cod preluat cu succes.'
                sh 'ls -la'
            }
        }
        // Aici vom adăuga mai târziu etape pentru:
        // - Instalare dependențe (pip install)
        // - Testare (dacă e cazul)
        // - Build (ex: creare imagine Docker)
        // - Deploy
    }

    post { // Acțiuni care rulează la finalul pipeline-ului
        always { // Rulează indiferent de succesul sau eșecul pipeline-uluigit st
            echo 'Pipeline finalizat.'
        }
    }
}