pipeline {
    agent any

    environment {
        AWS_DEFAULT_REGION = 'eu-central-1' 
        ECR_REPOSITORY_NAME = 'cloud-app'    
        IMAGE_NAME = 'flask-app'
    }

    stages {
        stage('Checkout SCM') {
            steps {
                echo 'Preluare cod din GitHub...'
                checkout scm
                echo 'Cod preluat cu succes.'
                sh 'ls -la'
            }
        }

        stage('Build Docker Image') {
            steps {
                echo "Construire imagine Docker..."
                sh "docker build -t ${env.IMAGE_NAME}:build-${env.BUILD_NUMBER} ."
                echo "Imagine Docker construită: ${env.IMAGE_NAME}:build-${env.BUILD_NUMBER}"
            }
        }

        stage('Push to ECR') {
            steps {
                script {
                    echo "Obținere detalii AWS..."
                    def awsAccount = sh(script: 'aws sts get-caller-identity --query Account --output text', returnStdout: true).trim()
                    def ecrRegistry = "${awsAccount}.dkr.ecr.${env.AWS_DEFAULT_REGION}.amazonaws.com"
                    def localImageTag = "${env.IMAGE_NAME}:build-${env.BUILD_NUMBER}"
                    def ecrImageFullName = "${ecrRegistry}/${env.ECR_REPOSITORY_NAME}"
                    def ecrImageTag = "${ecrImageFullName}:build-${env.BUILD_NUMBER}"
                    def ecrImageLatestTag = "${ecrImageFullName}:latest"

                    echo "Autentificare la Amazon ECR: ${ecrRegistry}..."
                    sh "aws ecr get-login-password --region ${env.AWS_DEFAULT_REGION} | docker login --username AWS --password-stdin ${ecrRegistry}"

                    echo "Etichetare imagine pentru ECR..."
                    sh "docker tag ${localImageTag} ${ecrImageTag}"
                    sh "docker tag ${localImageTag} ${ecrImageLatestTag}"

                    echo "Publicare imagine în ECR repository ${env.ECR_REPOSITORY_NAME}..."
                    sh "docker push ${ecrImageTag}"
                    sh "docker push ${ecrImageLatestTag}"
                    echo "Imagine publicată cu succes în ECR."
                }
            }
            post {
                always {
                    script {
                        def awsAccount = sh(script: 'aws sts get-caller-identity --query Account --output text', returnStdout: true).trim()
                        def ecrRegistry = "${awsAccount}.dkr.ecr.${env.AWS_DEFAULT_REGION}.amazonaws.com"
                        def localImageTag = "${env.IMAGE_NAME}:build-${env.BUILD_NUMBER}"
                        def ecrImageFullName = "${ecrRegistry}/${env.ECR_REPOSITORY_NAME}"
                        def ecrImageTag = "${ecrImageFullName}:build-${env.BUILD_NUMBER}"
                        def ecrImageLatestTag = "${ecrImageFullName}:latest"

                        echo "Deautentificare de la ECR: ${ecrRegistry}..."
                        sh "docker logout ${ecrRegistry}"

                        echo "Ștergere imagine Docker locală..."
                    
                        sh script: "docker rmi -f ${ecrImageTag} ${ecrImageLatestTag} ${localImageTag}", returnStatus: true
                        echo "Curățare imagine locală finalizată (sau încercată)."
                    }
                }
            }
        }
    }

    post {
        always {
            echo 'Pipeline finalizat.'
        }
    }
}