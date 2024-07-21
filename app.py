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
import zipfile
from io import BytesIO
from pyairtable import Table
import nacl.encoding
import nacl.public
import nacl.signing

# Load environment variables from .env file
load_dotenv()

# Access secrets
openai_api_key = os.getenv("OPENAI_API_KEY")
github_token = os.getenv("MY_GITHUB_TOKEN")
heroku_api_key = os.getenv("HEROKU_API_KEY")
airtable_api_key = os.getenv("AIRTABLE_API_KEY")
airtable_base_id = os.getenv("AIRTABLE_BASE_ID")
airtable_table_name = os.getenv("AIRTABLE_TABLE_NAME")

# Ensure secrets are set
required_secrets = [
    openai_api_key, github_token, heroku_api_key,
    airtable_api_key, airtable_base_id, airtable_table_name
]

for secret in required_secrets:
    if not secret:
        st.error(f"{secret} not found. Please set the corresponding environment variable.")
        st.stop()

# Initialize OpenAI client
client = OpenAI(api_key=openai_api_key)

# Initialize Airtable client
airtable = Table(airtable_api_key, airtable_base_id, airtable_table_name)

# Set page configuration
st.set_page_config(
    page_title="AIrlyft",
    page_icon=":rocket:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Title and subtitle
st.title("AIrlyft")
st.markdown("### Enter your ideas, we will generate the code - initial version and deploy it. You can also get pitch deck and business plans and other marketing materials.")

# Form for user input
st.markdown("### Describe your app idea and we'll generate and deploy it for you!")
with st.form("app_idea_form"):
    app_prompt = st.text_area("Describe your app idea:")
    app_type = st.selectbox("Select App Type:", ["Streamlit", "React"])
    submitted = st.form_submit_button("Generate App Code")

# Status dictionary
status_dict = {
    "Code Generation": "not started",
    "GitHub Repository": "not started",
    "Heroku Deployment": "not started",
    "Pitch Deck": "not started",
    "Business Plan": "not started",
}

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

def update_status(key, status):
    status_dict[key] = status
    st.session_state.status_dict = status_dict

def display_status():
    st.sidebar.markdown("### Status")
    for key, value in status_dict.items():
        if value == "completed":
            st.sidebar.markdown(f"✅ {key}")
        elif value == "in progress":
            st.sidebar.markdown(f"⏳ {key}")
        else:
            st.sidebar.markdown(f"🔲 {key}")

if 'status_dict' not in st.session_state:
    st.session_state.status_dict = status_dict

display_status()

if submitted:
    # Step 1: Generate code using OpenAI API
    update_status("Code Generation", "in progress")
    display_status()
    with st.spinner("Generating code..."):
        try:
            if app_type == "Streamlit":
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": f"""Generate a Streamlit app for the following idea:\n{app_prompt}. make sure there are no errors, it has to be modern looking, include relevant icons and add css to make it look modern and sleek usable application. if data is needed then, create an input box for the user to enter thier own openai api key and Use openai.chat.completions.create and  gpt4 model and the below structure to get and parse the response response = openai.chat.completions.create model=gpt-4, messages='role': 'system', 'content': 'You are a helpful assistant.', 'role': 'user', 'content': f'give me all the food festivals near .'} message_content = response.choices[0].message.content.strip() - Use message_content = response.choices[0].message.content.strip() instead of message_content = response.choices[0].message['content'].strip()"""}
                    ]
                )
                message_content = response.choices[0].message.content.strip()
                message_content = message_content.replace("openai.ChatCompletion.create", "openai.chat.completions.create")
                code_block = re.search(r'```python\n(.*?)\n```', message_content, re.DOTALL).group(1)
            else:
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": f"Generate a React app for the following idea:\n{app_prompt}. make sure there are no errors, it has to be modern looking, include relevant icons and add css to make it look modern and sleek usable application. Create a zip file of the project including package.json and all necessary files. if data is needed then, create an input box for the user to enter thier own openai api key"}
                    ]
                )
                message_content = response.choices[0].message.content.strip()
                zip_content = re.search(r'```base64\n(.*?)\n```', message_content, re.DOTALL).group(1)
                zip_data = base64.b64decode(zip_content)
                with open("react-app.zip", "wb") as f:
                    f.write(zip_data)
                with zipfile.ZipFile("react-app.zip", 'r') as zip_ref:
                    zip_ref.extractall("react-app")
                code_block = None

            st.session_state['code_block'] = code_block  # Store in session state
            st.session_state['app_type'] = app_type  # Store app type in session state
            st.code(code_block, language='python' if app_type == "Streamlit" else 'javascript')
            update_status("Code Generation", "completed")
            st.success("Code generated successfully.")
        except Exception as e:
            st.error(f"Error generating code: {e}")
            print(f"Error generating code: {e}")

        # Add to Airtable if Pitch Deck or Business Plan is checked
        unique_id = str(uuid.uuid4())
        app_name = f"{repo_name_input}-{unique_id[:8]}"
        new_row = {
            "unique_id": unique_id,
            "app_prompt": app_prompt,
            "app_name": app_name,
            "repo_name_input": repo_name_input,
            "Status": "In progress",
            "pitch_deck": False,
            "business_plan": False,
        }
        try:
            airtable.create(new_row)
            st.session_state['uuid'] = unique_id  # Store UUID in session state for fetching download links later
            st.session_state['app_name'] = app_name
        except Exception as e:
            st.error(f"Error updating Airtable: {e}")
            print(f"Error updating Airtable: {e}")
            st.stop()

deploy_button = st.button("Deploy Application")

if deploy_button:
    if 'code_block' not in st.session_state:
        st.error("No code to deploy. Please generate the code first.")
    else:
        app_type = st.session_state['app_type']
        with st.spinner("Deploying application..."):
            try:
                if app_type == "Streamlit":
                    code_block = st.session_state['code_block']
                    update_status("GitHub Repository", "in progress")
                    display_status()
                    g = Github(github_token)
                    user = g.get_user()
                    repo_name = st.session_state['app_name']

                    # Check if the repository already exists
                    repo_exists = any(repo.name == repo_name for repo in user.get_repos())
                    if repo_exists:
                        unique_suffix = str(uuid.uuid4())[:8]
                        repo_name = f"{repo_name}-{unique_suffix}"

                    repo = user.create_repo(repo_name)
                    update_status("GitHub Repository", "completed")
                    st.success(f"GitHub repository '{repo.name}' created successfully.")

                    st.info("Pushing code to GitHub...")
                    # Commit the code to the repository
                    repo.create_file("app.py", "initial commit", code_block)

                    # Extract imports and generate requirements.txt
                    imports = extract_imports(code_block)
                    requirements = generate_requirements(imports)
                    if 'streamlit' not in requirements:
                        requirements = 'streamlit\n' + requirements
                    repo.create_file("requirements.txt", "add requirements", requirements)

                    # Create and push the Procfile
                    procfile = "web: streamlit run app.py"
                    repo.create_file("Procfile", "add Procfile", procfile)

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

                    # Create and push the entrypoint.sh file
                    entrypoint_sh = """
                    #!/bin/bash
                    # Set the Streamlit server port to the value of the PORT environment variable
                    export STREAMLIT_SERVER_PORT=${PORT}

                    # Run Streamlit with the specified port
                    streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0
                    """
                    repo.create_file("entrypoint.sh", "add entrypoint.sh", entrypoint_sh)

                    # Create and push the heroku.yml file
                    heroku_yml = """
                    build:
                      docker:
                        web: Dockerfile

                    run:
                      web: ./entrypoint.sh
                    """
                    repo.create_file("heroku.yml", "add heroku.yml", heroku_yml)

                    st.success("Code pushed to GitHub successfully!")

                    st.info("Creating GitHub secret for Heroku API Key...")
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

                    with st.spinner("Deploying app to Heroku..."):
                        update_status("Heroku Deployment", "in progress")
                        display_status()
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
                        else:
                            st.error(f"Failed to create Heroku app: {response.json()}")
                            st.stop()

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

                        # Push changes to GitHub to trigger the Action
                        repo.update_file("app.py", "deploy to Heroku", code_block, repo.get_contents("app.py").sha)
                        repo.update_file("requirements.txt", "deploy to Heroku", requirements, repo.get_contents("requirements.txt").sha)
                        repo.update_file("Procfile", "deploy to Heroku", procfile, repo.get_contents("Procfile").sha)
                        repo.update_file("setup.sh", "deploy to Heroku", setup_sh, repo.get_contents("setup.sh").sha)
                        repo.update_file("Dockerfile", "deploy to Heroku", dockerfile, repo.get_contents("Dockerfile").sha)
                        repo.update_file("entrypoint.sh", "deploy to Heroku", entrypoint_sh, repo.get_contents("entrypoint.sh").sha)
                        repo.update_file("heroku.yml", "deploy to Heroku", heroku_yml, repo.get_contents("heroku.yml").sha)

                        st.info("Waiting for deployment to complete...")
                        time.sleep(60)  # Adjust this delay as needed

                        app_url = f"https://{heroku_app_name}.herokuapp.com"
                        st.success(f"Your app has been deployed! You can access it here: [Heroku App]({app_url})")

                        # Update Airtable Status to Done
                        if 'uuid' in st.session_state:
                            airtable_record_id = st.session_state['uuid']
                            try:
                                record = airtable.first(formula=f"{{unique_id}}='{airtable_record_id}'")
                                if record:
                                    record_id = record['id']
                                    airtable.update(record_id, {"Status": "Done"})
                                    st.success("Airtable status updated to Done.")
                            except Exception as e:
                                st.error(f"Error updating Airtable status: {e}")
                        update_status("Heroku Deployment", "completed")
                        display_status()
                else:
                    st.success("React app code has been generated and zipped successfully.")
                    with open("react-app.zip", "rb") as file:
                        st.download_button(
                            label="Download React App",
                            data=file,
                            file_name="react-app.zip",
                            mime="application/zip"
                        )
            except Exception as e:
                st.error(f"Error deploying application: {e}")
                print(f"Error deploying application: {e}")

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
                    st.markdown(f"[Download Business Plan]({document_url})")
                return
        st.info("No matching record found in Airtable.")
    except Exception as e:
        st.error(f"Error fetching download links: {e}")

# Show download links if available
if 'uuid' in st.session_state:
    get_download_links(st.session_state['uuid'])

# Add sections for Pitch Deck and Business Plan
st.markdown("### Generate Additional Materials")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Pitch Deck")
    generate_pitch_deck_button = st.button("Generate Pitch Deck")

with col2:
    st.subheader("Business Plan")
    generate_business_plan_button = st.button("Generate Business Plan")

if generate_pitch_deck_button:
    # Code to trigger pitch deck generation
    st.write("Generating Pitch Deck...")
    if 'uuid' not in st.session_state:
        st.error("No app data found. Please generate the code first.")
    else:
        try:
            payload = {
                "app_name": st.session_state['app_name'],
                "app_prompt": app_prompt,
                "pitch_deck": True,
                "business_plan": False,
            }
            response = requests.post(os.getenv("MAKE_WEBHOOK_URL"), json=payload)
            response.raise_for_status()
            st.success("Pitch Deck generation triggered successfully.")
        except Exception as e:
            st.error(f"Error triggering Pitch Deck generation: {e}")
            print(f"Error triggering Pitch Deck generation: {e}")

if generate_business_plan_button:
    # Code to trigger business plan generation
    st.write("Generating Business Plan...")
    if 'uuid' not in st.session_state:
        st.error("No app data found. Please generate the code first.")
    else:
        try:
            payload = {
                "app_name": st.session_state['app_name'],
                "app_prompt": app_prompt,
                "pitch_deck": False,
                "business_plan": True,
            }
            response = requests.post(os.getenv("MAKE_WEBHOOK_URL"), json=payload)
            response.raise_for_status()
            st.success("Business Plan generation triggered successfully.")
        except Exception as e:
            st.error(f"Error triggering Business Plan generation: {e}")
            print(f"Error triggering Business Plan generation: {e}")
