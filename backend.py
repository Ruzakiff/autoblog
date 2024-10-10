from flask import Flask, request, jsonify, render_template, Response, redirect, url_for
from openai import OpenAI
import csv
from io import StringIO
import json
import uuid

app = Flask(__name__)
client = OpenAI()  # Assumes OPENAI_API_KEY is set in environment variables

# In-memory storage for generated content (replace with a database in production)
generated_content = {}

def analyze_csv(data, stream=False):
    print("Entering analyze_csv function")
    print("Input data:", data)

    prompt = f"""Choose from the below list of longtail keywords, and generate blog titles for {__import__('datetime').datetime.now().strftime('%B %Y')}. Rank and align these titles by how well they support Armarkat's goals as outlined above:
    
    Format the output as a JSON array of objects, each containing:
    {{
        "keyword": "...",
        "title": "...",
        "searchVolume": "...",
        "competition": "...",
        "alignment_with_goals":"...",
        "totalScore": ...
    }}
    
    Rank the list by totalScore in descending order. OUTPUT ONLY EXPLICIT RAW JSON
    \n\n{data}"""
    
    print("Generated prompt:", prompt)

    from context import messages
    messages.append({"role": "user", "content": prompt})

    completion = client.chat.completions.create(
        model="o1-preview-2024-09-12",  # Use an appropriate model
        messages=messages
    )
    response_content = completion.choices[0].message.content
    
    print("Raw API response:", response_content)

    # Clean the response content
    response_content = response_content.strip()
    if response_content.startswith("```json"):
        response_content = response_content[7:]  # Remove ```json
    if response_content.endswith("```"):
        response_content = response_content[:-3]  # Remove ```
    
    print("Cleaned response content:", response_content)

    # Attempt to parse the JSON
    try:
        json_data = json.loads(response_content)
        print("Successfully parsed JSON data")
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON. Error: {str(e)}")
        print("Raw content:", response_content)
        return []  # Return an empty list if parsing fails
    
    messages.append({"role": "assistant", "content": json.dumps(json_data)})
    return json_data  # Return the parsed JSON data as a Python object

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/upload-csv', methods=['POST'])
def upload_csv():
    print("Entering upload_csv function")

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and file.filename.endswith('.csv'):
        try:
            csv_content = file.read().decode('utf-8')
            csv_file = StringIO(csv_content)
            csv_reader = csv.reader(csv_file)
            
            headers = next(csv_reader)
            data = [dict(zip(headers, row)) for row in csv_reader]
            
            print("CSV data:", data)

            result = analyze_csv(data)
            
            print("Analyze CSV result:", result)

            # Generate a unique ID for this result
            result_id = str(uuid.uuid4())
            generated_content[result_id] = result  # Store the result as a list of dictionaries
            
            print(f"Stored result with ID: {result_id}")

            # Return JSON response with the result ID
            return jsonify({'id': result_id}), 200
        except Exception as e:
            print(f"Error processing CSV: {str(e)}")
            return jsonify({'error': f'Error processing CSV: {str(e)}'}), 500
    else:
        return jsonify({'error': 'Invalid file format. Please upload a CSV file.'}), 400

@app.route('/generate-content', methods=['POST'])
def generate_content():
    selected_data = request.json
    
    # Generate content for each selected item
    generated_items = []
    for item in selected_data:
        prompt = f"Write a blog post about {item['keyword']} with the title: {item['title']}"
        response = client.chat.completions.create(
            model="gpt-4-0125-preview",  # or use the model that's available to you
            messages=[{"role": "user", "content": prompt}]
        )
        generated_items.append({
            "keyword": item['keyword'],
            "title": item['title'],
            "content": response.choices[0].message.content
        })
    
    # Store the generated content with a unique ID
    content_id = str(uuid.uuid4())
    generated_content[content_id] = generated_items
    
    return jsonify({"id": content_id})

@app.route('/content')
def display_content():
    print("Entering display_content function")

    content_id = request.args.get('id')
    print(f"Requested content ID: {content_id}")

    if content_id not in generated_content:
        print("Content not found")
        return "Content not found", 404
    
    items = generated_content[content_id]
    print("Retrieved items:", items)
    print("Type of items:", type(items))
    print("Number of items:", len(items))

    # Add this block to check each item in the list
    for i, item in enumerate(items):
        print(f"Item {i}:")
        for key, value in item.items():
            print(f"  {key}: {value}")

    return render_template('parsedcsv.html', items=items)

if __name__ == '__main__':
    app.run(debug=True)


