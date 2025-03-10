# frontend/app.py
import streamlit as st
import requests
import json
from datetime import datetime
import time
import os

# API endpoint
API_URL = os.getenv("API_URL", "http://backend:8000")

# Page config
st.set_page_config(
    page_title="AI Chatbot",
    page_icon="🤖",
    layout="wide",
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None

if "token" not in st.session_state:
    st.session_state.token = None

# Authentication functions
def login(username, password):
    """Authenticate user and get token"""
    try:
        response = requests.post(
            f"{API_URL}/token",
            data={"username": username, "password": password}
        )
        if response.status_code == 200:
            data = response.json()
            st.session_state.token = data["access_token"]
            return True
        else:
            return False
    except Exception as e:
        st.error(f"Error during login: {str(e)}")
        return False

def get_conversations():
    """Get user conversations"""
    try:
        headers = {"Authorization": f"Bearer {st.session_state.token}"}
        response = requests.get(f"{API_URL}/api/conversations/", headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error fetching conversations: {response.status_code}")
            return []
    except Exception as e:
        st.error(f"Error fetching conversations: {str(e)}")
        return []

def send_message(content, model_name):
    """Send message to API and get response"""
    try:
        headers = {
            "Authorization": f"Bearer {st.session_state.token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "content": content,
            "conversation_id": st.session_state.conversation_id,
            "model_name": model_name
        }
        
        response = requests.post(
            f"{API_URL}/api/messages/",
            headers=headers,
            json=data
        )
        
        if response.status_code == 200:
            data = response.json()
            if not st.session_state.conversation_id:
                st.session_state.conversation_id = data["conversation_id"]
            return data
        else:
            st.error(f"Error sending message: {response.status_code}")
            if response.text:
                st.error(response.text)
            return None
    except Exception as e:
        st.error(f"Error sending message: {str(e)}")
        return None

# Sidebar for settings and conversation history
with st.sidebar:
    st.title("AI Chatbot")
    
    # Login form if not authenticated
    if not st.session_state.token:
        with st.form("login_form"):
            st.subheader("Login")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit_button = st.form_submit_button("Login")
            
            if submit_button:
                if login(username, password):
                    st.success("Login successful!")
                    st.experimental_rerun()
                else:
                    st.error("Invalid username or password")
    else:
        # Model selection
        st.subheader("Model Settings")
        model_options = ["gpt-3.5-turbo", "gpt-4", "claude-2"]
        selected_model = st.selectbox("Select Model", model_options)
        
        # Conversation history
        st.subheader("Conversations")
        if st.button("Refresh Conversations"):
            conversations = get_conversations()
            
            if conversations:
                for conv in conversations:
                    if st.button(f"{conv['title']} - {conv['created_at'][:10]}", key=conv["id"]):
                        st.session_state.conversation_id = conv["id"]
                        st.session_state.messages = conv["messages"]
                        st.experimental_rerun()
            else:
                st.info("No conversations found")
        
        # New conversation button
        if st.button("New Conversation"):
            st.session_state.conversation_id = None
            st.session_state.messages = []
            st.experimental_rerun()
        
        # Logout button
        if st.button("Logout"):
            st.session_state.token = None
            st.session_state.conversation_id = None
            st.session_state.messages = []
            st.experimental_rerun()

# Main chat interface
st.title("AI Chatbot")

# Display messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# Chat input
if st.session_state.token:  # Only show chat input if authenticated
    user_input = st.chat_input("Type your message here...")
    
    if user_input:
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)
        
        # Send message to API
        with st.spinner("AI is thinking..."):
            response = send_message(user_input, selected_model)
            
            if response:
                # Check for assistant message in conversation (it's processed asynchronously)
                time.sleep(1)  # Small delay to allow processing
                
                # Poll for assistant response
                max_retries = 30
                for i in range(max_retries):
                    conversations = get_conversations()
                    current_conv = next((c for c in conversations if c["id"] == st.session_state.conversation_id), None)
                    
                    if current_conv:
                        messages = current_conv["messages"]
                        # Find assistant message that comes after user message
                        for j in range(len(messages)-1, 0, -1):
                            if messages[j]["role"] == "assistant" and j > 0 and messages[j-1]["content"] == user_input:
                                # Add assistant message to chat
                                assistant_msg = messages[j]
                                st.session_state.messages.append({
                                    "role": "assistant", 
                                    "content": assistant_msg["content"]
                                })
                                with st.chat_message("assistant"):
                                    st.write(assistant_msg["content"])
                                break
                        else:
                            # If assistant message not found, continue polling
                            if i < max_retries - 1:
                                time.sleep(1)
                                continue
                            else:
                                st.error("No response received from assistant")
                        break
            else:
                st.error("Failed to send message")
else:
    st.info("Please login to start chatting")
