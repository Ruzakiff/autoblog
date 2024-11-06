import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO
from flask import Flask, request, jsonify
from openai import OpenAI
app = Flask(__name__)

# Constants
SCOPES = ['https://www.googleapis.com/auth/drive.file']
FOLDER_ID = '1B83n4LXCYmWjEVs6kaAH1k3pUoClscBO'  # Replace with your actual folder ID

def get_google_drive_service():
    # Get the credentials JSON from the environment variable
    creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    if not creds_json:
        raise ValueError("Google credentials not found in environment variables")
    
    # Parse the JSON string
    creds_info = json.loads(creds_json)
    
    # Create credentials object
    credentials = service_account.Credentials.from_service_account_info(
        creds_info, scopes=SCOPES)
    
    return build('drive', 'v3', credentials=credentials)

@app.route('/export-to-drive', methods=['POST'])
def export_to_drive():
    data = request.json
    title = data.get('title')
    content = data.get('content')

    try:
        # Initialize OpenAI client locally
        client = OpenAI()
        
        # Format content using OpenAI
        response = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": "Format the provided content to markdown to be more webblog friendly. Do not paraphrase, just reformat for spacing and ease of reading. Never include conclusion/body/intro headers."},
                {"role": "user", "content": f"Title: {title}\n\nContent: {content}"}
            ],
            temperature=0,
            max_tokens=16384
        )
        
        formatted_content = response.choices[0].message.content
        print(formatted_content)
        
        # Continue with Google Drive export using formatted content
        drive_service = get_google_drive_service()
        file_metadata = {
            'name': title,
            'mimeType': 'application/vnd.google-apps.document',
            'parents': [FOLDER_ID]
        }
        media = MediaIoBaseUpload(
            BytesIO(formatted_content.encode('utf-8')),
            mimetype='text/plain',
            resumable=True
        )
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return jsonify({'success': True, 'fileId': file.get('id')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True)

