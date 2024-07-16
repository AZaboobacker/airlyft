import streamlit as st
from openai import OpenAI
import requests
from github import Github
from dotenv import load_dotenv
import os
import time
import re
import uuid
import ast
import base64
from pyairtable import Table
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Load environment variables from .env file
load_dotenv()

# Access secrets
openai_api_key = os.getenv("OPENAI_API_KEY")
github_token = os.getenv("MY_GITHUB_TOKEN")
heroku_api_key = os.getenv("HEROKU_API_KEY")
airtable_api_key = os.getenv("AIRTABLE_API_KEY")
airtable_base_id = os.getenv("AIRTABLE_BASE_ID")
airtable_table_name = os.getenv("AIRTABLE_TABLE_NAME")
google_creds_json = os.getenv("GOOGLE_CREDS_JSON")

# Ensure secrets are set
required_secrets = [
    openai_api_key, github_token, heroku_api_key, 
    airtable_api_key, airtable_base_id, airtable_table_name, google_creds_json
]

for secret in required_secrets:
    if not secret:
        st.error(f"{secret} not found. Please set the corresponding environment variable.")
        st.stop()

# Initialize OpenAI client
client = OpenAI(api_key=openai_api_key)

# Initialize Airtable client
airtable = Table(airtable_api_key, airtable_base_id, airtable_table_name)

st.title("App Idea to Deployed Application")

# Form for user input
with st.form("app_idea_form"):
    app_prompt = st.text_area("Describe your app idea:")
    repo_name_input = st.text_input("GitHub Repository Name:", value="generated-streamlit-app")
    pitch_deck = st.checkbox("Pitch Deck")
    document = st.checkbox("Document")
    submitted = st.form_submit_button("Generate App Code")

def extract_imports(code):
    tree = ast.parse(code)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module.split('.')[0])
    return list(imports)

def generate_requirements(imports):
    base_requirements = {
        'streamlit': 'streamlit',
        'openai': 'openai',
        'requests': 'requests',
        'github': 'PyGithub',
        'dotenv': 'python-dotenv',
        'nacl': 'pynacl',
        'plotly': 'plotly',
        'pyairtable': 'pyairtable'
    }
    return "\n".join([base_requirements.get(lib, lib) for lib in imports if lib in base_requirements])

if submitted:
    # Step 1: Generate code using OpenAI API
    with st.spinner("Generating code..."):
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": f"Generate a Streamlit app for the following idea:\n{app_prompt}"}
                ]
            )
            message_content = response.choices[0].message.content.strip()
            code_block = re.search(r'```python\n(.*?)\n```', message_content, re.DOTALL).group(1)
            st.session_state['code_block'] = code_block  # Store in session state
            st.code(code_block, language='python')
            print("Code generated successfully.")
        except Exception as e:
            st.error(f"Error generating code: {e}")
            print(f"Error generating code: {e}")

        # Add to Airtable if Pitch Deck or Document is checked
        if pitch_deck or document:
            try:
                unique_id = str(uuid.uuid4())
                new_row = {
                    "unique_id": unique_id,
                    "app_prompt": app_prompt,
                    "repo_name_input": repo_name_input,
                    "Status": "In Progress",
                    "pitch_deck": pitch_deck,
                    "document": document,
                }
                airtable.create(new_row)
                st.success("Added to Airtable and triggered Make.com workflow!")
                st.session_state['uuid'] = unique_id  # Store UUID in session state for fetching download links later
            except Exception as e:
                st.error(f"Error updating Airtable: {e}")
                print(f"Error updating Airtable: {e}")
                st.stop()

deploy_button = st.button("Deploy Application")

