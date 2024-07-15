#!/bin/bash

# Set the Streamlit server port to the value of the PORT environment variable
export STREAMLIT_SERVER_PORT=${PORT}

# Run Streamlit with the specified port
streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0