if deploy_button:
    if 'code_block' not in st.session_state:
        st.error("No code to deploy. Please generate the code first.")
    else:
        code_block = st.session_state['code_block']  # Retrieve from session state
        print("Deploy button clicked.")
        with st.spinner("Creating GitHub repository..."):
            try:
                g = Github(github_token)
                user = g.get_user()
                repo_name = repo_name_input  # Use the user-provided repository name

                # Check if the repository already exists
                repo_exists = any(repo.name == repo_name for repo in user.get_repos())
                if repo_exists:
                    unique_suffix = str(uuid.uuid4())[:8]
                    repo_name = f"{repo_name}-{unique_suffix}"

                repo = user.create_repo(repo_name)
                print(f"GitHub repository '{repo.name}' created successfully.")
                st.info(f"GitHub repository '{repo.name}' created successfully.")
            except Exception as e:
                st.error(f"Error creating GitHub repository: {e}")
                print(f"Error creating GitHub repository: {e}")
                st.stop()

        st.info("Pushing code to GitHub...")
        try:
            # Commit the code to the repository
            repo.create_file("app.py", "initial commit", code_block)
            print("app.py pushed to GitHub.")

            # Extract imports and generate requirements.txt
            imports = extract_imports(code_block)
            requirements = generate_requirements(imports)
            if 'streamlit' not in requirements:
                requirements = 'streamlit\n' + requirements
            repo.create_file("requirements.txt", "add requirements", requirements)
            print("requirements.txt pushed to GitHub.")

            # Create and push the Procfile
            procfile = "web: streamlit run app.py"
            repo.create_file("Procfile", "add Procfile", procfile)
            print("Procfile pushed to GitHub.")

            # Create and push the setup.sh file
            setup_sh = """
            mkdir -p ~/.streamlit/
            echo "\\
            [server]\\n\\
            headless = true\\n\\
            port = $PORT\\n\\
            enableCORS = false\\n\\
            \\n\\
            " > ~/.streamlit/config.toml
            chmod +x setup.sh
            """
            repo.create_file("setup.sh", "add setup.sh", setup_sh)
            print("setup.sh pushed to GitHub.")

            # Create and push the Dockerfile
            dockerfile = """
            # Use the official Python image from the Docker Hub
            FROM python:3.11-slim

            # Set the working directory in the container
            WORKDIR /app

            # Copy the requirements file into the container
            COPY requirements.txt .

            # Install the dependencies
            RUN pip install --no-cache-dir -r requirements.txt

            # Copy the rest of the application code into the container
            COPY . .

            # Expose the port that Streamlit will run on
            EXPOSE 8000

            # Add execute permissions to the entrypoint script
            RUN chmod +x entrypoint.sh

            # Specify the entrypoint script
            ENTRYPOINT ["./entrypoint.sh"]
            """
            repo.create_file("Dockerfile", "add Dockerfile", dockerfile)
            print("Dockerfile pushed to GitHub.")

            # Create and push the entrypoint.sh file
            entrypoint_sh = """
            #!/bin/bash
            # Set the Streamlit server port to the value of the PORT environment variable
            export STREAMLIT_SERVER_PORT=${PORT}

            # Run Streamlit with the specified port
            streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0
            """
            repo.create_file("entrypoint.sh", "add entrypoint.sh", entrypoint_sh)
            print("entrypoint.sh pushed to GitHub.")

            # Create and push the heroku.yml file
            heroku_yml = """
            build:
              docker:
                web: Dockerfile

            run:
              web: ./entrypoint.sh
            """
            repo.create_file("heroku.yml", "add heroku.yml", heroku_yml)
            print("heroku.yml pushed to GitHub.")

            st.success("Code pushed to GitHub successfully!")
        except Exception as e:
            st.error(f"Error pushing code to GitHub: {e}")
            print(f"Error pushing code to GitHub: {e}")
            st.stop()

        st.info("Creating GitHub secret for Heroku API Key...")
        try:
            # Fetch the public key for the repository
            repo_name = repo.full_name
            public_key_url = f"https://api.github.com/repos/{repo_name}/actions/secrets/public-key"
            headers = {"Authorization": f"Bearer {github_token}"}
            response = requests.get(public_key_url, headers=headers)
            response.raise_for_status()
            public_key_data = response.json()
            public_key = public_key_data["key"]
            key_id = public_key_data["key_id"]

            # Encrypt the Heroku API key
            def encrypt_secret(public_key, secret_value):
                public_key = nacl.public.PublicKey(public_key.encode("utf-8"), nacl.encoding.Base64Encoder())
                sealed_box = nacl.public.SealedBox(public_key)
                encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
                return base64.b64encode(encrypted).decode("utf-8")

            encrypted_heroku_api_key = encrypt_secret(public_key, heroku_api_key)

            # Create the secret
            secret_url = f"https://api.github.com/repos/{repo_name}/actions/secrets/HEROKU_API_KEY"
            payload = {
                "encrypted_value": encrypted_heroku_api_key,
                "key_id": key_id
            }
            response = requests.put(secret_url, headers=headers, json=payload)
            response.raise_for_status()

            st.success("GitHub secret for Heroku API Key created successfully!")
            print("GitHub secret for Heroku API Key created successfully!")
        except Exception as e:
            st.error(f"Error creating GitHub secret: {e}")
            print(f"Error creating GitHub secret: {e}")
            st.stop()

        with st.spinner("Deploying app to Heroku..."):
            try:
                # Generate a valid and unique Heroku app name
                heroku_app_name_base = re.sub(r'[^a-z0-9-]', '', repo_name.lower())[:20].strip('-')
                unique_suffix = str(uuid.uuid4())[:8]
                heroku_app_name = f"{heroku_app_name_base}-{unique_suffix}"
                headers = {
                    "Authorization": f"Bearer {heroku_api_key}",
                    "Accept": "application/vnd.heroku+json; version=3",
                }
                payload = {
                    "name": heroku_app_name,
                    "stack": "container"
                }
                response = requests.post("https://api.heroku.com/apps", json=payload, headers=headers)
                if response.status_code == 201:
                    st.success("Heroku app created successfully")
                    print("Heroku app created successfully.")
                else:
                    st.error(f"Failed to create Heroku app: {response.json()}")
                    print(f"Failed to create Heroku app: {response.json()}")
                    st.stop()
            except Exception as e:
                st.error(f"Error creating Heroku app: {e}")
                print(f"Error creating Heroku app: {e}")
                st.stop()

        try:
            # Create GitHub Action to deploy to Heroku using Docker
            action_yml = f"""
            name: Deploy to Heroku

            on:
              push:
                branches:
                  - main

            jobs:
              build-and-deploy:
                runs-on: ubuntu-latest

                steps:
                  - name: Checkout code
                    uses: actions/checkout@v3

                  - name: Set up Docker Buildx
                    uses: docker/setup-buildx-action@v2

                  - name: Login to Heroku Container Registry
                    run: echo "${{{{ secrets.HEROKU_API_KEY }}}}" | docker login --username=_ --password-stdin registry.heroku.com

                  - name: Build Docker image
                    run: docker build -t registry.heroku.com/{heroku_app_name}/web .

                  - name: Push Docker image to Heroku
                    run: docker push registry.heroku.com/{heroku_app_name}/web

                  - name: Release app
                    run: |
                      heroku container:release web --app {heroku_app_name}
                    env:
                      HEROKU_API_KEY: ${{{{ secrets.HEROKU_API_KEY }}}}
            """
            repo.create_file(".github/workflows/main.yml", "add GitHub Action", action_yml)
            print("GitHub Action created.")

            # Push changes to GitHub to trigger the Action
            repo.update_file("app.py", "deploy to Heroku", code_block, repo.get_contents("app.py").sha)
            repo.update_file("requirements.txt", "deploy to Heroku", requirements, repo.get_contents("requirements.txt").sha)
            repo.update_file("Procfile", "deploy to Heroku", procfile, repo.get_contents("Procfile").sha)
            repo.update_file("setup.sh", "deploy to Heroku", setup_sh, repo.get_contents("setup.sh").sha)
            repo.update_file("Dockerfile", "deploy to Heroku", dockerfile, repo.get_contents("Dockerfile").sha)
            repo.update_file("entrypoint.sh", "deploy to Heroku", entrypoint_sh, repo.get_contents("entrypoint.sh").sha)
            repo.update_file("heroku.yml", "deploy to Heroku", heroku_yml, repo.get_contents("heroku.yml").sha)
            print("Pushed updates to GitHub to trigger deployment.")

            st.info("Waiting for deployment to complete...")
            time.sleep(60)  # Adjust this delay as needed

            app_url = f"https://{heroku_app_name}.herokuapp.com"
            st.success(f"Your app has been deployed! You can access it here: {app_url}")
            print(f"Your app has been deployed! You can access it here: {app_url}")

            # Update Airtable Status to Done
            if 'uuid' in st.session_state:
                airtable_record_id = st.session_state['uuid']
                try:
                    airtable.update_by_field('unique_id', airtable_record_id, {"Status": "Done"})
                    print("Airtable status updated to Done.")
                except Exception as e:
                    st.error(f"Error updating Airtable status: {e}")
                    print(f"Error updating Airtable status: {e}")

        except Exception as e:
            st.error(f"Error deploying to Heroku: {e}")
            print(f"Error deploying to Heroku: {e}")

# Create functions to provide download links for the generated pitch deck and document
def get_download_links(uuid):
    try:
        airtable_records = airtable.all()
        for record in airtable_records:
            fields = record['fields']
            if fields.get('unique_id') == uuid:
                pitch_deck_url = fields.get('pitch_deck_url')
                document_url = fields.get('document_url')
                if pitch_deck_url:
                    st.markdown(f"[Download Pitch Deck]({pitch_deck_url})")
                if document_url:
                    st.markdown(f"[Download Document]({document_url})")
                return
        st.info("No matching record found in Airtable.")
    except Exception as e:
        st.error(f"Error fetching download links: {e}")

# Show download links if available
if 'uuid' in st.session_state:
    get_download_links(st.session_state['uuid'])
